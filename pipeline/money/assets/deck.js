/* School Money — deck.js (units C2, D1). Defer-loaded on /deck/ only; the page says what to do without it.
   Builds presentation decks in the browser: three packs for one school (the governors' finance pack, the
   PTFA pack and the school review pack), a compare deck and an area deck.
   One slide model feeds the on-screen slides, the print layout and the PowerPoint file. Packs carry
   ratings (icon + word + colour), an editable meeting line, a notes box on every slide and an actions table;
   notes and actions are kept in this browser (localStorage, per school and pack) and go into the
   PowerPoint as speaker notes and an editable table.
   Pure model exported as globalThis.MoneyDeck (tested under node); DOM wiring runs only in a browser.

   Reads: /data/s/<urn>.json (including its optional 'nearby' block), /data/sx/<urn>.json, /data/a/<id>.json
          and the #deck-context JSON block that deck.py writes (IFS framings, questions and context lines with
          page numbers, real-terms label).
   Query: ?urn=<urn>&view=governors|ptfa|review (view=school, or no view, is the governors' pack),
          ?urns=a,b,c&view=compare, ?area=<area id>.
   Loads PptxGenJS from the CDN only when "Download PowerPoint" is pressed. */
(function (root) {
  "use strict";

  // Pinned library. Hash checked against the jsDelivr data API and a fresh download on 2026-11-07.
  var PPTX_URL = "https://cdn.jsdelivr.net/npm/pptxgenjs@3.12.0/dist/pptxgen.bundle.js";
  var PPTX_SRI = "sha384-Cck14aA9cifjYolcnjebXRfWGkz5ltHMBiG4px/j8GS+xQcb7OhNQWZYyWjQ+UwQ";

  // status.ORDER: 'reserve_held_by_trust' (an academy whose trust pools reserves, so its own is £0) comes last.
  var HELD = "reserve_held_by_trust";
  var ORDER = ["in_deficit", "heading_for_deficit", "tight", "healthy", "large_reserves", HELD];
  var LABELS = { in_deficit: "In deficit", heading_for_deficit: "Heading for deficit", tight: "Tight", healthy: "Healthy", large_reserves: "Large reserves",
    reserve_held_by_trust: "Reserve held by the trust" };
  var ICONS = { in_deficit: "▼", heading_for_deficit: "↘", tight: "●", healthy: "✓", large_reserves: "▲", reserve_held_by_trust: "◇" };
  var SITE = "School Money";
  var CHARITY_SOURCE = "Charity Commission register";
  var AREA_SOURCE = "School Money medians of DfE returns";
  var DSG_SOURCE = "DfE section 251 outturn";
  // The measure's one name (contract C8): the council's whole cumulative DSG balance, all four blocks together.
  var DSG_NAME = "Dedicated Schools Grant balance (all four blocks)";
  var REGISTER_HOME = "https://register-of-charities.charitycommission.gov.uk/";
  // A charity's page on the register (contract C9). The number sits mid-URL, so links are only built by charityUrl().
  var CHARITY_PAGE = ["https://register-of-charities.charitycommission.gov.uk/charity-search?p_p_id=uk_gov_ccew_onereg_charitydetails_web_portlet_CharityDetailsPortlet" +
    "&p_p_lifecycle=0&p_p_state=maximized&p_p_mode=view&_uk_gov_ccew_onereg_charitydetails_web_portlet_CharityDetailsPortlet_regId=",
    "&_uk_gov_ccew_onereg_charitydetails_web_portlet_CharityDetailsPortlet_subId=0"];
  var FBIT_HOME = "https://financial-benchmarking-and-insights-tool.education.gov.uk/school/";
  var MARK = "◆";
  var MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  // Finance-row metrics the decks read from /data/sx (m) with /data/s years[] as the fallback.
  var METRICS = ["total_income", "total_expenditure", "in_year_balance", "revenue_reserve", "grant_funding", "self_generated",
    "sen_funding", "pupil_premium", "donations_revenue", "staff_total", "facilities_income", "catering_income",
    "teaching_staff", "education_support_staff", "supply_staff", "admin_clerical_staff", "premises", "energy", "educational_supplies", "bought_in_services"];
  var S_FALLBACK = { total_income: "income", total_expenditure: "spend", in_year_balance: "balance", revenue_reserve: "reserve" };
  // The deck's metric names, as /data/sx names them (series.METRICS); the deck name is read when the SERIES name is absent.
  var SX_NAMES = { grant_funding: "grant_funding_government", self_generated: "self_generated_income", staff_total: "total_staff" };
  var SPEND_LINES = [["teaching_staff", "Teachers"], ["education_support_staff", "Support staff (e.g. TAs)"], ["supply_staff", "Supply staff"],
    ["admin_clerical_staff", "Admin and clerical"], ["premises", "Premises"], ["energy", "Energy"],
    ["educational_supplies", "Learning resources and ICT"], ["bought_in_services", "Bought-in services"]];

  // ======================================================================
  // Formatting
  // ======================================================================
  function isNum(v) { return typeof v === "number" && isFinite(v); }
  function isObj(v) { return v != null && typeof v === "object" && !Array.isArray(v); }
  function fmtMoney(v, signed) {
    var a = root.MoneyApp;
    if (a && typeof a.fmtMoney === "function") return a.fmtMoney(v, signed);
    if (!isNum(v)) return "—";
    var sign = v < 0 ? "-" : (signed && v > 0 ? "+" : ""), x = Math.abs(v);
    if (x >= 1e9) return sign + "£" + (x / 1e9).toFixed(2) + "bn";
    if (x >= 1e6) return sign + "£" + (x / 1e6).toFixed(1) + "m";
    if (x >= 1e3) return sign + "£" + Math.round(x / 1e3) + "k";
    return sign + "£" + Math.round(x).toLocaleString("en-GB");
  }
  // MoneyApp has no exact formatter: £4,115 style, for per-pupil figures.
  function fmtExact(v, signed) {
    if (!isNum(v)) return "—";
    var sign = v < 0 ? "-" : (signed && v > 0 ? "+" : "");
    return sign + "£" + Math.round(Math.abs(v)).toLocaleString("en-GB");
  }
  function fmtPupils(n) {
    if (!isNum(n)) return "—";
    return (Math.round(n * 10) / 10).toLocaleString("en-GB", { maximumFractionDigits: 1 });
  }
  function fmtPct(n) {
    if (!isNum(n)) return "—";
    return (Math.round(n * 10) / 10).toLocaleString("en-GB", { maximumFractionDigits: 1 }) + "%";
  }
  function fmtUnit(v, unit) {
    if (unit === "£ per pupil") return fmtExact(v);
    if (unit === "£") return fmtMoney(v);
    if (unit === "%") return fmtPct(v);
    return fmtPupils(v);
  }
  function round(v) { return isNum(v) ? Math.round(v) : null; }
  function perPupil(v, pupils) { return isNum(v) && isNum(pupils) && pupils > 0 ? v / pupils : null; }
  function both(pp, v, compact) {
    if (isNum(pp)) return fmtExact(pp) + " per pupil" + (isNum(v) ? " (" + fmtMoney(v) + (compact ? ")" : " in total)") : "");
    return fmtMoney(v);
  }
  function pages(p) {
    var list = (Array.isArray(p) ? p : [p]).filter(isNum);
    if (!list.length) return "";
    if (list.length === 1) return "IFS p." + list[0];
    var run = list.every(function (n, i) { return i === 0 || n === list[i - 1] + 1; });
    return "IFS pp." + (run ? list[0] + "–" + list[list.length - 1] : list.join(", "));
  }
  function charityUrl(n) {
    var d = /^\s*(\d+)/.exec(String(n == null ? "" : n));
    return d ? CHARITY_PAGE[0] + d[1] + CHARITY_PAGE[1] : REGISTER_HOME;
  }
  // phrasing.ratio_words (contract C1): a / b in words that sit before a noun phrase ("about double the median"),
  // or null when either value is missing, not a number, zero or negative. data/phrasing_cases.json is the shared table.
  function ratioWords(a, b) {
    if (!isNum(a) || !isNum(b) || a <= 0 || b <= 0) return null;
    var r = a / b;
    if (r >= 2.75) return "about " + Math.max(3, Math.round(r)) + " times";
    if (r >= 2.25) return "about two and a half times";
    if (r >= 1.75) return "about double";
    if (r >= 1.42) return "about half as much again as";
    if (r >= 1.29) return "about a third more than";
    if (r > 1.15) return "about a quarter more than";
    if (r > 1.05) return "a little more than";
    if (r >= 0.95) return "about the same as";
    if (r >= 0.85) return "a little less than";
    if (r >= 0.71) return "about three-quarters of";
    if (r >= 0.58) return "about two-thirds of";
    if (r >= 0.42) return "about half";
    if (r >= 0.29) return "about a third of";
    if (r >= 0.21) return "about a quarter of";
    return "under a quarter of";
  }
  // The school year (September to August) a PTA return ends in, as series.pta_year counts it for every school,
  // and the words every PTA figure leads with: "2024-25" is "the year to Aug 2025".
  function ptaYearWords(y) {
    var d = /^(\d{4})-\d{2}$/.exec(String(y || ""));
    return d ? "year to Aug " + (+d[1] + 1) : String(y || "");
  }
  function fileSafe(s) { return String(s || SITE).replace(/[\\/:*?"<>|]+/g, "-").replace(/\s+/g, " ").trim(); }
  function plural(n, one, many) { return n + " " + (n === 1 ? one : (many || one + "s")); }

  // ======================================================================
  // The one adapter: every field read from /data/s, /data/sx and /data/a happens here.
  // ======================================================================
  function adapt(s, sx, council, england) {
    s = isObj(s) ? s : null;
    sx = isObj(sx) ? sx : null;
    function n(v) {
      if (isNum(v)) return v;
      if (typeof v === "string" && v.trim() !== "" && isFinite(Number(v))) return Number(v);
      return null;
    }
    function str(v) { return v == null ? null : String(v); }
    function status(st, label, reason, year) {
      var key = isObj(st) ? st.status : st;
      if (!key || ORDER.indexOf(key) === -1) return null;
      return {
        key: key, label: (isObj(st) && st.label) || label || LABELS[key], icon: ICONS[key],
        reason: (isObj(st) && st.reason) || reason || "", year: (isObj(st) && st.year) || year || null
      };
    }
    function flags(f) {
      var out = {};
      function add(y, t) {
        if (y == null || y === "") return;
        y = String(y);
        t = t ? String(t) : "";
        if (!(y in out)) out[y] = t;
        else if (t && out[y].indexOf(t) === -1) out[y] = out[y] ? out[y] + "; " + t : t;
      }
      function text(x) { return typeof x === "string" ? x : isObj(x) ? (x.text || x.code || "") : ""; }
      if (Array.isArray(f)) {
        f.forEach(function (x) {
          if (typeof x === "string" || isNum(x)) add(x, "");
          else if (isObj(x)) add(x.year || x.y, text(x));
        });
      } else if (isObj(f)) {
        // series.py writes suspect as {year: [keys]}: only a year with at least one key is marked.
        Object.keys(f).forEach(function (y) {
          var list = Array.isArray(f[y]) ? f[y] : f[y] == null || f[y] === false ? [] : [f[y]];
          list.forEach(function (x) { add(y, text(x)); });
        });
      }
      return out;
    }
    function area(a) {
      if (!isObj(a)) return { ok: false };
      var A = isObj(a.area) && !a.by_year ? a.area : a;
      var ALIASES = {
        schools: ["schools"], inDeficit: ["in_deficit"], inDeficitPct: ["in_deficit_pct"], heading: ["heading", "heading_for_deficit"],
        deficitTotal: ["deficit_total"], deficitPp: ["deficit_pp"], reservePp: ["reserve_median_pp", "reserve_pp_median"],
        incomePp: ["income_pp_median", "income_median_pp"], spendPp: ["spend_pp_median", "spend_median_pp", "expenditure_pp_median"],
        grantPp: ["grant_pp_median", "gov_pp_median", "grants_pp_median"], ptaPp: ["pta_pp_median", "pta_median_pp"],
        ptaSchools: ["pta_schools"], donationsPp: ["donations_pp_median", "donations_median_pp"], fsmPct: ["fsm_pct", "fsm_pct_median"],
        ptaBands: ["pta_pp_median_by_band", "pta_band_medians", "pta_median_pp_by_band"]
      };
      function stats(S) {
        var out = {};
        Object.keys(ALIASES).forEach(function (k) {
          out[k] = null;
          if (!isObj(S)) return;
          for (var i = 0; i < ALIASES[k].length; i++) {
            var v = S[ALIASES[k][i]];
            if (k === "ptaBands" ? isObj(v) : n(v) != null) { out[k] = k === "ptaBands" ? v : n(v); break; }
          }
        });
        return out;
      }
      var id = str(a.id) || "";
      var type = a.type || (id === "england" ? "england" : (id.split("-")[0] || "area"));
      var byYear = isObj(A.by_year) ? A.by_year : {};
      var by = {}, years = {};
      Object.keys(byYear).forEach(function (y) {
        years[y] = 1;
        by[y] = {};
        ["all", "council-run", "academy"].forEach(function (g) { by[y][g] = stats((byYear[y] || {})[g]); });
      });
      var pupils = {}, schools = {}, dsg = {};
      Object.keys(isObj(A.pupils_by_year) ? A.pupils_by_year : {}).forEach(function (y) { years[y] = 1; pupils[y] = n(A.pupils_by_year[y]); });
      Object.keys(isObj(A.schools_by_year) ? A.schools_by_year : {}).forEach(function (y) { years[y] = 1; schools[y] = n(A.schools_by_year[y]); });
      Object.keys(isObj(A.dsg) ? A.dsg : {}).forEach(function (y) {
        var d = A.dsg[y];
        dsg[y] = isObj(d) ? { balance: n(d.balance), pp: n(d.per_pupil), provisional: d.provisional === true || d.status === "provisional" } : { balance: n(d), pp: null, provisional: false };
      });
      var pta = isObj(A.pta) ? A.pta : (isObj(a.pta) ? a.pta : null);
      var bands = null;
      if (pta && isObj(pta.by_band || pta.bands)) bands = pta.by_band || pta.bands;
      var statuses = {};
      var sl = isObj(A.statuses_latest) ? A.statuses_latest : {};
      Object.keys(sl).forEach(function (k) { if (n(sl[k]) != null) statuses[k] = n(sl[k]); });
      return {
        ok: true, id: id, type: type, name: str(a.name || A.name) || "This area", path: str(a.path),
        years: Object.keys(years).sort(), by: by, pupils: pupils, schools: schools, dsg: dsg,
        statuses: statuses, ptaBands: bands, ptaGap: pta ? (pta.gap != null ? pta.gap : null) : null,
        ptaText: pta && typeof pta.text === "string" ? pta.text : null, ptaYear: pta ? str(pta.year) : null,
        combinedLast: str(a.combined_last_year || A.combined_last_year)
      };
    }

    var m = { ok: !!s, urn: null, name: null, rows: [], flagged: {}, pta: [], area: area(council), england: area(england),
      siteFlags: {}, notReported: {}, nearby: null, similarSchools: [], phaseKey: "" };
    if (!s) return m;
    var c = isObj(s.council) ? s.council : {};
    var tags = isObj(s.tags) ? s.tags : {};
    var trust = isObj(s.trust) ? s.trust.name : s.trust;
    m.urn = str(s.urn);
    m.name = str(s.name) || "School " + m.urn;
    m.path = str(s.path);
    m.council = { code: c.code != null ? String(c.code) : null, name: str(c.name), path: str(c.path) };
    m.academy = !!s.academy || tags.governance === "academy" || tags.governance === "free school";
    m.trust = trust ? String(trust) : null;
    m.governance = tags.governance || (m.academy ? "academy" : "council-run");
    m.overseer = m.academy ? (m.trust || "the trust") : "the council";
    m.phase = str(s.phase || tags.phase || (sx && sx.phase));
    m.phaseKey = (m.phase || "").toLowerCase();
    m.band = n(s.band);
    m.status = status(s.status, s.label, s.reason, s.year);
    m.year = str(s.year);
    m.streak = n(s.streak) || 0;
    m.pp = {};
    m.similar = {};
    Object.keys(isObj(s.pp) ? s.pp : {}).forEach(function (k) { if (n(s.pp[k]) != null) m.pp[k] = n(s.pp[k]); });
    Object.keys(isObj(s.similar) ? s.similar : {}).forEach(function (k) { if (n(s.similar[k]) != null) m.similar[k] = n(s.similar[k]); });
    var il = isObj(s.income_lines) ? s.income_lines : {};
    m.incomeLines = {
      grant_funding: n(il.grant_funding), sen_funding: n(il.sen_funding), pupil_premium: n(il.pupil_premium),
      self_generated: n(il.self_generated_income != null ? il.self_generated_income : il.self_generated),
      donations_revenue: n(il.donations_revenue)
    };
    m.pupilsLatest = n(s.pupils);
    // School Money's similar schools (contract C2): one stated year and the number of schools with a return that year.
    var sm = isObj(s.similar_meta) ? s.similar_meta : null;
    m.similarMeta = sm && str(sm.year) ? { year: str(sm.year), peers: n(sm.peers), method: str(sm.method) } : null;
    // The reserve basis series.py shows in every year (contract C3): 'own', or 'incl_trust_share' for an academy whose
    // published status counts its share of the trust's reserve. Without it, the older per-year handling below applies.
    var basis = (sx && sx.reserve_basis) || s.reserve_basis;
    m.reserveBasis = basis === "own" || basis === "incl_trust_share" ? basis : null;
    // series.py writes source as {year: "CFR" | "AAR"}; older documents carry one string.
    var sxSource = sx ? sx.source : null, sourceByYear = {};
    if (isObj(sxSource)) {
      Object.keys(sxSource).forEach(function (y) { if (sxSource[y]) sourceByYear[y] = /AAR/i.test(String(sxSource[y])) ? "AAR" : "CFR"; });
      var sourceYears = Object.keys(sourceByYear).sort();
      sxSource = sourceYears.length ? sourceByYear[sourceYears[sourceYears.length - 1]] : null;
    }
    var src = str(sxSource || s.source) || (m.academy ? "AAR" : "CFR");
    m.sourceKey = /AAR/i.test(src) ? "AAR" : "CFR";
    m.source = "DfE " + m.sourceKey + " return";
    // Each year's own return (a school that converted has CFR years, then AAR years): see srcOf().
    m.sourceByYear = sourceByYear;
    m.sx = !!(sx && isObj(sx.m));

    // Yearly rows: labels from sx.years, else s.years[].y; metrics from sx.m, else the s.years fields.
    var sYears = Array.isArray(s.years) ? s.years.filter(isObj) : [];
    var sByYear = {};
    sYears.forEach(function (r) { if (r.y) sByYear[String(r.y)] = r; });
    var labels = sx && Array.isArray(sx.years) && sx.years.length ? sx.years.map(String) : sYears.map(function (r) { return String(r.y); });
    // series.py writes {falling_rolls, pass_through, high_send, suspect: {year: [keys]}, not_reported}; older
    // documents carry the marked years alone (a list, or an object keyed by year).
    var rawFlags = sx && sx.flags;
    if (isObj(rawFlags) && ["suspect", "falling_rolls", "pass_through", "high_send", "not_reported"].some(function (k) { return k in rawFlags; })) {
      ["falling_rolls", "pass_through", "high_send"].forEach(function (k) { if (isObj(rawFlags[k])) m.siteFlags[k] = rawFlags[k]; });
      if (isObj(rawFlags.not_reported)) m.notReported = rawFlags.not_reported;
      rawFlags = rawFlags.suspect;
    }
    var flagged = flags(rawFlags);
    m.flagged = flagged;
    var sxm = m.sx ? sx.m : {};
    var sxp = sx && isObj(sx.pupils) ? sx.pupils : {};
    m.rows = labels.filter(function (y, i) { return y && labels.indexOf(y) === i; }).map(function (y) {
      var sr = sByYear[y] || {};
      var pupils = n(sxp[y]);
      if (pupils == null) pupils = n(sr.pupils);
      var row = { y: y, pupils: pupils, suspect: y in flagged, flag: flagged[y] || "", metrics: {}, status: str(sr.status) };
      METRICS.forEach(function (k) {
        var src = isObj(sxm[SX_NAMES[k]]) ? sxm[SX_NAMES[k]] : sxm[k];
        var cell = isObj(src) ? src[y] : null;
        var v = null, pp = null, r = null, rpp = null;
        if (isObj(cell)) { v = n(cell.v); pp = n(cell.pp); r = n(cell.r); rpp = n(cell.rpp); } else if (n(cell) != null) v = n(cell);
        // With reserve_basis, a year /data/sx leaves out has no reserve on that basis: /data/s never fills it in.
        if (v == null && S_FALLBACK[k] && !(k === "revenue_reserve" && m.reserveBasis && m.sx)) v = n(sr[S_FALLBACK[k]]);
        if (pp == null) pp = perPupil(v, pupils);
        if (v != null || pp != null) row.metrics[k] = { v: v, pp: pp, r: r, rpp: rpp };
      });
      // An academy's status (status.py, /data/s) counts its share of the trust's central reserve where the DfE
      // publishes one. With reserve_basis, /data/sx revenue_reserve is already on that basis in every year (and
      // revenue_reserve_own, when present, is the academy's own figure for the note). Without it, /data/sx keeps the
      // academy's own reserve, so the /data/s figure stands in year by year and the own figure is kept for the note.
      var own = row.metrics.revenue_reserve, incl = n(sr.reserve);
      if (m.reserveBasis) {
        if (m.reserveBasis === "incl_trust_share" && own) {
          row.trustShare = true;
          row.basisWords = ", including its share of the trust's reserve";
          var ownCell = isObj(sxm.revenue_reserve_own) ? sxm.revenue_reserve_own[y] : null;
          var ownV = isObj(ownCell) ? n(ownCell.v) : n(ownCell);
          if (ownV != null) row.reserveOwn = ownV;
        }
      } else if (m.academy && incl != null && own && isNum(own.v) && Math.abs(incl - own.v) > 1) {
        row.metrics.revenue_reserve = { v: incl, pp: perPupil(incl, pupils), r: null, rpp: null };
        row.trustShare = true;
        row.reserveOwn = own.v;
      }
      return row;
    });
    m.trustShare = m.rows.some(function (r) { return r.trustShare; });

    // Parents' associations: register history from /data/s, per-pupil figures from sx.pta where given.
    var sxPta = sx && isObj(sx.pta) ? sx.pta : {};
    var rowPupils = {}, rowMarked = {};
    m.rows.forEach(function (r) { rowPupils[r.y] = r.pupils; rowMarked[r.y] = r.suspect; });
    // pta.attach_history writes period_end as YYYY-MM; older rows carry YYYY-MM-DD. One rule for every school, as
    // series.pta_year and the area medians count it: a return sits in the school year (September to August) its
    // accounts end in, so a return to August 2025 is 2024-25 for a council-run school and an academy alike.
    function charityEnd(end) {
      var d = /^(\d{4})-(\d{2})(?:-(\d{2}))?/.exec(String(end || ""));
      if (!d || +d[2] < 1 || +d[2] > 12) return null;
      var y = +d[1], month = MONTHS[+d[2] - 1], day = d[3] ? +d[3] + " " : "";
      return { year: y, month: +d[2], iso: d[1] + "-" + d[2], end: day + month.slice(0, 3) + " " + y, fye: day + month };
    }
    function ptaSchoolYear(e) {
      var start = e.month >= 9 ? e.year : e.year - 1;
      return start + "-" + String(start + 1).slice(2);
    }
    var charities = (Array.isArray(s.pta) ? s.pta : []).filter(function (p) { return isObj(p) && !p.review; });
    m.pta = charities.map(function (p) {
      var num = str(p.charity_number);
      // One entry per school year, as series._pta and the area medians count it: a return listed twice counts once,
      // and distinct returns ending in the same school year (an association moving its year end files two) are added.
      var returns = {}, slots = {};
      (Array.isArray(p.history) ? p.history : []).forEach(function (h) {
        if (!isObj(h) || !charityEnd(h.period_end)) return;
        if (n(h.income) == null && n(h.expenditure != null ? h.expenditure : h.spend) == null) return;
        returns[String(h.period_end)] = h;
      });
      Object.keys(returns).forEach(function (key) {
        var h = returns[key], ce = charityEnd(key), y = ptaSchoolYear(ce);
        var income = n(h.income), spend = n(h.expenditure != null ? h.expenditure : h.spend);
        var e = slots[y] || (slots[y] = { y: y, ends: [], income: null, spend: null });
        e.ends.push(ce);
        if (income != null) e.income = (e.income || 0) + income;
        if (spend != null) e.spend = (e.spend || 0) + spend;
      });
      var years = Object.keys(slots).sort().map(function (y) {
        var e = slots[y];
        e.ends.sort(function (a, b) { return a.iso < b.iso ? -1 : a.iso > b.iso ? 1 : 0; });
        var latest = e.ends[e.ends.length - 1];
        e.end = latest.end; e.month = latest.month; e.iso = latest.iso; e.fye = latest.fye;
        return e;
      });
      var fye = years.length ? years[years.length - 1].fye : null;
      if (!years.length) {
        Object.keys(sxPta).sort().forEach(function (y) {
          var e = sxPta[y];
          if (isObj(e) && (!e.charity_number || String(e.charity_number) === num || charities.length === 1)) {
            years.push({ y: y, ends: [], end: null, month: null, iso: "", income: n(e.income), spend: n(e.spend) });
          }
        });
      }
      var confidence = isObj(p.match) && (p.match.method === "llm" || p.match.confidence === "medium") ? "medium" : null;
      years.forEach(function (e) {
        var x = sxPta[e.y];
        // sx.pta is the producer's row for the same school year; it describes this return when charity and income agree.
        var same = isObj(x) && (!x.charity_number || String(x.charity_number) === num) && (n(x.income) == null || e.income == null || Math.abs(n(x.income) - e.income) < 1);
        // A school year marked as unusual may have a wrong pupil count, so no per-pupil figure is made from it.
        e.pupilsMarked = !!rowMarked[e.y];
        e.pupils = isNum(rowPupils[e.y]) && rowPupils[e.y] > 0 ? rowPupils[e.y] : null;
        // Per pupil is this return's own total over the SAME school year's pupils; the producer's same-year figure
        // stands in only when that year's pupils aren't in the documents.
        function pp(total, given) { return e.pupilsMarked ? null : e.pupils ? perPupil(total, e.pupils) : same && n(given) != null ? n(given) : null; }
        e.incomePp = pp(e.income, x && x.income_pp);
        e.spendPp = pp(e.spend, x && (x.spend_pp != null ? x.spend_pp : x.expenditure_pp));
        if (same && x.confidence === "medium") confidence = "medium";
      });
      var partB = [], pb = isObj(p.part_b) ? p.part_b : isObj(p.breakdown) ? p.breakdown : {};
      Object.keys(pb).sort().forEach(function (y) {
        var lines = isObj(pb[y]) ? (pb[y].expenditure_lines || pb[y].spend_lines) : null;
        if (!isObj(lines)) return;
        var list = Object.keys(lines).filter(function (k) { return n(lines[k]) != null; }).map(function (k) { return [k, n(lines[k])]; })
          .sort(function (a, b) { return b[1] - a[1]; });
        if (list.length) partB.push({ y: y, lines: list });
      });
      return { number: num, name: str(p.name) || "Parents' association", status: str(p.status), latestIncome: n(p.latest_income), fye: fye, years: years,
        confidence: confidence, partB: partB };
    }).sort(function (a, b) { return (b.latestIncome || 0) - (a.latestIncome || 0); });
    m.gap = sx && sx.gap != null ? sx.gap : null;
    m.trustCentralPp = n(sx && sx.trust_central_pp);
    m.similarSchools = (Array.isArray(s.similar_schools) ? s.similar_schools : []).filter(function (x) { return isObj(x) && x.name; })
      .map(function (x) { return { name: String(x.name), urn: str(x.urn), p: str(x.p || x.path) }; });
    m.nearby = nearbyOf(s.nearby);
    return m;

    // The 'nearby' block (see the shared contract): any field may be missing, and a missing value stays missing.
    function nearbyRow(r, self) {
      if (!isObj(r)) return null;
      var out = { urn: str(r.urn), name: str(r.name) || (self ? m.name : null), p: str(r.p), mi: n(r.mi), academy: r.academy === true,
        status: ORDER.indexOf(r.status) !== -1 ? r.status : null, pta_year: str(r.pta_year), pta_lower: r.pta_confidence === "medium", lines: {} };
      if (!out.name) return null;
      // A federation lead's combined return (contract C5): its figures are the whole federation's, never one school's.
      if (typeof r.federation === "string") out.federation = r.federation.trim() || "federation";
      ["pupils", "spend_pp", "income_pp", "gov_pp", "reserve_pp", "staff_pct", "pta_pp", "fsm_pct"].forEach(function (k) { if (n(r[k]) != null) out[k] = n(r[k]); });
      if (isObj(r.lines)) SPEND_LINES.forEach(function (l) { if (n(r.lines[l[0]]) != null) out.lines[l[0]] = n(r.lines[l[0]]); });
      return out;
    }
    function nums(o) {
      var out = {};
      Object.keys(isObj(o) ? o : {}).forEach(function (k) { if (n(o[k]) != null) out[k] = n(o[k]); });
      return out;
    }
    function nearbyOf(nb) {
      if (!isObj(nb)) return null;
      var rank = {};
      Object.keys(isObj(nb.rank) ? nb.rank : {}).forEach(function (k) {
        var r = nb.rank[k];
        if (isObj(r) && n(r.rank) != null && n(r.of) != null) rank[k] = { rank: n(r.rank), of: n(r.of) };
      });
      return { year: str(nb.year), phase: str(nb.phase), radius: n(nb.radius_mi), self: nearbyRow(nb.self, true),
        schools: (Array.isArray(nb.schools) ? nb.schools : []).map(function (r) { return nearbyRow(r, false); }).filter(Boolean),
        medians: nums(nb.medians), rank: rank, lineMedians: nums(nb.line_medians) };
    }
  }

  // ======================================================================
  // Model helpers
  // ======================================================================
  function ctxOf(ctx) {
    ctx = isObj(ctx) ? ctx : {};
    return {
      framings: isObj(ctx.framings) ? ctx.framings : {}, questions: isObj(ctx.questions) ? ctx.questions : {},
      lines: isObj(ctx.context_lines) ? ctx.context_lines : {}, cite: ctx.cite || "IFS, Annual report on education spending in England: 2025–26 (January 2026)",
      url: ctx.url || "", realLabel: ctx.real_label || null, dsgNote: ctx.dsg_note || null,
      links: isObj(ctx.links) ? ctx.links : {}, notInReport: Array.isArray(ctx.not_in_report) ? ctx.not_in_report : [],
      today: ctx.today || null, raw: ctx
    };
  }
  // The IFS's all-age £8,400 per pupil is not a school-level comparator (schools compare with £7,000 primary or
  // £7,800 secondary), so that sentence and its pointer are left out wherever a framing is quoted, as on school pages.
  function framingText(text) {
    var parts = String(text).split(/\.\s+/);
    return parts.map(function (s, i) { return i < parts.length - 1 ? s + "." : s; })
      .filter(function (s) { return s.indexOf("8,400") === -1 && s.indexOf("Compare a school with") !== 0; }).join(" ");
  }
  function framing(c, key) {
    var f = c.framings[key];
    if (!f || !f.text) return "";
    var p = pages(f.pages);
    return framingText(f.text) + (p ? " (" + p + ")" : "");
  }
  function framingSource(c, key) {
    var f = c.framings[key];
    return f && f.pages ? c.cite + ", " + pages(f.pages) : null;
  }
  function ctxLine(c, group, id) {
    var list = Array.isArray(c.lines[group]) ? c.lines[group] : [];
    for (var i = 0; i < list.length; i++) {
      if (list[i] && list[i].id === id && list[i].text) return { text: list[i].text + (list[i].page ? " (" + pages(list[i].page) + ")" : ""), page: list[i].page };
    }
    return null;
  }
  function ifsSource(c, p) { return c.cite + (pages(p) ? ", " + pages(p) : "") + (c.url ? ": " + c.url : ""); }
  function slide(id, kind, title) {
    return { id: id, kind: kind, title: title, lead: "", bullets: [], figures: [], chart: null, note: "", notes: "", sources: [], links: [] };
  }
  function figText(f) {
    var main;
    if (f.unit === "pupils") main = fmtPupils(f.v) + " pupils";
    else if (f.unit === "%") main = fmtPct(f.v);
    else if (f.unit === "count") main = String(f.v);
    else main = both(f.pp, f.v);
    if (isNum(f.share)) main += ", " + Math.round(f.share * 100) + "% of spending";
    return main + (f.year ? ", " + f.year : "") + (f.source ? ", " + f.source : "");
  }
  function figure(key, label, v, pp, year, source, unit, extra) {
    unit = unit || "£";
    var f = {
      key: key, label: label, unit: unit, year: year || null, source: source || null,
      v: isNum(v) ? (unit === "£" ? Math.round(v) : Math.round(v * 10) / 10) : null, pp: isNum(pp) ? Math.round(pp) : null
    };
    if (extra) Object.keys(extra).forEach(function (k) { f[k] = extra[k]; });
    f.text = figText(f);
    return f;
  }
  function chartAlt(chart) {
    var kind = chart.type === "line" ? "Line chart" : chart.type === "stack" ? "Stacked bar chart" : "Bar chart";
    var parts = chart.series.map(function (s) {
      return s.name + ": " + s.points.map(function (p) { return p.y + " " + fmtUnit(p.v, chart.unit) + (p.suspect ? " (marked)" : ""); }).join(", ");
    });
    return kind + ", " + chart.unit + ". " + parts.join(". ") + ".";
  }
  function chart(type, unit, series) {
    series = series.filter(function (s) { return s.points.some(function (p) { return isNum(p.v); }); });
    if (!series.length) return null;
    var c = { type: type, unit: unit, series: series };
    c.alt = chartAlt(c);
    return c;
  }
  function metric(row, key) { return row && row.metrics[key] ? row.metrics[key] : null; }
  function points(m, key, field) {
    return m.rows.map(function (r) {
      var c = metric(r, key);
      return { y: r.y, v: c ? round(field === "pp" ? c.pp : c.v) : null, suspect: r.suspect };
    });
  }
  function latestRow(m, key) {
    for (var i = m.rows.length - 1; i >= 0; i--) {
      var c = metric(m.rows[i], key);
      if (c && isNum(c.v) && !m.rows[i].suspect) return m.rows[i];
    }
    return null;
  }
  function firstRow(m, key) {
    for (var i = 0; i < m.rows.length; i++) {
      var c = metric(m.rows[i], key);
      if (c && isNum(c.v) && !m.rows[i].suspect) return m.rows[i];
    }
    return null;
  }
  function suspectYear(m, y) { return y != null && Object.prototype.hasOwnProperty.call(m.flagged, y); }
  // The return a year's figures come from: that year's own source in /data/sx, else the school's latest.
  function srcOf(m, y) {
    var k = y != null && m.sourceByYear && m.sourceByYear[y] ? m.sourceByYear[y] : m.sourceKey;
    return "DfE " + k + " return";
  }
  function lastTrusted(m, test) {
    for (var i = m.rows.length - 1; i >= 0; i--) { if (!m.rows[i].suspect && (!test || test(m.rows[i]))) return m.rows[i]; }
    return null;
  }
  // /data/s pp, similar and income_lines describe one year: s.year, or the latest row when s.year is missing.
  function snapshotYear(m) { return m.year || (m.rows.length ? m.rows[m.rows.length - 1].y : null); }
  // The snapshot only stands in for the year it describes, and never for a marked year.
  function snapshotFor(m, y) { var sy = snapshotYear(m); return sy === y && !suspectYear(m, sy); }
  // The year /data/s similar medians describe: similar_meta's stated year (contract C2), else the snapshot year.
  function simYear(m) { return (m.similarMeta && m.similarMeta.year) || snapshotYear(m); }
  // "School Money's similar schools (17 schools, 2025-26)" when the build says how many there were; else "similar schools".
  function simWords(m) {
    var sm = m.similarMeta;
    return sm && isNum(sm.peers) && sm.peers > 0 ? "School Money's similar schools (" + plural(sm.peers, "school") + ", " + sm.year + ")" : "similar schools";
  }
  // "a little more than the median (£8,100)": the ratio in words when both are positive, else the plain figure.
  function againstMedian(mine, median, what) {
    var w = ratioWords(mine, median);
    return w ? w + " " + what + " (" + fmtExact(median) + ")" : "against " + what + " of " + fmtExact(median);
  }
  // Why a slide has no headline: nothing published, or only years marked as unusual.
  function noHeadline(m, key, what) {
    var marked = m.rows.some(function (r) { var c = metric(r, key); return r.suspect && c && isNum(c.v); });
    return marked ? what + " are only published for years marked as unusual, so the chart shows them marked and none is used as a headline."
      : what + " aren't published yet.";
  }
  function suspectNote(m) {
    var marked = m.rows.filter(function (r) { return r.suspect; });
    if (!marked.length) return "";
    return marked.map(function (r) {
      return MARK + " " + r.y + " is marked: its published figures look unusual" + (r.flag ? " (" + r.flag + ")" : "") + ".";
    }).join(" ") + " Marked years are shown but never used for headline figures.";
  }
  function yearSpan(m) {
    var ys = m.rows.map(function (r) { return r.y; });
    return ys.length ? (ys.length > 1 ? ys[0] + " to " + ys[ys.length - 1] : ys[0]) : "";
  }
  // "DfE CFR returns, 2018-19 to 2020-21; DfE AAR returns, 2021-22 to 2024-25" for a school that converted.
  function sourceSpan(m) {
    var runs = [];
    m.rows.forEach(function (r) {
      var k = srcOf(m, r.y), last = runs[runs.length - 1];
      if (last && last.k === k) last.to = r.y; else runs.push({ k: k, from: r.y, to: r.y });
    });
    if (runs.length < 2) return m.source.replace("return", "returns") + (yearSpan(m) ? ", " + yearSpan(m) : "");
    return runs.map(function (x) { return x.k.replace("return", "returns") + ", " + (x.from === x.to ? x.from : x.from + " to " + x.to); }).join("; ");
  }
  function schoolSources(m, c) {
    var out = [sourceSpan(m) + " (DfE Financial Benchmarking and Insights Tool data)"];
    if (m.path) out.push(SITE + " page: " + (c.links.base || "") + m.path);
    return out;
  }
  function dsgDenominator(y) {
    return "The " + DSG_NAME + " per pupil divides the council's balance by the pupils at the council's schools on this site in " + y + ".";
  }
  function areaGroup(m) { return m.academy ? "academy" : "council-run"; }
  function areaStat(A, year, group, key) {
    if (!A || !A.ok || !A.by[year]) return null;
    var g = A.by[year][group];
    if (g && g[key] != null) return { v: g[key], group: group };
    g = A.by[year].all;
    return g && g[key] != null ? { v: g[key], group: "all" } : null;
  }
  function groupWords(group, name) {
    if (group === "council-run") return "council-run schools in " + name;
    if (group === "academy") return "academies in " + name;
    return "schools in " + name;
  }
  function messageDeck(title, message, links) {
    var sl = slide("message", "message", title);
    sl.lead = message;
    sl.links = links || [{ text: "Search for a school", href: "/search/" }, { text: "Browse councils", href: "/council/" }];
    return { title: title, filename: fileSafe(title) + " - " + SITE + ".pptx", message: message, slides: [sl] };
  }
  // Data that couldn't be loaded is named on the first slide, so print and PowerPoint keep the warning.
  function withWarnings(deck, warnings) {
    var list = (Array.isArray(warnings) ? warnings : []).filter(Boolean);
    if (list.length && deck && deck.slides && deck.slides.length) deck.slides[0].bullets = deck.slides[0].bullets.concat(list);
    return deck;
  }
  function sourcesSlide(slides, c, extra) {
    var sl = slide("sources", "sources", "Sources");
    var seen = {};
    slides.forEach(function (x) { x.sources.forEach(function (s) { if (!seen[s]) { seen[s] = 1; sl.bullets.push(s); } }); });
    (extra || []).forEach(function (s) { if (s && !seen[s]) { seen[s] = 1; sl.bullets.push(s); } });
    sl.lead = "Every figure in this presentation comes from published open data, shown as it was filed.";
    sl.note = SITE + " shows published figures as a starting point for a conversation with a school, not a verdict on it. Figures are in cash unless they say otherwise.";
    sl.links = [{ text: "How the figures are worked out", href: "/about/" }];
    if (c.url) sl.links.push({ text: c.cite, href: c.url });
    sl.sources = sl.bullets.slice();
    return sl;
  }

  // ======================================================================
  // Packs: shared helpers (dates, ratings, tables, saved notes and actions)
  // ======================================================================
  var PACKS = {
    governors: { label: "Governors' finance pack", meeting: "Governors' finance committee", file: "Governors finance pack" },
    ptfa: { label: "PTFA pack", meeting: "PTFA committee meeting", file: "PTFA pack" },
    review: { label: "School review pack", meeting: "School financial review", file: "School review pack" }
  };
  // view=school (and no view) is the governors' pack, as links made before the packs existed expect.
  var VIEWS = { "": "governors", school: "governors", governors: "governors", ptfa: "ptfa", review: "review" };
  function packView(view) {
    var v = String(view == null ? "" : view).trim().toLowerCase();
    return Object.prototype.hasOwnProperty.call(VIEWS, v) ? VIEWS[v] : null;
  }
  // Ratings always carry an icon and a word; the colour (tone) only repeats them. Red, amber and green reuse
  // the status icons of the same colour, so a ▼ is always the red end and a ✓ the green.
  var RAG = {
    red: { icon: "▼", word: "Needs attention", tone: "critical" },
    amber: { icon: "●", word: "Worth watching", tone: "warning" },
    green: { icon: "✓", word: "On track", tone: "good" }
  };
  var TONES = { in_deficit: "critical", heading_for_deficit: "serious", tight: "warning", healthy: "good", large_reserves: "plenty", reserve_held_by_trust: "held" };
  var ORDINAL_WORDS = ["", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth"];
  var NOTES_PREFIX = "moneyDeck:";

  function ordinal(n) {
    var s = ["th", "st", "nd", "rd"], v = n % 100;
    return n + (s[(v - 20) % 10] || s[v] || s[0]);
  }
  function fmtDate(value) {
    if (value instanceof Date && !isNaN(value.getTime())) return value.getDate() + " " + MONTHS[value.getMonth()] + " " + value.getFullYear();
    var d = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value || ""));
    if (d && +d[2] >= 1 && +d[2] <= 12) return (+d[3]) + " " + MONTHS[+d[2] - 1] + " " + d[1];
    return value ? String(value) : fmtDate(new Date());
  }
  function signedPct(x) { return (x < 0 ? "-" : "+") + Math.round(Math.abs(x) * 100) + "%"; }
  function rag(level, measure, value, why) {
    var g = RAG[level];
    var r = { level: level, icon: g ? g.icon : ICONS[level], word: g ? g.word : LABELS[level], tone: g ? g.tone : TONES[level],
      measure: measure, value: value || "", why: why || "" };
    r.text = r.icon + " " + r.word + " · " + measure + (r.value ? ": " + r.value : "");
    return r;
  }
  function ragCell(r) { return r ? { text: r.icon + " " + r.word, rag: r } : { text: "—" }; }
  function cell(text) { return { text: text == null || text === "" ? "—" : String(text) }; }

  function rowOf(m, y) {
    for (var i = 0; i < m.rows.length; i++) { if (m.rows[i].y === y) return m.rows[i]; }
    return null;
  }
  function trustedRows(m, key) {
    return m.rows.filter(function (r) { var c = metric(r, key); return !r.suspect && c && isNum(c.v); });
  }
  function previousLabel(y) {
    var d = /^(\d{4})-\d{2}$/.exec(String(y || ""));
    return d ? (+d[1] - 1) + "-" + String(+d[1]).slice(2) : null;
  }
  // The latest unbroken run of school years that pass has(), back from the latest unmarked one (at most max):
  // a year that is missing or marked as unusual ends the run, since nothing is known about it.
  function runOfYears(m, has, max) {
    var out = [];
    for (var row = lastTrusted(m, has); row && !row.suspect && has(row) && out.length < (max || Infinity); row = rowOf(m, previousLabel(row.y))) out.unshift(row);
    return out;
  }
  function hasMetric(key) { return function (r) { var c = metric(r, key); return !!(c && isNum(c.v)); }; }
  // How many years in a row, up to the latest unmarked one, pass the test (e.g. a reserve below zero).
  function runBack(m, key, test) {
    var rows = runOfYears(m, hasMetric(key)), n = 0;
    for (var i = rows.length - 1; i >= 0 && test(metric(rows[i], key).v); i--) n++;
    return n;
  }
  // The reserve basis is the published status's (see adapt): for an academy, its share of the trust's reserve is in.
  function trustWords(row) { return row && row.trustShare ? row.basisWords || ", counting its share of the trust's reserve" : ""; }
  function reserveLabel(text, row) { return text + (row && row.trustShare ? row.basisWords || ", counting the trust share" : ""); }
  function trustNote(m) {
    var rows = m.rows.filter(function (r) { return r.trustShare; });
    if (!rows.length) return "";
    var last = rows[rows.length - 1];
    if (m.reserveBasis) {
      var owned = rows.filter(function (r) { return isNum(r.reserveOwn); }), lo = owned[owned.length - 1];
      return "Reserves in every year shown include this academy's share of its trust's reserve, as its published status does" +
        (lo ? "; the academy's own reserve was " + fmtMoney(lo.reserveOwn) + " in " + lo.y : "") + ".";
    }
    return "Reserves " + (rows.length < m.rows.length ? "for " + rows.map(function (r) { return r.y; }).join(", ") + " " : "") +
      "include this academy's share of its trust's central reserve, as its published status does; the academy's own reserve was " +
      fmtMoney(last.reserveOwn) + " in " + last.y + ".";
  }
  function reserveShare(m) {
    var row = latestRow(m, "revenue_reserve");
    if (!row) return null;
    var r = metric(row, "revenue_reserve"), inc = metric(row, "total_income");
    return { row: row, r: r, inc: inc, share: inc && isNum(inc.v) && inc.v > 0 ? r.v / inc.v : null };
  }
  function staffShare(m) {
    var row = latestRow(m, "staff_total");
    var e = row ? metric(row, "total_expenditure") : null;
    if (!row || !e || !isNum(e.v) || e.v <= 0) return null;
    return { row: row, share: metric(row, "staff_total").v / e.v, staff: metric(row, "staff_total"), spend: e };
  }
  // This school's spending beside the similar-schools median: both from the year the median describes.
  function spendVsSimilar(m) {
    var sy = simYear(m);
    if (!sy || suspectYear(m, sy) || !isNum(m.similar.total_expenditure)) return null;
    var row = rowOf(m, sy), c = row ? metric(row, "total_expenditure") : null;
    var mine = c && isNum(c.pp) ? c.pp : sy === snapshotYear(m) ? m.pp.total_expenditure : null;
    return isNum(mine) ? { year: sy, mine: mine, sim: m.similar.total_expenditure, row: row } : null;
  }
  function pupilTrend(m) {
    var withP = m.rows.filter(function (r) { return isNum(r.pupils) && !r.suspect; });
    if (withP.length < 2) return null;
    var p0 = withP[0], p1 = withP[withP.length - 1], change = p1.pupils / p0.pupils - 1;
    var last4 = runOfYears(m, function (r) { return isNum(r.pupils); }, 4);
    var fellEach = last4.length === 4 && last4.every(function (r, i) { return i === 0 || r.pupils < last4[i - 1].pupils; });
    return { first: p0, last: p1, change: change, fellEach: fellEach, falling: change <= -0.05 || fellEach || !!m.siteFlags.falling_rolls };
  }

  // ---------------------------------------------------------------- ratings
  function rateBalance(m) {
    var row = latestRow(m, "in_year_balance");
    if (!row) return null;
    var b = metric(row, "in_year_balance"), inc = metric(row, "total_income");
    var share = inc && isNum(inc.v) && inc.v > 0 ? b.v / inc.v : null;
    var run = runBack(m, "in_year_balance", function (v) { return v < 0; });
    var level = b.v >= 0 ? "green" : (run >= 2 || (share != null && share <= -0.03)) ? "red" : "amber";
    var why = b.v >= 0 ? "Received more than it spent in " + row.y + "."
      : "Spent more than it received in " + row.y + (share != null ? ", by " + Math.round(-share * 100) + "% of the year's income" : "") +
        (run >= 2 ? ", " + run + " years running" : "") + ". One year under 3% is worth watching; 3% or more, or two years running, needs attention.";
    return rag(level, "In-year balance", both(b.pp, b.v, true) + ", " + row.y, why);
  }
  function isHeld(m) { return !!(m.status && m.status.key === HELD); }
  function heldWords(m) {
    return (m.trust || "The trust") + " pools its academies' reserves, so this academy's own reserve is £0: that is how the trust manages its money, not a shortfall";
  }
  function rateReserve(m) {
    var x = reserveShare(m);
    // Held by the trust is its own status, never 'Tight' and never a deficit (contract C4).
    if (isHeld(m)) {
      return rag(HELD, "Reserve", "held by " + (m.trust || "the trust") + (x ? ", " + x.row.y : ""),
        heldWords(m) + ". Ask the trust how much of the pooled reserve is set aside for this school.");
    }
    if (!x || x.share == null) return null;
    var large = m.phaseKey === "secondary" ? 0.05 : 0.08;
    var key = x.share < 0 ? "in_deficit" : x.share < 0.03 ? "tight" : x.share < large ? "healthy" : "large_reserves";
    return rag(key, "Reserve as a share of income",
      both(x.r.pp, x.r.v, true) + trustWords(x.row) + ", " + (x.share < 0 ? "a deficit of " : "") + Math.round(Math.abs(x.share) * 100) + "% of the year's income, " + x.row.y,
      "The site's rule: below zero is in deficit; under 3% of a year's income is tight; 3% to 8% (5% for secondary schools) is healthy; above that is large reserves.");
  }
  // Spending against a comparison: more than 15% (and £100 per pupil) above needs attention, more than 5% (and £25) is worth
  // watching, so a small category isn't flagged for a few pounds.
  function rateAgainst(measure, mine, other, otherWords, year) {
    if (!isNum(mine) || !isNum(other) || other <= 0) return null;
    var d = mine / other - 1, gap = mine - other;
    var level = d > 0.15 && gap >= 100 ? "red" : d > 0.05 && gap >= 25 ? "amber" : "green";
    return rag(level, measure, fmtExact(mine) + " per pupil against " + otherWords + " " + fmtExact(other) + " (" + signedPct(d) + "), " + year,
      "More than 15% and £100 per pupil above the comparison needs attention; more than 5% and £25 above is worth watching; anything less, or below it, is on track. A difference is a reason to ask why, not a judgement.");
  }
  function rateSpendSimilar(m) {
    var x = spendVsSimilar(m);
    return x ? rateAgainst("Spending per pupil against similar schools", x.mine, x.sim, "a median of", x.year) : null;
  }
  function rateSpendNearby(m) {
    var nb = m.nearby;
    if (!nb || !nb.schools.length || !nb.self) return null;
    return rateAgainst("Spending per pupil against " + nearbyWords(nb), nb.self.spend_pp, nb.medians.spend_pp, "a median of", nb.year);
  }
  function rateStaff(m, c) {
    var x = staffShare(m);
    if (!x) return null;
    var p = x.share * 100, line = ctxLine(c, "school", "staff_share");
    return rag(p <= 80 ? "green" : p <= 85 ? "amber" : "red", "Staff costs share", Math.round(p) + "% of spending, " + x.row.y,
      (line ? line.text + " " : "") + "Up to 80% is on track, 80% to 85% worth watching, above 85% needs attention. The DfE staff total leaves out premises and catering staff, so it can read lower than the national figure.");
  }
  function ratePupils(m) {
    var t = pupilTrend(m);
    if (!t) return null;
    return rag(t.falling ? "red" : t.change < -0.01 ? "amber" : "green", "Pupil numbers",
      fmtPupils(t.first.pupils) + " in " + t.first.y + " to " + fmtPupils(t.last.pupils) + " in " + t.last.y + " (" + (t.change < 0 ? "-" : "+") + fmtPct(Math.abs(t.change) * 100) + ")",
      "Funding follows pupils. A fall of 5% or more, or a fall in each of the last three years, needs attention; a smaller fall is worth watching.");
  }
  function lastPta(main) {
    if (!main) return null;
    for (var i = main.years.length - 1; i >= 0; i--) { if (isNum(main.years[i].income)) return main.years[i]; }
    return null;
  }
  function prevPta(main, last) {
    for (var i = main.years.indexOf(last) - 1; i >= 0; i--) { if (isNum(main.years[i].income)) return main.years[i]; }
    return null;
  }
  function ratePtaTrend(main) {
    var last = lastPta(main), prev = last ? prevPta(main, last) : null;
    if (!last || !prev || !(prev.income > 0)) return null;
    var d = last.income / prev.income - 1;
    return rag(d >= 0 ? "green" : d >= -0.1 ? "amber" : "red", "Parents' association income trend",
      fmtExact(last.income) + " in the " + ptaYearWords(last.y) + ", against " + fmtExact(prev.income) + " in the " + ptaYearWords(prev.y) + " (" + signedPct(d) + ")",
      "Rising is on track; a fall of up to 10% is worth watching; a bigger fall needs attention. One-off events can move a single year.");
  }
  function ratePtaAgainst(last, median, words, year) {
    if (!last || !isNum(last.incomePp) || !median || !isNum(median.v) || median.v <= 0) return null;
    // ratioWords has no words for a zero income, so a null phrase alone doesn't mean the years differ.
    var pp = last.incomePp, same = year === last.y, w = same ? ratioWords(pp, median.v) : null;
    return rag(pp >= median.v ? "green" : pp >= median.v / 2 ? "amber" : "red", "Per pupil against " + words,
      w ? fmtExact(pp) + " per pupil in the " + ptaYearWords(last.y) + ", " + w + " the median (" + fmtExact(median.v) + ")"
        : same ? fmtExact(pp) + " per pupil in the " + ptaYearWords(last.y) + ", against a median of " + fmtExact(median.v)
        : fmtExact(pp) + " per pupil (" + ptaYearWords(last.y) + ") against a median of " + fmtExact(median.v) + " (" + ptaYearWords(year) + ", a different year)",
      "At or above the median is on track; at least half of it is worth watching; under half needs attention. What parents can give varies a lot between schools.");
  }

  // ---------------------------------------------------------------- summary messages
  function budgetMessage(m) {
    var x = reserveShare(m);
    if (isHeld(m)) return ICONS[HELD] + " " + LABELS[HELD] + (x ? " at the end of " + x.row.y : "") + ": " + heldWords(m).charAt(0).toLowerCase() + heldWords(m).slice(1);
    if (!x) return m.status ? m.status.icon + " " + m.status.label + (m.status.year ? " (" + m.status.year + ")" : "") : "There isn't a full year of published figures to assess this school's budget yet.";
    var run = runBack(m, "revenue_reserve", function (v) { return v < 0; });
    var pct = x.share != null ? " (" + Math.round(Math.abs(x.share) * 100) + "% of a year's income)" : "";
    if (x.r.v < 0) return "In deficit by " + fmtMoney(-x.r.v) + trustWords(x.row) + pct + " at the end of " + x.row.y + (run >= 2 ? ", the " + (ORDINAL_WORDS[run] || ordinal(run)) + " year running" : "");
    var spentRun = runBack(m, "in_year_balance", function (v) { return v < 0; });
    var r = rateReserve(m);
    return "Holds " + fmtMoney(x.r.v) + " in reserve" + trustWords(x.row) + pct + " at the end of " + x.row.y +
      (spentRun >= 2 ? ", after spending more than it received for " + spentRun + " years running" : r ? ", which the site counts as " + r.word.toLowerCase() : "");
  }
  function spendMessage(m) {
    var x = spendVsSimilar(m), st = staffShare(m);
    var row = x ? null : latestRow(m, "total_expenditure");
    var year = x ? x.year : row ? row.y : null;
    var mine = x ? x.mine : row ? metric(row, "total_expenditure").pp : null;
    if (!isNum(mine)) return st ? "Staff costs are " + Math.round(st.share * 100) + "% of spending (" + st.row.y + ")" : "Spending per pupil isn't published for an unmarked year yet";
    var diff = x ? Math.round(x.mine) - Math.round(x.sim) : null, w = x ? ratioWords(x.mine, x.sim) : null;
    var text = "Spends " + fmtExact(mine) + " per pupil in " + year +
      (diff == null ? "" : w ? ", " + w + " the median of " + simWords(m) + " (" + fmtExact(x.sim) + ")"
        : diff === 0 ? ", the same as similar schools' median" : ", " + fmtExact(Math.abs(diff)) + (diff > 0 ? " more" : " less") + " than similar schools' median");
    if (st && st.row.y === year) text += "; staff costs are " + Math.round(st.share * 100) + "% of spending";
    return text;
  }
  function reserveMessage(m) {
    var rows = trustedRows(m, "revenue_reserve");
    if (rows.length < 2) {
      var t = pupilTrend(m);
      return t ? fmtPupils(t.last.pupils) + " pupils in " + t.last.y + ", " + (t.change < 0 ? "down " : "up ") + fmtPct(Math.abs(t.change) * 100) + " from " + t.first.y
        : "There aren't enough unmarked years yet to show how the reserve has moved";
    }
    // Years with and without the trust share aren't set against each other: a mixed run compares the academy's own reserve.
    var mixed = rows.some(function (r) { return r.trustShare; }) && rows.some(function (r) { return !r.trustShare; });
    function val(r) { return mixed && r.trustShare ? r.reserveOwn : metric(r, "revenue_reserve").v; }
    var what = mixed ? "The academy's own reserve" : "The reserve";
    var peak = rows[0];
    rows.forEach(function (r) { if (val(r) > val(peak)) peak = r; });
    var last = rows[rows.length - 1], pv = val(peak), lv = val(last);
    var withTrust = mixed && last.trustShare ? " (" + fmtExact(metric(last, "revenue_reserve").v) + " counting its share of the trust's reserve)" : "";
    if (peak === last) {
      return what + " grew to " + fmtExact(lv) + " in " + last.y + withTrust + ", the highest in the years shown (from " + fmtExact(val(rows[0])) + " in " + rows[0].y + ")";
    }
    var text = what + " fell from " + fmtExact(pv) + " in " + peak.y + " to " + fmtExact(lv) + " in " + last.y + withTrust;
    var i0 = metric(peak, "total_income"), i1 = metric(last, "total_income"), e0 = metric(peak, "total_expenditure"), e1 = metric(last, "total_expenditure");
    if (i0 && i1 && e0 && e1 && i0.v > 0 && e0.v > 0) {
      var gi = i1.v / i0.v - 1, ge = e1.v / e0.v - 1;
      if (ge > gi) text += ", as spending rose faster than income (" + signedPct(ge) + " against " + signedPct(gi) + ")";
    }
    return text;
  }
  function categoryMessage(m) {
    var ly = lineYear(m), sy = simYear(m);
    if (!ly || ly.year !== sy || suspectYear(m, sy)) return null;
    var best = null;
    SPEND_LINES.forEach(function (l) {
      var mine = ly.get(l[0]), sim = m.similar[l[0]];
      if (isNum(mine) && isNum(sim) && (!best || Math.abs(mine - sim) > Math.abs(best.mine - best.sim))) best = { label: l[1], mine: mine, sim: sim };
    });
    return best ? "The biggest difference from " + simWords(m) + " is " + best.label.toLowerCase() + ": " + fmtExact(best.mine) + " per pupil in " + sy + ", " +
      againstMedian(best.mine, best.sim, "the median") : null;
  }
  function ptaMessages(m, c) {
    var main = m.pta[0] || null, last = lastPta(main), out = [];
    var councilName = (m.area.ok && m.area.name) || m.council.name || "the council";
    if (!main) {
      out.push("No registered parents' association found on the " + CHARITY_SOURCE + " (charities with an income of £5,000 or less don't have to register)");
      var don = donationsLine(m);
      out.push(don ? "The school's own donations and voluntary funds line was " + both(don.pp, don.v, true) + " in " + don.y + ", which can include parents' giving"
        : "The school's own donations line isn't published for an unmarked year");
    } else if (!last) {
      out.push(main.name + " is registered as charity " + main.number + ", but no yearly figures are published yet");
    } else {
      var prev = prevPta(main, last);
      out.push(ptaLead(last) + ": raised " + fmtExact(last.income) +
        (isNum(last.incomePp) ? ", " + fmtExact(last.incomePp) + " per pupil" : "") +
        (prev && prev.income > 0 ? ", " + signedPct(last.income / prev.income - 1).replace("+", "up ").replace("-", "down ") + " on the year before" : ""));
      var cmp = ptaComparison(m, last);
      if ((cmp.council || cmp.england) && isNum(last.incomePp)) {
        var against = [];
        if (cmp.council) against.push(ptaAgainst(last, cmp.council.v, cmp.councilYear, "the median among " + councilName + " schools with a registered parents' association"));
        if (cmp.england) against.push(ptaAgainst(last, cmp.england.v, cmp.englandYear, "the median across England"));
        out.push(fmtExact(last.incomePp) + " per pupil in the " + ptaYearWords(last.y) + ": " + against.join("; "));
      }
    }
    var t = ptaTarget(m);
    if (t) out.push(t.message);
    if (out.length < 3) out.push(budgetMessage(m));
    return out.slice(0, 3);
  }
  function capital(t) { return t.charAt(0).toUpperCase() + t.slice(1); }
  // A PTA's per pupil beside a median, in words when both are for the same school year; a different year says so.
  function ptaAgainst(last, median, year, what) {
    var w = year === last.y ? ratioWords(last.incomePp, median) : null;
    return w ? w + " " + what + " (" + fmtExact(median) + ")"
      : "against " + what + " of " + fmtExact(median) + " (" + ptaYearWords(year) + (year !== last.y ? ", a different year" : "") + ")";
  }
  function summaryMessages(m, ctx, view) {
    var c = ctxOf(ctx);
    if (!m || !m.ok) return [];
    if (packView(view) === "ptfa") return ptaMessages(m, c);
    var out = [budgetMessage(m), spendMessage(m)];
    var third = packView(view) === "review" ? categoryMessage(m) : null;
    out.push(third || reserveMessage(m));
    return out;
  }
  function inDeficitOrHeading(m) {
    var x = reserveShare(m);
    return !!((x && x.r.v < 0) || (m.status && (m.status.key === "in_deficit" || m.status.key === "heading_for_deficit")));
  }
  // Why a deficit happens and what helps, short enough for a summary; the full IFS framing is quoted on the budget slide.
  function deficitHelp(m, c) {
    var f = c.framings.why_schools_go_into_deficit, p = f ? pages(f.pages) : "";
    return ["Why this happens: most of a school's money goes on staff, so when pay and other costs rise faster than funding, or pupil numbers fall, the budget is squeezed" + (p ? " (" + p + ")" : "") + ".",
      "What helps: a recovery plan agreed with " + m.overseer + " that says how many years it will take, forecasts governors check often, and an open conversation with parents."];
  }

  // ---------------------------------------------------------------- nearby schools (the 'nearby' contract in /data/s)
  function nearbyWords(nb) {
    var phase = nb && nb.phase ? nb.phase.toLowerCase() + " " : "";
    return "nearby " + phase + "schools";
  }
  function nearbyNotes(m) {
    var nb = m.nearby, out = [];
    if (!nb) return out;
    var sy = snapshotYear(m);
    if (nb.year && sy && nb.year !== sy) {
      out.push("Nearby figures are for " + nb.year + ", the latest year most of these schools have published; this school's own latest year is " + sy + ".");
    }
    var rows = [nb.self].concat(nb.schools).filter(Boolean);
    if (rows.some(function (r) { return r.academy; }) && rows.some(function (r) { return !r.academy; })) {
      out.push("The list mixes council-run schools and academies: council-run years run April to March and academy years September to August.");
    }
    out.push("Nearby schools serve different intakes, so the free school meals column is shown beside the money.");
    if (rows.some(function (r) { return r.federation; })) out.push("A school marked 'figures for the whole' federation reports one return for every school in it, so its figures aren't one school's.");
    if (rows.some(function (r) { return r.pta_lower && isNum(r.pta_pp); })) out.push("* Parents' association matched with lower confidence.");
    return out;
  }
  function nearbySlides(m, c) {
    var nb = m.nearby;
    var sl = slide("nearby", "chart", "Compared with schools nearby");
    if (!nb || !nb.schools.length) {
      sl.kind = "note";
      sl.lead = "Nearby comparisons aren't published for this school yet.";
      sl.bullets = ["When they are, this slide sets the school beside the nearest state schools of the same phase: spending, reserve, staff costs and parents' association income per pupil, with free school meals shown because intakes differ.",
        "The similar-schools comparisons in this pack still apply."];
      sl.sources = schoolSources(m, c).slice(0, 1);
      return [sl];
    }
    var words = nearbyWords(nb), year = nb.year || "the latest year";
    sl.lead = "The " + plural(nb.schools.length, "nearest " + (nb.phase ? nb.phase.toLowerCase() + " " : "") + "school") +
      (isNum(nb.radius) ? ", all within " + nb.radius + " miles" : "") + ", " + year + ". A difference is a reason to ask why, not a judgement.";
    [["spend_pp", "Spending per pupil"], ["reserve_pp", "Reserve per pupil"], ["pta_pp", "Parents' association income per pupil"]].forEach(function (k) {
      var r = nb.rank[k[0]], med = nb.medians[k[0]];
      if (!r) return;
      var own = k[0] === "pta_pp" ? "each association's own year" : year;
      // In words only where every figure is for the one nearby year (each PTA keeps its own year, so not for those).
      var mine = nb.self ? nb.self[k[0]] : null, w = isNum(med) && k[0] !== "pta_pp" ? ratioWords(mine, med) : null;
      sl.bullets.push(k[1] + ": " + (r.rank === 1 ? "the highest" : ordinal(r.rank) + " highest") + " of " + r.of + " " + words + " with a figure, counting this one (" + own + ")" +
        (isNum(med) ? (w ? "; this school's " + fmtExact(mine) + " is " + w + " the median of " + fmtExact(med) : "; the median is " + fmtExact(med)) : "") + ".");
    });
    if (!sl.bullets.length) sl.bullets.push("Too few nearby schools have published figures for " + year + " to rank this school among them.");
    var cats = [["spend_pp", "Spending"], ["income_pp", "Income"], ["gov_pp", "Government grants"], ["reserve_pp", "Reserve"]];
    var me = nb.self || {};
    sl.chart = chart("bar", "£ per pupil", [
      { key: "school", name: "This school, " + year, points: cats.map(function (k) { return { y: k[1], v: round(me[k[0]]), suspect: false }; }) },
      { key: "nearby", name: "Nearby median, " + year, points: cats.map(function (k) { return { y: k[1], v: round(nb.medians[k[0]]), suspect: false }; }) }
    ]);
    if (!sl.chart) sl.kind = "note";
    sl.note = nearbyNotes(m).join(" ");
    sl.sources = [SITE + " nearby comparison of DfE CFR and AAR returns, " + year, CHARITY_SOURCE + " (parents' associations)"];
    // The table is split across slides (this school repeated on each) rather than shrunk: 4 neighbours a slide.
    var full = nearbyTable(m), PER = 4;
    var selfRows = full.rows.filter(function (r) { return r.self; }), medRows = full.rows.filter(function (r) { return r.median; });
    var others = full.rows.filter(function (r) { return !r.self && !r.median; }), chunks = [];
    for (var i = 0; i < others.length; i += PER) chunks.push(others.slice(i, i + PER));
    var out = [sl];
    chunks.forEach(function (ch, k) {
      var t = slide(k ? "nearby_table_" + (k + 1) : "nearby_table", "table", "Schools nearby, " + year + (chunks.length > 1 ? " (" + (k + 1) + " of " + chunks.length + ")" : ""));
      t.lead = "Nearest first, per pupil in the same year; a dash means the figure isn't published or is marked as unusual.";
      t.table = { caption: full.caption, columns: full.columns, rows: selfRows.concat(ch, k === chunks.length - 1 ? medRows : []) };
      t.note = nearbyNotes(m).join(" ");
      t.sources = sl.sources.slice();
      t.links = k === 0 ? [{ text: "Compare these schools side by side", href: compareHref(m) }] : [];
      out.push(t);
    });
    return out;
  }
  function compareHref(m) {
    var urns = [m.urn].concat(m.nearby.schools.map(function (r) { return r.urn; })).filter(function (u, i, a) { return u && a.indexOf(u) === i; }).slice(0, 6);
    return "/compare/?urns=" + urns.map(encodeURIComponent).join(",");
  }
  function nearbyTable(m) {
    var nb = m.nearby, year = nb.year || "";
    function row(r, self) {
      var st = r.status ? { text: ICONS[r.status] + " " + LABELS[r.status], status: r.status } : cell(null);
      return { self: !!self, cells: [
        cell(r.name + (self ? " (this school)" : "") + (r.academy ? " · academy" : "") + (r.federation ? " (figures for the whole " + r.federation + ")" : "")),
        cell(self ? "here" : isNum(r.mi) ? r.mi.toFixed(1) : null), st,
        cell(isNum(r.spend_pp) ? fmtExact(r.spend_pp) : null), cell(isNum(r.reserve_pp) ? fmtExact(r.reserve_pp) : null),
        cell(isNum(r.staff_pct) ? fmtPct(r.staff_pct) : null),
        cell(isNum(r.pta_pp) ? fmtExact(r.pta_pp) + (r.pta_year ? " (" + r.pta_year + ")" : "") + (r.pta_lower ? " *" : "") : null), cell(isNum(r.fsm_pct) ? fmtPct(r.fsm_pct) : null)
      ] };
    }
    var rows = (nb.self ? [row(nb.self, true)] : []).concat(nb.schools.map(function (r) { return row(r, false); }));
    var md = nb.medians;
    if (isNum(md.spend_pp) || isNum(md.reserve_pp) || isNum(md.pta_pp)) {
      rows.push({ median: true, cells: [cell("Median"), cell(null), cell(null), cell(isNum(md.spend_pp) ? fmtExact(md.spend_pp) : null),
        cell(isNum(md.reserve_pp) ? fmtExact(md.reserve_pp) : null), cell(null), cell(isNum(md.pta_pp) ? fmtExact(md.pta_pp) : null), cell(null)] });
    }
    return {
      caption: "Schools nearby, " + year + ": distance, budget status and per-pupil figures",
      columns: ["School", "Miles", "Status, " + year, "Spending per pupil", "Reserve per pupil", "Staff costs (share of spending)", "Parents' association per pupil (year)", "Free school meals"],
      rows: rows
    };
  }

  // ---------------------------------------------------------------- spending categories
  // This school's category figures: the latest unmarked year in /data/sx, else the /data/s snapshot when it isn't marked.
  function lineYear(m) {
    var row = latestRow(m, "teaching_staff");
    if (row) return { year: row.y, get: function (k) { var c = metric(row, k); return c && isNum(c.pp) ? c.pp : null; } };
    var sy = snapshotYear(m);
    if (sy && !suspectYear(m, sy) && SPEND_LINES.some(function (l) { return isNum(m.pp[l[0]]); })) {
      return { year: sy, get: function (k) { return isNum(m.pp[k]) ? m.pp[k] : null; } };
    }
    return null;
  }
  function spendTable(m, withCouncil) {
    var ly = lineYear(m), sy = simYear(m), nb = m.nearby, sm = m.similarMeta;
    var simOk = !!(sy && !suspectYear(m, sy) && Object.keys(m.similar).length);
    var nbOk = !!(nb && nb.schools.length);
    var selfLines = nbOk && nb.self && nb.year !== (ly && ly.year) && Object.keys(nb.self.lines).length ? nb.self.lines : null;
    var ya = ly ? ly.year : sy;
    var ca = withCouncil ? areaStat(m.area, ya, areaGroup(m), "spendPp") : null;
    var columns = ["Per pupil", "This school" + (ly ? ", " + ly.year : ""), "Similar schools' median" + (simOk && sm && isNum(sm.peers) && sm.peers > 0 ? " (" + plural(sm.peers, "school") + ")" : "") + (simOk ? ", " + sy : ""), "Difference from similar", "Rating",
      "Nearby median" + (nbOk && nb.year ? ", " + nb.year : "")];
    if (selfLines) columns.push("This school, " + nb.year);
    if (withCouncil) columns.push("Council median (all phases)" + (ca ? ", " + ya : ""));
    function line(label, key, mine, sim, near, own, council) {
      var same = ly && simOk && ly.year === sy;
      var diff = same && isNum(mine) && isNum(sim) ? mine - sim : null;
      var r = diff != null ? rateAgainst(label, mine, sim, "similar schools' median", sy) : null;
      var cells = [cell(label), cell(isNum(mine) ? fmtExact(mine) : null), cell(isNum(sim) ? fmtExact(sim) : null),
        cell(diff != null ? fmtExact(diff, true) : null), ragCell(r), cell(isNum(near) ? fmtExact(near) : null)];
      if (selfLines) cells.push(cell(isNum(own) ? fmtExact(own) : null));
      if (withCouncil) cells.push(cell(isNum(council) ? fmtExact(council) : null));
      return { key: key, cells: cells, rag: r };
    }
    var totRow = ly ? rowOf(m, ly.year) : null, tot = totRow ? metric(totRow, "total_expenditure") : null;
    var rows = [line("All spending", "total_expenditure", tot && isNum(tot.pp) ? tot.pp : (ly && ly.year === sy && sy === snapshotYear(m) ? m.pp.total_expenditure : null),
      simOk ? m.similar.total_expenditure : null, nbOk ? nb.medians.spend_pp : null, nbOk && nb.self ? nb.self.spend_pp : null, ca ? ca.v : null)];
    SPEND_LINES.forEach(function (l) {
      rows.push(line(l[1], l[0], ly ? ly.get(l[0]) : null, simOk ? m.similar[l[0]] : null, nbOk ? nb.lineMedians[l[0]] : null, selfLines ? selfLines[l[0]] : null, null));
    });
    return { caption: "Spending per pupil by category: this school, similar schools and nearby schools", columns: columns, rows: rows,
      years: { mine: ly ? ly.year : null, similar: simOk ? sy : null, nearby: nbOk ? nb.year : null } };
  }
  function spendTableNotes(m, t, withCouncil) {
    var out = [];
    var ys = [t.years.mine, t.years.similar, t.years.nearby].filter(Boolean).filter(function (y, i, a) { return a.indexOf(y) === i; });
    if (ys.length > 1) out.push("The columns are from different years (" + ys.join(", ") + "), as each heading says; differences and ratings are worked out only within one year.");
    if (!m.nearby || !m.nearby.schools.length) out.push("Nearby comparisons aren't published for this school yet, so the nearby column shows a dash.");
    if (withCouncil) out.push("Council medians mix primary and secondary schools, so they are a rough guide only.");
    var sm = m.similarMeta;
    out.push(sm && isNum(sm.peers) && sm.peers > 0 ? capital(simWords(m)) + ": " + (sm.method || "schools of the same phase and size with a similar intake.") + (/[.!?]$/.test(sm.method || ".") ? "" : ".")
      : "Similar schools are the same phase and size with a similar intake.");
    return out;
  }

  // ---------------------------------------------------------------- parents' associations
  function donationsLine(m) {
    var row = latestRow(m, "donations_revenue");
    if (row) return { y: row.y, v: metric(row, "donations_revenue").v, pp: metric(row, "donations_revenue").pp };
    var y = snapshotYear(m);
    if (y && !suspectYear(m, y) && isNum(m.incomeLines.donations_revenue)) {
      var r = rowOf(m, y);
      return { y: y, v: m.incomeLines.donations_revenue, pp: perPupil(m.incomeLines.donations_revenue, r ? r.pupils : m.pupilsLatest) };
    }
    return null;
  }
  // The council and England PTA medians, each chosen on its own: the association's own school year when that area
  // publishes one, else its latest published year. Each carries its year, so a difference is always said in words,
  // and a council with too few returns for a median never hides the England figure.
  function ptaComparison(m, last) {
    function yearOf(A) {
      if (!A || !A.ok) return null;
      if (last && areaStat(A, last.y, "all", "ptaPp")) return last.y;
      var years = A.years.slice().reverse();
      for (var i = 0; i < years.length; i++) { if (areaStat(A, years[i], "all", "ptaPp")) return years[i]; }
      return null;
    }
    var cy = yearOf(m.area), ey = yearOf(m.england);
    return { year: cy || ey, councilYear: cy, englandYear: ey, council: cy ? areaStat(m.area, cy, "all", "ptaPp") : null,
      england: ey ? areaStat(m.england, ey, "all", "ptaPp") : null, councilN: cy ? areaStat(m.area, cy, "all", "ptaSchools") : null };
  }
  // The association's figures for one school year, if it has a return counted in that year.
  function ptaIn(main, y) {
    if (!main) return null;
    for (var i = main.years.length - 1; i >= 0; i--) { if (main.years[i].y === y) return main.years[i]; }
    return null;
  }
  // Every PTA figure leads with the school year its return is counted in, as "the year to Aug 2025" (the year pupils
  // and medians use); accounts that end in another month say when, and two returns in one school year say both.
  function accountsEnd(e) {
    var ends = (e.ends || []).map(function (x) { return x.end; });
    if (ends.length > 1) return "accounts to " + ends.slice(0, -1).join(", ") + " and " + ends[ends.length - 1] + ", added together";
    return e.end && e.month && e.month !== 8 ? "accounts to " + e.end : "";
  }
  function ptaWhen(e) { var a = accountsEnd(e); return "the " + ptaYearWords(e.y) + (a ? " (" + a + ")" : ""); }
  function ptaLead(e) { var a = accountsEnd(e); return capital(ptaYearWords(e.y)) + (a ? " (" + a + ")" : ""); }
  function ptaYearText(e) { var a = accountsEnd(e); return ptaYearWords(e.y) + " (school year " + e.y + (a ? ", " + a : "") + ")"; }
  function usablePupils(row) { return !!(row && !row.suspect && isNum(row.pupils) && row.pupils > 0); }
  // What a parents' association raising the council's median per pupil would bring in, with the same year's pupils.
  // A year whose figures are marked as unusual is never used: the latest unmarked year with a council median stands
  // in, named as such, and with none there is no illustration.
  function ptaTarget(m) {
    var main = m.pta[0] || null, last = lastPta(main);
    var cmp = ptaComparison(m, last);
    if (!cmp.council) return null;
    var year = cmp.councilYear, row = rowOf(m, year), marked = row && row.suspect ? year : null;
    if (!usablePupils(row)) {
      year = null;
      row = null;
      var years = m.area.years.slice().reverse();
      for (var i = 0; i < years.length; i++) {
        var r = rowOf(m, years[i]);
        if (usablePupils(r) && areaStat(m.area, years[i], "all", "ptaPp")) { year = years[i]; row = r; break; }
      }
      if (!row) return null;
    }
    var councilName = (m.area.ok && m.area.name) || m.council.name || "the council";
    var median = areaStat(m.area, year, "all", "ptaPp").v, target = median * row.pupils;
    var same = ptaIn(main, year), income = same && isNum(same.income) ? same.income : null;
    var t = { year: year, median: median, pupils: row.pupils, target: Math.round(target), income: income, gap: isNum(income) ? Math.round(target - income) : null };
    if (marked) t.note = marked + " is marked as unusual, so the illustration uses " + year + ", the latest unmarked year with a median.";
    var when = ptaYearWords(t.year), w = isNum(income) ? ratioWords(income, t.target) : null;
    var base = "At " + councilName + "'s median of " + fmtExact(t.median) + " per pupil, " + fmtPupils(t.pupils) + " pupils (" + when + ") would bring in about " + fmtExact(t.target) + " a year";
    if (t.gap != null && t.gap <= 0) {
      t.message = "Already raises " + (w && w !== "about the same as" ? w : "more than") + " " + councilName + "'s median per pupil: " + fmtExact(income) + " in the " + when +
        " against about " + fmtExact(t.target) + " at the median (an illustration)";
    } else if (t.gap != null) t.message = base + ", " + fmtExact(t.gap) + " more than in the " + when + " (an illustration, not a target set by anyone)";
    else t.message = base + " (an illustration, not a target set by anyone)";
    return t;
  }

  // ---------------------------------------------------------------- slides every pack shares
  function titleSlide(m, view, c, title, extraLead) {
    var p = PACKS[view];
    var latest = latestRow(m, "total_income") || lastTrusted(m);
    var year = latest ? latest.y : snapshotYear(m);
    var sl = slide("title", "title", title || m.name);
    sl.meta = { preparedFor: p.meeting, date: fmtDate(c.today) };
    sl.lead = p.label + (title && title !== m.name ? " for " + m.name : "") + (m.council.name ? ": " + m.council.name : "") + (year ? ", " + year : "") +
      (latest && isNum(latest.pupils) ? ", " + fmtPupils(latest.pupils) + " pupils" : "") + (extraLead || "");
    if (latest && isNum(latest.pupils)) sl.figures.push(figure("pupils", "Pupils", latest.pupils, null, latest.y, srcOf(m, latest.y), "pupils"));
    if (m.council.name) sl.bullets.push("Council: " + m.council.name + (m.council.code ? " (LA " + m.council.code + ")" : ""));
    sl.bullets.push(m.academy ? "An academy" + (m.trust ? " in " + m.trust : "") + ": its accounts go to the DfE through the trust, in years running September to August."
      : "Council-run: its budget is set and checked through the council, in years running April to March.");
    var newest = snapshotYear(m);
    if (latest && newest !== latest.y && suspectYear(m, newest)) sl.bullets.push(newest + " is published too, but its figures are marked as unusual, so headlines use " + latest.y + ".");
    sl.note = "Figures are a starting point for a conversation with the school, not a verdict on it. Type the meeting and date above; they print and go into the PowerPoint.";
    sl.sources = schoolSources(m, c);
    return sl;
  }
  function summarySlide(m, c, view, ratings) {
    var sl = slide("summary", "summary", "Summary");
    sl.messages = summaryMessages(m, c.raw, view);
    sl.ratings = ratings.filter(Boolean);
    sl.lead = "Three things to know, worked out from the published figures.";
    if (view !== "ptfa" && inDeficitOrHeading(m)) sl.note = deficitHelp(m, c).join(" ");
    else if (view === "ptfa" && inDeficitOrHeading(m)) sl.note = "The school's own budget is under pressure (see 'The school's finances in brief'); parents' money pays for extras, not the core budget.";
    else sl.note = "Each rating carries an icon and a word as well as a colour, and says what it is measured against.";
    sl.sources = schoolSources(m, c).slice(0, 1);
    if (view !== "ptfa" && inDeficitOrHeading(m)) { var fs = framingSource(c, "why_schools_go_into_deficit"); if (fs) sl.sources.push(fs); }
    if (view === "ptfa") sl.sources.push(CHARITY_SOURCE);
    return sl;
  }
  function fillQuestion(m) {
    var x = reserveShare(m);
    return function (t) {
      return String(t || "").replace(/\{name\}/g, m.name).replace(/\{overseer\}/g, m.overseer)
        .replace(/\{reserve\}/g, fmtMoney(x ? x.r.v : null)).replace(/\{years\}/g, String(m.streak));
    };
  }
  function questionsSlide(m, c, opts) {
    opts = opts || {};
    var sl = slide("questions", "questions", opts.title || "Questions to ask");
    var fill = fillQuestion(m);
    (opts.first || []).forEach(function (q) { sl.bullets.push(fill(q)); });
    var sets = [];
    if (m.status) sets.push(m.status.key);
    if (opts.falling) sets.push("falling_rolls");
    if (m.siteFlags.high_send) sets.push("high_send");
    if (m.academy) sets.push("academy");
    sets.push("any");
    var qs = [];
    sets.forEach(function (k) { (c.questions[k] || []).forEach(function (q) { if (q && q.text && qs.indexOf(q) === -1) qs.push(q); }); });
    qs.slice(0, Math.max(0, (opts.max || 6) - sl.bullets.length)).forEach(function (q) {
      var tail = q.why || q.page ? " (" + [q.why, q.page ? pages(q.page) : ""].filter(Boolean).join(" ") + ")" : "";
      sl.bullets.push(fill(q.text) + tail);
      if (q.page) sl.sources.push(ifsSource(c, q.page));
    });
    if (!sl.bullets.length) sl.bullets.push("What is the school's budget plan for the next three years, and what does it assume about pupil numbers and pay?");
    sl.lead = opts.lead || "Questions to take to the meeting, with context from the IFS annual report on education spending.";
    sl.links = opts.links || [{ text: "Guides for parents and governors", href: "/guides/" }];
    if (m.path) sl.links.push({ text: "The school's page", href: m.path });
    if (!sl.sources.length) sl.sources = schoolSources(m, c).slice(0, 1);
    return sl;
  }
  function actionsSlide(suggestions) {
    var sl = slide("actions", "actions", "Actions and decisions");
    sl.lead = "Who does what, by when. Type into the table: rows are kept in this browser and go into the PowerPoint as an editable table.";
    sl.columns = ["Action or decision", "Owner", "By when"];
    sl.actions = (suggestions || []).filter(Boolean).map(function (a) { return { action: a, owner: "", by: "" }; });
    while (sl.actions.length < 3) sl.actions.push({ action: "", owner: "", by: "" });
    sl.note = "Suggested rows come from the figures; change or remove them.";
    sl.sources = ["Typed at the meeting and kept in this browser only"];
    return sl;
  }
  function packSources(slides, c, m, extraLinks, extra) {
    var sl = sourcesSlide(slides.filter(function (x) { return x.kind !== "actions"; }), c, extra);
    sl.title = "Sources and how to check";
    var ifsPages = [], rest = [];
    sl.bullets.forEach(function (b) {
      if (b.indexOf(c.cite) === 0) {
        var p = /IFS pp?\.([\d–, ]+)/.exec(b);
        if (p) p[1].split(/,\s*/).forEach(function (x) { if (ifsPages.indexOf(x) === -1) ifsPages.push(x); });
      } else rest.push(b);
    });
    if (ifsPages.length) {
      ifsPages.sort(function (a, b) { return parseInt(a, 10) - parseInt(b, 10); });
      rest.push(c.cite + ", pages quoted: " + ifsPages.join(", ") + (c.url ? ": " + c.url : ""));
    }
    sl.bullets = rest;
    sl.lead = "Every figure comes from published open data, shown as it was filed. To check one, open the official source below.";
    var how = [{ text: "This school in the DfE Financial Benchmarking and Insights Tool", href: (c.links.fbit || FBIT_HOME) + m.urn }];
    sl.links = how.concat(extraLinks || [], sl.links);
    sl.sources = sl.bullets.slice();
    return sl;
  }
  function finish(slides, deck) {
    slides.forEach(function (x, i) { x.n = i + 1; });
    deck.slides = slides;
    return deck;
  }

  // ======================================================================
  // Governors' finance pack (also view=school)
  // ======================================================================
  function schoolDeck(m, ctx) {
    var c = ctxOf(ctx);
    if (!m || !m.ok) return messageDeck(PACKS.governors.label, "This school's figures couldn't be loaded, so there is nothing to present yet.");
    var slides = [];
    var st = m.status;
    var trend = pupilTrend(m);

    slides.push(titleSlide(m, "governors", c));
    slides.push(summarySlide(m, c, "governors", [rateBalance(m), rateReserve(m), rateSpendSimilar(m), rateSpendNearby(m), rateStaff(m, c), ratePupils(m)]));

    // Budget position: in-year balance and reserve, every year, per pupil with totals beside.
    var sb = slide("budget", "chart", "Budget position");
    var reserveRow = latestRow(m, "revenue_reserve");
    if (st) {
      sb.status = { key: st.key, label: st.label, icon: st.icon };
      var said = st.reason && st.reason.toLowerCase().indexOf(st.label.toLowerCase()) === 0;
      sb.lead = st.icon + " " + (said ? st.reason : st.label + (st.reason ? ": " + st.reason : "")) + (st.year ? " (" + st.year + ", " + srcOf(m, st.year) + ")" : "");
    } else {
      sb.lead = "There isn't a full year of published figures to assess this school's budget yet.";
    }
    sb.chart = chart("bar", "£ per pupil", [
      { key: "in_year_balance", name: "In-year balance per pupil", points: points(m, "in_year_balance", "pp") },
      { key: "revenue_reserve", name: "Reserve per pupil at year end", points: points(m, "revenue_reserve", "pp") }
    ]);
    if (reserveRow) {
      var rv = metric(reserveRow, "revenue_reserve");
      sb.figures.push(figure("revenue_reserve", reserveLabel("Reserve at the end of the year", reserveRow), rv.v, rv.pp, reserveRow.y, srcOf(m, reserveRow.y)));
      var bal = metric(reserveRow, "in_year_balance");
      if (bal && isNum(bal.v)) sb.figures.push(figure("in_year_balance", bal.v < 0 ? "Spent more than it received" : "Received more than it spent", bal.v, bal.pp, reserveRow.y, srcOf(m, reserveRow.y)));
    } else {
      sb.bullets.push(noHeadline(m, "revenue_reserve", "Reserve figures for this school"));
    }
    sb.ratings = [rateBalance(m), rateReserve(m)].filter(Boolean);
    if (inDeficitOrHeading(m)) {
      sb.bullets.push(deficitHelp(m, c)[1]);
      sb.links = [{ text: "How to read a deficit", href: "/guides/parents/#how-to-read-a-deficit" }];
      var whyFull = framing(c, "why_schools_go_into_deficit");
      sb.note = "Why this happens: " + (whyFull || deficitHelp(m, c)[0].replace(/^Why this happens: /, ""));
      sb.sources.push(framingSource(c, "why_schools_go_into_deficit"));
    } else if (isHeld(m)) {
      sb.bullets.push(heldWords(m) + ".");
      sb.bullets.push("What helps: asking the trust how much of the pooled reserve is set aside for this school, and how it decides what the reserve is used for.");
    } else if (st && st.key === "tight") {
      var tightLine = ctxLine(c, "school", "costs_outpaced_funding");
      if (tightLine) { sb.bullets.push("Context: " + tightLine.text); sb.sources.push(ifsSource(c, tightLine.page)); }
      sb.bullets.push("What helps: a small contingency in the budget, knowing which costs are likely to rise next year, and not relying on one-off money to balance.");
    } else {
      sb.bullets.push("The status is worked out from the reserve as a share of a year's income and the run of years spending more than received.");
    }
    if (!sb.note) { sb.note = [suspectNote(m), framing(c, "one_deficit_year")].filter(Boolean).join(" "); sb.sources.push(framingSource(c, "one_deficit_year")); }
    sb.note = [sb.note, trustNote(m)].filter(Boolean).join(" ");
    sb.sources = sb.sources.filter(Boolean).concat(schoolSources(m, c).slice(0, 1));
    slides.push(sb);

    // Funding and spending per pupil over the years, with similar schools beside the latest year.
    var s3 = slide("funding", "chart", "Funding and spending per pupil");
    s3.chart = chart("line", "£ per pupil", [
      { key: "grant_funding", name: "Government grants", points: points(m, "grant_funding", "pp") },
      { key: "total_income", name: "All income", points: points(m, "total_income", "pp") },
      { key: "total_expenditure", name: "Spending", points: points(m, "total_expenditure", "pp") }
    ]);
    var inc = latestRow(m, "total_income");
    if (inc) {
      var ci = metric(inc, "total_income"), cg = metric(inc, "grant_funding"), ce = metric(inc, "total_expenditure");
      s3.figures.push(figure("total_income", "All income", ci.v, ci.pp, inc.y, srcOf(m, inc.y)));
      if (cg && isNum(cg.v)) s3.figures.push(figure("grant_funding", "Government grants", cg.v, cg.pp, inc.y, srcOf(m, inc.y)));
      if (ce && isNum(ce.v)) s3.figures.push(figure("total_expenditure", "Spending", ce.v, ce.pp, inc.y, srcOf(m, inc.y)));
    } else {
      s3.lead = noHeadline(m, "total_income", "Figures for this school's income");
    }
    var vs = spendVsSimilar(m);
    if (vs) {
      var sw3 = ratioWords(vs.mine, vs.sim);
      s3.bullets.push("The median spending of " + simWords(m) + " was " + fmtExact(vs.sim) + " per pupil in " + vs.year + (isNum(m.similar.total_income) ? " and their median income " + fmtExact(m.similar.total_income) : "") +
        "; this school spent " + fmtExact(vs.mine) + (sw3 ? ", " + sw3 + " the median" : "") + " (" + vs.year + ", " + srcOf(m, vs.year) + "; medians from " + SITE + ").");
    } else if (Object.keys(m.similar).length) {
      s3.bullets.push("Similar schools' medians are published for " + simYear(m) + ", a year marked as unusual here, so they aren't set beside this school's figures.");
    }
    var r0 = firstRow(m, "total_income"), r1 = inc;
    var rpp0 = r0 && metric(r0, "total_income").rpp, rpp1 = r1 && metric(r1, "total_income").rpp;
    if (c.realLabel && r0 && r1 && r0 !== r1 && isNum(rpp0) && isNum(rpp1)) {
      s3.bullets.push("In real terms, " + c.realLabel + ", all income per pupil went from " + fmtExact(rpp0) + " in " + r0.y + " to " + fmtExact(rpp1) + " in " + r1.y + ".");
      s3.sources.push(c.realLabel.replace(/^in /, "Real terms: "));
    }
    s3.note = [suspectNote(m), framing(c, "funding_vs_spending_per_pupil")].filter(Boolean).join(" ");
    s3.sources = schoolSources(m, c).slice(0, 1).concat(s3.sources, [AREA_SOURCE.replace("returns", "returns (similar schools)"), framingSource(c, "funding_vs_spending_per_pupil")]).filter(Boolean);
    slides.push(s3);

    slides.push(incomeSlide(m, c));

    // Where the money goes, by category, against similar and nearby schools.
    var sw = slide("where_money_goes", "table", "Where the money goes");
    sw.table = spendTable(m, false);
    var ss = staffShare(m);
    sw.lead = ss ? "Staff costs were " + Math.round(ss.share * 100) + "% of spending in " + ss.row.y + ": " + both(ss.staff.pp, ss.staff.v) + " (" + srcOf(m, ss.row.y) + ", 'Staff Total')."
      : "Spending per pupil in each category, beside similar and nearby schools.";
    var staffLine = ctxLine(c, "school", "staff_share");
    sw.note = (staffLine ? staffLine.text + " " : "") + spendTableNotes(m, sw.table, false).join(" ");
    sw.sources = schoolSources(m, c).slice(0, 1).concat([AREA_SOURCE + " (similar and nearby schools)"], staffLine ? [ifsSource(c, staffLine.page)] : []);
    slides.push(sw);

    nearbySlides(m, c).forEach(function (x) { slides.push(x); });

    // Pupil numbers and the risk of a falling roll.
    var s8 = slide("pupils", "chart", "Pupil numbers and falling-roll risk");
    s8.chart = chart("line", "pupils", [{ key: "pupils", name: "Pupils", points: m.rows.map(function (r) { return { y: r.y, v: isNum(r.pupils) ? Math.round(r.pupils * 10) / 10 : null, suspect: r.suspect }; }) }]);
    if (trend) {
      var change = trend.change;
      s8.figures.push(figure("pupils", "Pupils", trend.last.pupils, null, trend.last.y, srcOf(m, trend.last.y), "pupils"));
      s8.lead = fmtPupils(trend.last.pupils) + " pupils in " + trend.last.y + ", " + (Math.abs(change) < 0.005 ? "about the same as" : (change < 0 ? "down " : "up ") +
        fmtPct(Math.abs(change) * 100) + " from") + " " + fmtPupils(trend.first.pupils) + " in " + trend.first.y + " (" + sourceSpan(m) + ").";
      s8.ratings = [ratePupils(m)];
    } else {
      s8.lead = m.rows.some(function (r) { return r.suspect && isNum(r.pupils); })
        ? "Pupil numbers aren't published for enough unmarked years to show a trend; the chart shows every year, with marked years flagged."
        : "Pupil numbers for this school aren't published for enough years to show a trend.";
    }
    var rollsLine = ctxLine(c, "school", m.phaseKey === "secondary" ? "secondary_rolls" : "primary_rolls");
    if (trend && trend.falling) {
      s8.bullets.push("Schools are mostly funded per pupil, so fewer pupils means less money, while costs don't fall in step.");
      s8.note = framing(c, "falling_rolls");
      s8.sources.push(framingSource(c, "falling_rolls"));
    } else {
      s8.bullets.push("Schools are mostly funded per pupil, so pupil numbers drive most of the budget.");
    }
    if (rollsLine && (m.phaseKey === "primary" || m.phaseKey === "secondary")) {
      s8.bullets.push("Looking ahead: " + rollsLine.text);
      s8.sources.push(ifsSource(c, rollsLine.page));
    }
    s8.sources = schoolSources(m, c).slice(0, 1).concat(s8.sources).filter(Boolean);
    slides.push(s8);

    slides.push(pressuresSlide(m, c));
    slides.push(councilSlide(m, c));
    slides.push(questionsSlide(m, c, { falling: trend && trend.falling,
      links: [{ text: "Guides for parents and governors", href: "/guides/" }, { text: "The PTFA pack", href: "/deck/?urn=" + encodeURIComponent(m.urn) + "&view=ptfa" }] }));
    var acts = [];
    if (st && st.key === "in_deficit") acts.push("Review the recovery plan and its timetable with " + m.overseer);
    else if (st && st.key === "heading_for_deficit") acts.push("Ask for a three-year forecast showing when spending and income meet");
    acts.push("Agree which questions from this pack go to the head and finance lead");
    slides.push(actionsSlide(acts));
    slides.push(packSources(slides, c, m, [], ["DfE Financial Benchmarking and Insights Tool: " + (c.links.fbit || FBIT_HOME) + m.urn]));
    return finish(slides, { title: m.name + ": governors' finance pack", filename: fileSafe(m.name) + " - " + PACKS.governors.file + " - " + SITE + ".pptx",
      kind: "governors", view: "governors", pack: PACKS.governors.label, meta: slides[0].meta });
  }

  // Where the money comes from (kept as 'income': its totals and per-pupil figures share one year).
  function incomeSlide(m, c) {
    var s5 = slide("income", "chart", "Where the money comes from");
    var ly = latestRow(m, "total_income");
    var lyY = ly ? ly.y : snapshotYear(m);
    var src = srcOf(m, lyY);
    var useRow = ly && m.sx;
    // income_lines is the /data/s snapshot: use it only when it describes lyY, so total and pupils share a year.
    var snap5 = snapshotFor(m, lyY);
    function line5(key) {
      if (useRow && metric(ly, key) && isNum(metric(ly, key).v)) return { v: metric(ly, key).v, pp: metric(ly, key).pp };
      var v = snap5 ? m.incomeLines[key] : null;
      return isNum(v) ? { v: v, pp: perPupil(v, ly ? ly.pupils : m.pupilsLatest) } : null;
    }
    var g5 = line5("grant_funding"), sg5 = line5("self_generated"), sen5 = line5("sen_funding"), pp5 = line5("pupil_premium"), don5 = line5("donations_revenue");
    var let5 = line5("facilities_income"), cat5 = line5("catering_income");
    var cat = [];
    if (g5) cat.push({ y: "Government grants", v: round(g5.pp), suspect: false });
    if (sg5) cat.push({ y: "Self-generated income", v: round(sg5.pp), suspect: false });
    s5.chart = chart("bar", "£ per pupil", [{ key: "income_lines", name: lyY ? "Per pupil, " + lyY : "Per pupil", points: cat }]);
    if (g5) s5.figures.push(figure("grant_funding", "Government grants", g5.v, g5.pp, lyY, src));
    if (sg5) s5.figures.push(figure("self_generated", "Self-generated income (lettings, catering, donations)", sg5.v, sg5.pp, lyY, src));
    var within = [];
    if (sen5) within.push("special needs (SEN) funding " + both(sen5.pp, sen5.v, true));
    if (pp5) within.push("pupil premium " + both(pp5.pp, pp5.v, true));
    else if (m.academy && (g5 || sg5)) within.push("pupil premium: not reported in academy accounts");
    if (within.length) s5.bullets.push("Within the grants: " + within.join(" and ") + ", " + lyY + ", " + src + ".");
    var own = [];
    if (let5) own.push("lettings and facilities " + both(let5.pp, let5.v, true));
    if (cat5) own.push("catering " + both(cat5.pp, cat5.v, true));
    if (don5) own.push("donations and voluntary funds " + both(don5.pp, don5.v, true) + ", which can include money from a parents' association");
    if (own.length) s5.bullets.push("Within self-generated income: " + own.join("; ") + " (" + lyY + ", " + src + ").");
    if (!g5 && sg5) s5.bullets.push("Government grants for " + lyY + " aren't published as a separate figure.");
    if (!g5 && !sg5) {
      s5.lead = !ly && suspectYear(m, lyY)
        ? "This school's latest income breakdown (" + lyY + ") is marked as unusual, so it isn't used as a headline."
        : "A breakdown of this school's income isn't published for this year.";
    } else {
      s5.lead = "Most of a school's money is government grants, paid mainly per pupil.";
    }
    s5.note = framing(c, "pass_through_grants");
    s5.sources = schoolSources(m, c).slice(0, 1).concat([framingSource(c, "pass_through_grants")]).filter(Boolean);
    return s5;
  }

  function pressuresSlide(m, c) {
    var sl = slide("pressures", "note", "Pressures and context");
    var f = m.siteFlags;
    function add(text, line) {
      sl.bullets.push(text + (line ? " " + line.text : ""));
      if (line) sl.sources.push(ifsSource(c, line.page));
    }
    if (f.falling_rolls) {
      var fr = f.falling_rolls;
      add("Falling rolls: pupils went from " + fmtPupils(fr.from) + " to " + fmtPupils(fr.to) + (isNum(fr.change) ? " (" + signedPct(fr.change) + ")" : "") + " over the years shown.",
        ctxLine(c, "school", m.phaseKey === "secondary" ? "secondary_rolls" : "primary_rolls"));
    }
    if (f.pass_through) {
      var pt = f.pass_through;
      add("Pass-through grants: in " + pt.year + " income rose by " + fmtMoney(pt.income_rise) + " and staff costs by " + fmtMoney(pt.staff_rise) + ", so much of the rise paid for higher pension and National Insurance costs.",
        ctxLine(c, "school", "pass_through"));
    }
    if (f.high_send) {
      // series.py raises the flag for one of two reasons; the words follow the reason it gives. An EHCP share is
      // called above the national one only when that is the reason, since SEN funding can raise the flag alone.
      var hs = f.high_send, ehcp = isNum(hs.ehcp_pct) ? fmtPct(hs.ehcp_pct) + " of pupils have an education, health and care plan (EHCP)" : null;
      var latestY = m.rows.length ? m.rows[m.rows.length - 1].y : null;
      var sendText = hs.reason === "ehcp" && ehcp ? ehcp + ", above the national share."
        : "special needs (SEN) funding is " + (isNum(hs.sen_share) ? fmtPct(hs.sen_share * 100) + " of the school's income" + (latestY ? " in " + latestY : "") + ", " : "") +
          "a larger share than at most schools (the top quarter)" + (ehcp ? "; " + ehcp : "") + ".";
      add("Special needs: " + sendText, ctxLine(c, "council", "ehcp_share"));
      var first = ctxLine(c, "school", "send_first_6000");
      if (first) add("What it costs the school:", first);
    }
    if (!f.falling_rolls && !f.pass_through && !f.high_send) {
      sl.bullets.push("None of the site's pressure flags (falling rolls, pass-through grants, high special needs) is raised for this school's latest year.");
    }
    var costs = ctxLine(c, "school", "costs_outpaced_funding");
    if (costs) add("Costs nationally:", costs);
    var sp = latestRow(m, "total_expenditure");
    var ppLine = m.phaseKey === "primary" ? ctxLine(c, "school", "per_pupil_primary") : m.phaseKey === "secondary" ? ctxLine(c, "school", "per_pupil_secondary") : null;
    if (sp && ppLine) add("This school spent " + fmtExact(metric(sp, "total_expenditure").pp) + " per pupil in " + sp.y + " (" + srcOf(m, sp.y) + ").", ppLine);
    sl.lead = "Pressures the published figures point to, with national context from the IFS annual report on education spending.";
    var key = f.falling_rolls ? "falling_rolls" : f.pass_through ? "pass_through_grants" : f.high_send ? "send_pressure" : null;
    if (key) { sl.note = framing(c, key); sl.sources.push(framingSource(c, key)); }
    sl.sources = schoolSources(m, c).slice(0, 1).concat(sl.sources).filter(Boolean);
    return sl;
  }

  function councilSlide(m, c) {
    var A = m.area, E = m.england;
    var name = (A.ok && A.name) || m.council.name || "the council";
    var sl = slide("council", "chart", "The council picture");
    if (!A.ok) {
      sl.kind = "note";
      sl.lead = "Figures for " + name + " couldn't be loaded, so the council picture is left out.";
      sl.sources = [AREA_SOURCE];
      return sl;
    }
    var years = A.years.filter(function (y) { return A.by[y] && A.by[y].all.schools != null; });
    var ly = A.combinedLast && A.by[A.combinedLast] && A.by[A.combinedLast].all.schools != null ? A.combinedLast : years[years.length - 1];
    var S = ly ? A.by[ly].all : {}, ES = ly && E.ok && E.by[ly] ? E.by[ly].all : {};
    sl.chart = chart("line", "%", [
      { key: "area", name: name, points: years.map(function (y) { return { y: y, v: A.by[y].all.inDeficitPct, suspect: false }; }) },
      { key: "england", name: "England", points: years.map(function (y) { var e = E.ok && E.by[y] ? E.by[y].all.inDeficitPct : null; return { y: y, v: e, suspect: false }; }) }
    ]);
    if (S.inDeficit != null && S.schools != null) {
      sl.figures.push(figure("in_deficit_pct", "Schools in deficit in " + name, S.inDeficitPct, null, ly, AREA_SOURCE, "%"));
      sl.lead = "In " + ly + ", " + S.inDeficit + " of " + plural(S.schools, "school") + " in " + name + " with published figures (" + fmtPct(S.inDeficitPct) + ") were in deficit" +
        (ES.inDeficitPct != null ? "; across England it was " + fmtPct(ES.inDeficitPct) : "") + ".";
    } else {
      sl.lead = "There aren't enough schools with published figures in " + name + " to show a share in deficit.";
    }
    var dys = Object.keys(A.dsg).sort(), dl = null;
    for (var i = dys.length - 1; i >= 0; i--) { if (isNum(A.dsg[dys[i]].balance)) { dl = dys[i]; break; } }
    if (dl) {
      var d = A.dsg[dl];
      sl.figures.push(figure("dsg", "Council's " + DSG_NAME + " at 31 March" + (d.provisional ? " (provisional)" : ""), d.balance, d.pp, dl, DSG_SOURCE));
      sl.bullets.push(dsgDenominator(dl));
      if (d.balance < 0) sl.bullets.push("A negative " + DSG_NAME + " mostly reflects special needs (high needs) costs running ahead of the grant; it is the council's, not this school's money.");
    }
    var hn = ctxLine(c, "council", "high_needs_deficits");
    if (hn) sl.sources.push(ifsSource(c, hn.page));
    var cs = ly ? areaStat(A, ly, areaGroup(m), "spendPp") : null;
    if (cs) sl.bullets.push("Median spending among " + groupWords(cs.group, name) + ": " + fmtExact(cs.v) + " per pupil (" + ly + ", " + AREA_SOURCE + ").");
    sl.bullets.push("Council figures mix primary and secondary schools, so set them beside this school with care.");
    sl.note = [hn ? hn.text : "", c.dsgNote || ""].filter(Boolean).join(" ");
    sl.sources = [AREA_SOURCE, DSG_SOURCE].concat(sl.sources);
    return sl;
  }

  // ======================================================================
  // PTFA pack
  // ======================================================================
  function ptfaDeck(m, ctx) {
    var c = ctxOf(ctx);
    if (!m || !m.ok) return messageDeck(PACKS.ptfa.label, "This school's figures couldn't be loaded, so there is nothing to present yet.");
    var slides = [];
    var main = m.pta[0] || null;
    var last = lastPta(main);
    var guide = c.links.ptfa_guide || "/guides/ptfa/";
    var councilName = (m.area.ok && m.area.name) || m.council.name || "the council";
    var cmp = ptaComparison(m, last);
    var charitySource = main ? CHARITY_SOURCE + ", charity " + main.number + ": " + charityUrl(main.number) : CHARITY_SOURCE + ": " + REGISTER_HOME;

    var s1 = titleSlide(m, "ptfa", c, main ? main.name : m.name + ": parents' association", main ? ". Charity " + main.number + "." : "");
    s1.bullets = ["Parents' associations (PTAs, PTFAs, friends' groups) raise money for extras the budget doesn't stretch to.",
      "Their figures come from the " + CHARITY_SOURCE + "; the school's own figures come from the " + m.source + "."];
    s1.sources = [charitySource].concat(schoolSources(m, c).slice(0, 1));
    slides.push(s1);
    slides.push(summarySlide(m, c, "ptfa", main ? [ratePtaTrend(main), ratePtaAgainst(last, cmp.council, councilName + " schools", cmp.councilYear), ratePtaAgainst(last, cmp.england, "England", cmp.englandYear)] : []));

    if (!main) {
      var n1 = slide("not_found", "note", "No registered parents' association found");
      n1.lead = "No registered parents' association found for " + m.name + " on the " + CHARITY_SOURCE + ".";
      n1.bullets = [
        "Charities with an income of £5,000 or less a year don't have to register with the Charity Commission, so a smaller PTA may not appear on the register.",
        "A PTA may be registered under another name, such as 'Friends of " + m.name + "', or run as part of the school rather than as its own charity.",
        "Once its income is over £5,000 a year, a parents' association applies to the Charity Commission with its constitution, then files figures every year; those yearly figures are what this site reads.",
        "The school's own donations line may still show parents' giving (next slide)."
      ];
      n1.links = [{ text: "Search the charity register", href: REGISTER_HOME }, { text: "Does a PTA need to register?", href: guide + "#do-you-need-to-register" }];
      n1.sources = [CHARITY_SOURCE + ": " + REGISTER_HOME];
      slides.push(n1);
      var n2 = slide("donations", "note", "Parents' giving in the school's own accounts");
      var don = donationsLine(m);
      if (don) {
        n2.figures.push(figure("donations_revenue", "Donations and voluntary funds", don.v, don.pp, don.y, srcOf(m, don.y)));
        n2.lead = "The school's donations and voluntary funds line was " + both(don.pp, don.v) + " in " + don.y + " (" + srcOf(m, don.y) + "). It includes fundraising and parents' contributions paid into the school budget.";
      } else {
        n2.lead = "The school's donations figure isn't published for an unmarked year.";
      }
      n2.note = "This line can include money a parents' association passes to the school, which is why the two are never added together.";
      n2.sources = schoolSources(m, c).slice(0, 1);
      slides.push(n2);
    } else {
      var yrs = main.years;
      var s2 = slide("pta_money", "chart", "Money raised and spent");
      s2.chart = chart("bar", "£", [
        { key: "pta_income", name: "Income", points: yrs.map(function (e) { return { y: e.y, v: round(e.income), suspect: false }; }) },
        { key: "pta_spend", name: "Spending", points: yrs.map(function (e) { return { y: e.y, v: round(e.spend), suspect: false }; }) }
      ]);
      if (last) s2.figures.push(figure("pta_income", "Latest income", last.income, last.incomePp, ptaYearText(last), CHARITY_SOURCE));
      yrs.slice(-5).forEach(function (e) {
        s2.bullets.push(ptaLead(e) + ": raised " + both(e.incomePp, e.income, true) + (isNum(e.spend) ? ", spent " + both(e.spendPp, e.spend, true) : "") +
          (e.pupilsMarked ? " (no per-pupil figure: the school's " + e.y + " figures are marked as unusual)" : "") +
          (isNum(e.incomePp) && e.pupils ? ", with " + fmtPupils(e.pupils) + " pupils that year" : ""));
      });
      s2.lead = "The charity's own financial years" + (main.fye ? ", ending " + main.fye : "") + ", as filed with the " + CHARITY_SOURCE +
        ", each shown in the school year (September to August) its accounts end in.";
      if (main.confidence === "medium") s2.bullets.push("This association was matched with lower confidence: check the charity's name and area on the register.");
      if (m.pta.length > 1) s2.bullets.push("Also linked to the school: " + m.pta.slice(1).map(function (p) { return p.name + " (" + p.number + ")"; }).join(", ") + ".");
      s2.note = "Every return is counted in the school year (September to August) its accounts end in, for every kind of school, as the council and England medians count it" +
        (m.academy ? "." : "; the school's own budget years run April to March.") + " Per-pupil figures divide each year's total by the school's pupils in that same school year.";
      s2.links = [{ text: "Charity " + main.number + " on the register", href: charityUrl(main.number) }];
      s2.sources = [charitySource];
      slides.push(s2);
    }

    slides.push(ptaCompareSlide(m, c, last, councilName, cmp));

    if (main) {
      var sp = slide("pta_spent", "note", "What the money paid for");
      var part = main.partB && main.partB.length ? main.partB[main.partB.length - 1] : null;
      if (part) {
        sp.lead = "Spending lines the association reported for " + part.y + " (" + CHARITY_SOURCE + ").";
        part.lines.slice(0, 8).forEach(function (l) { sp.bullets.push(l[0] + ": " + fmtExact(l[1])); });
      } else {
        sp.lead = "The register's yearly figures give the total spent, not what it paid for.";
        sp.bullets = ["Charities with an income over £25,000 send their accounts too, which usually list what the money paid for; the association's treasurer or the head can say the rest.",
          last && isNum(last.spend) ? "Total spent in " + ptaWhen(last) + ": " + both(last.spendPp, last.spend) + " (" + CHARITY_SOURCE + ")." : "The total spent isn't published for the latest year."];
      }
      sp.bullets.push("Telling parents what last year's money paid for helps people give again.");
      sp.links = [{ text: "Charity " + main.number + " on the register", href: charityUrl(main.number) }];
      sp.sources = [charitySource];
      slides.push(sp);
    }

    // The school's finances in brief, with its own donations line beside (never added to) the association's income.
    var sf = slide("school_brief", "note", "The school's finances in brief");
    var st = m.status;
    if (st) {
      sf.status = { key: st.key, label: st.label, icon: st.icon };
      sf.lead = st.icon + " " + st.label + (st.year ? " (" + st.year + ", " + srcOf(m, st.year) + ")" : "") + ". " + (isHeld(m) ? heldWords(m) : budgetMessage(m)) + ".";
    } else {
      sf.lead = budgetMessage(m) + ".";
    }
    sf.ratings = [rateReserve(m)].filter(Boolean);
    if (inDeficitOrHeading(m)) sf.bullets = [deficitHelp(m, c).join(" ")];
    var don2 = donationsLine(m);
    if (last) sf.figures.push(figure("pta_income", "Parents' association income", last.income, last.incomePp, ptaYearText(last), CHARITY_SOURCE));
    if (don2) sf.figures.push(figure("donations_revenue", "School donations and voluntary funds", don2.v, don2.pp, don2.y, srcOf(m, don2.y)));
    sf.note = "Money a parents' association gives the school can also appear in the school's own donations income, so the two are shown side by side and never added together.";
    sf.sources = schoolSources(m, c).slice(0, 1).concat(main ? [charitySource] : []);
    if (inDeficitOrHeading(m)) { var fs = framingSource(c, "why_schools_go_into_deficit"); if (fs) sf.sources.push(fs); }
    slides.push(sf);

    var ideas = slide("ideas", "ideas", "Ideas and a target");
    var t = ptaTarget(m);
    ideas.lead = t ? t.message + "." : "Suggestions other parents' associations have found useful. Pick what fits your school.";
    if (t) ideas.figures.push(figure("pta_target", "Illustration: " + councilName + "'s median per pupil × this school's pupils", t.target, t.median, t.year, CHARITY_SOURCE + "; " + srcOf(m, t.year)));
    ideas.bullets = [
      "Claim Gift Aid on eligible donations from UK taxpayers: it adds 25p to every £1 given, at no cost to the giver.",
      "Ask parents and carers whether their employers offer match funding: many match what staff raise or volunteer for.",
      "Use the Gift Aid small donations scheme for cash and contactless gifts of £30 or less, where no declaration is needed (the association must also be claiming Gift Aid).",
      "Agree a wish-list with the school each year, so money goes where it helps most, and tell parents what it paid for.",
      main ? "Share the register figures with parents: seeing what last year paid for helps people give." :
        "If the association's income goes over £5,000 a year, it must register with the Charity Commission; the guide explains how."
    ];
    ideas.note = t ? ["The target is an illustration worked out with the same year's pupils (" + t.year + "), not a figure anyone has set.", t.note].filter(Boolean).join(" ") : "";
    ideas.links = [{ text: "Our guide for PTFAs", href: guide }];
    ideas.sources = ["HMRC Gift Aid and Gift Aid small donations scheme guidance (GOV.UK)", "Charity Commission: registering a charity (GOV.UK)"].concat(t ? [CHARITY_SOURCE + "; " + AREA_SOURCE] : []);
    slides.push(ideas);

    var first = ["Which three things would extra money help with most this year, and roughly what would each cost?",
      "How would the school like parents to hear what their money paid for?",
      "Is there a project where match funding or a grant could add to what parents raise?"];
    if (inDeficitOrHeading(m)) first.push("How does the school's budget plan change what would help most from parents' fundraising?");
    slides.push(questionsSlide(m, c, { title: "Questions for the school", first: first, max: 6,
      lead: "Questions about priorities for the head and governors, with context where the IFS report covers it.",
      links: [{ text: "Our guide for PTFAs", href: guide }, { text: "The governors' finance pack", href: "/deck/?urn=" + encodeURIComponent(m.urn) + "&view=governors" }] }));
    slides.push(actionsSlide(["Agree this year's wish-list with the head", "Check Gift Aid is claimed on eligible donations"]));
    slides.push(packSources(slides, c, m, main ? [{ text: "Charity " + main.number + " on the Charity Commission register", href: charityUrl(main.number) }] : [{ text: "Search the Charity Commission register", href: REGISTER_HOME }]));
    return finish(slides, { title: main ? main.name + ": PTFA pack" : m.name + ": PTFA pack", filename: fileSafe(m.name) + " - " + PACKS.ptfa.file + " - " + SITE + ".pptx",
      kind: "ptfa", view: "ptfa", pack: PACKS.ptfa.label, meta: slides[0].meta });
  }

  function ptaCompareSlide(m, c, last, councilName, cmp) {
    var sl = slide("pta_compare", "chart", "How the PTFA compares");
    cmp = cmp || ptaComparison(m, last);
    var yA = cmp.year, cy = cmp.councilYear, ey = cmp.englandYear, ca = cmp.council, en = cmp.england;
    var pts = [];
    if (last && isNum(last.incomePp)) pts.push({ y: "This PTA, " + last.y, v: round(last.incomePp), suspect: false });
    if (ca) pts.push({ y: councilName + ", " + cy, v: round(ca.v), suspect: false });
    if (en) pts.push({ y: "England, " + ey, v: round(en.v), suspect: false });
    sl.chart = chart("bar", "£ per pupil", [{ key: "pta_pp", name: "Parents' association income per pupil, school years to August (council and England: median)", points: pts }]);
    if (last && isNum(last.incomePp)) sl.figures.push(figure("pta_income", "This PTA", last.income, last.incomePp, ptaYearText(last), CHARITY_SOURCE));
    if (last && last.pupilsMarked) sl.bullets.push("The school's " + last.y + " figures are marked as unusual, so this association's income isn't set against its pupils for that year.");
    var groupText = cmp.councilN ? plural(cmp.councilN.v, "school") + " in " + councilName + " with a registered parents' association" : "schools in " + councilName + " with a registered parents' association";
    // The comparison in words, only where the median is for the association's own school year.
    var cw = ca && last && cy === last.y ? ratioWords(last.incomePp, ca.v) : null, ew = en && last && ey === last.y ? ratioWords(last.incomePp, en.v) : null;
    if (cw || ew) {
      sl.bullets.push(capital(ptaYearWords(last.y)) + ": this association raised " + fmtExact(last.incomePp) + " per pupil, " +
        [cw ? cw + " the median among " + groupText + " (" + fmtExact(ca.v) + ")" : null, ew ? ew + " the median across England (" + fmtExact(en.v) + ")" : null].filter(Boolean).join(", and ") +
        " (" + CHARITY_SOURCE + ").");
    }
    if (ca && !cw) {
      sl.bullets.push("Among " + groupText + ", the median raised was " + fmtExact(ca.v) + " per pupil" + (en && ey === cy && !ew ? "; across England " + fmtExact(en.v) : "") + " (" + ptaYearWords(cy) + ", " + CHARITY_SOURCE + ").");
    } else if (!ca) {
      sl.bullets.push("There aren't enough registered parents' associations in " + councilName + " with published figures to show a median.");
    }
    if (en && !ew && !(ca && !cw && ey === cy)) sl.bullets.push("Across England, the median raised was " + fmtExact(en.v) + " per pupil (" + ptaYearWords(ey) + ", " + CHARITY_SOURCE + ").");
    var differ = [ca ? ["The council median", cy] : null, en ? ["The England median", ey] : null].filter(function (x) { return x && last && x[1] !== last.y; });
    if (differ.length) {
      sl.bullets.push(differ.map(function (x) { return x[0] + " is for the " + ptaYearWords(x[1]); }).join("; ") + ", the latest published; this association's latest is the " + ptaYearWords(last.y) + ", so the years differ.");
    }
    var band = m.band != null ? (m.area.ok && m.area.ptaBands ? m.area.ptaBands[String(m.band)] : null) || (m.england.ok && m.england.ptaBands ? m.england.ptaBands[String(m.band)] : null) : null;
    var sbYear = null;
    if (band == null && yA && m.band != null) {
      var sb = cy ? areaStat(m.area, cy, "all", "ptaBands") : null;
      sbYear = cy;
      if (!sb && ey) { sb = areaStat(m.england, ey, "all", "ptaBands"); sbYear = ey; }
      band = sb && isObj(sb.v) ? sb.v[String(m.band)] : null;
    }
    var bandV = isNum(band) ? band : isObj(band) && isNum(band.median_pp) ? band.median_pp : null;
    if (bandV != null) {
      var bandYear = m.england.ptaYear ? "each school's latest charity year up to " + m.england.ptaYear : (sbYear || yA || "latest year");
      sl.bullets.push("Schools with a similar intake (free school meals band " + m.band + " of 5, where 1 has the fewest pupils eligible): median " + fmtExact(bandV) + " per pupil" +
        (isObj(band) && isNum(band.schools) ? " across " + plural(band.schools, "school") : "") + " (" + bandYear + ", " + CHARITY_SOURCE + ").");
    } else {
      sl.bullets.push("A comparison with schools of a similar intake (free school meals band) isn't available yet.");
    }
    var nb = m.nearby;
    var near = nb ? nb.schools.filter(function (r) { return isNum(r.pta_pp); }) : [];
    if (near.length) {
      sl.bullets.push("Nearby " + (nb.phase ? nb.phase.toLowerCase() + " " : "") + "schools' parents' associations: " + near.slice(0, 4).map(function (r) {
        return r.name + " " + fmtExact(r.pta_pp) + (r.pta_year ? " (" + ptaYearWords(r.pta_year) + ")" : "") + (r.pta_lower ? ", matched with lower confidence" : "");
      }).join("; ") + (near.length > 4 ? "; and " + (near.length - 4) + " more" : "") + ". Each is the association's own year.");
      if (nb.rank.pta_pp) sl.bullets.push("Among " + nb.rank.pta_pp.of + " nearby schools with a figure, counting this one, this association is " + (nb.rank.pta_pp.rank === 1 ? "the highest" : ordinal(nb.rank.pta_pp.rank) + " highest") + " per pupil.");
    } else if (!nb || !nb.schools.length) {
      sl.bullets.push("Nearby comparisons aren't published for this school yet.");
    } else {
      sl.bullets.push("No registered parents' association with published figures was found for the nearby schools listed.");
    }
    sl.lead = "What this parents' association raises per pupil, beside the typical figure in the council, across England and nearby.";
    sl.note = "Medians count only schools whose parents' association is registered and has filed figures; charities with an income of £5,000 or less needn't register.";
    sl.sources = [CHARITY_SOURCE, AREA_SOURCE];
    return sl;
  }

  // ======================================================================
  // School review pack (benchmarking)
  // ======================================================================
  function reviewDeck(m, ctx) {
    var c = ctxOf(ctx);
    if (!m || !m.ok) return messageDeck(PACKS.review.label, "This school's figures couldn't be loaded, so there is nothing to present yet.");
    var slides = [];
    var trend = pupilTrend(m);
    slides.push(titleSlide(m, "review", c));
    slides.push(summarySlide(m, c, "review", [rateBalance(m), rateReserve(m), rateSpendSimilar(m), rateSpendNearby(m), rateStaff(m, c), ratePupils(m)]));

    var sd = slide("dashboard", "table", "Benchmarking dashboard");
    sd.table = spendTable(m, true);
    sd.lead = "Spending per pupil in every category beside similar schools, nearby schools and the council.";
    sd.note = spendTableNotes(m, sd.table, true).join(" ");
    sd.sources = schoolSources(m, c).slice(0, 1).concat([AREA_SOURCE + " (similar, nearby and council medians)"]);
    slides.push(sd);

    var im = incomeSlide(m, c);
    im.id = "income_mix";
    im.title = "Income mix";
    var ly = latestRow(m, "total_income"), gcmp = [];
    if (ly && m.nearby && m.nearby.schools.length && isNum(m.nearby.medians.gov_pp)) gcmp.push("nearby schools " + fmtExact(m.nearby.medians.gov_pp) + " (" + m.nearby.year + ")");
    var cg = ly ? areaStat(m.area, ly.y, areaGroup(m), "grantPp") : null;
    if (cg) gcmp.push(groupWords(cg.group, (m.area.ok && m.area.name) || "the council") + " " + fmtExact(cg.v) + " (" + ly.y + ", primary and secondary together)");
    if (gcmp.length) im.bullets.push("Median government grants per pupil: " + gcmp.join("; ") + ".");
    slides.push(im);

    var tr = slide("trends", "table", "Eight-year trends");
    var trows = m.rows.slice(-8);
    tr.table = { caption: "Year by year: pupils, income and spending per pupil, in-year balance, reserve and status",
      columns: ["Year", "Pupils", "Income per pupil", "Spending per pupil", "In-year balance per pupil (total)", "Reserve per pupil (total)", "Status"],
      rows: trows.map(function (r) {
        var i = metric(r, "total_income"), e = metric(r, "total_expenditure"), b = metric(r, "in_year_balance"), v = metric(r, "revenue_reserve");
        var stKey = ORDER.indexOf(r.status) !== -1 ? r.status : null;
        return { suspect: r.suspect, cells: [cell(r.y + (r.suspect ? " " + MARK : "")), cell(isNum(r.pupils) ? fmtPupils(r.pupils) : null),
          cell(i && isNum(i.pp) ? fmtExact(i.pp) : null), cell(e && isNum(e.pp) ? fmtExact(e.pp) : null),
          cell(b && isNum(b.v) ? both(b.pp, b.v, true).replace(" per pupil", "") : null), cell(v && isNum(v.v) ? both(v.pp, v.v, true).replace(" per pupil", "") : null),
          stKey ? { text: ICONS[stKey] + " " + LABELS[stKey], status: stKey } : cell(null)] };
      }) };
    tr.lead = "Per-pupil figures use the same year's pupils; totals are in brackets. " + (m.academy ? "Academy years run September to August." : "Council-run years run April to March.");
    tr.note = [suspectNote(m) || "Figures are in cash, not adjusted for prices.", trustNote(m)].filter(Boolean).join(" ");
    tr.sources = schoolSources(m, c).slice(0, 1);
    slides.push(tr);

    var rt = slide("reserve_trajectory", "chart", "Reserve and recovery");
    rt.chart = chart("bar", "£ per pupil", [{ key: "revenue_reserve", name: "Reserve per pupil", points: points(m, "revenue_reserve", "pp") }]);
    var x = reserveShare(m);
    if (x) {
      rt.figures.push(figure("revenue_reserve", reserveLabel("Latest reserve", x.row), x.r.v, x.r.pp, x.row.y, srcOf(m, x.row.y)));
      rt.lead = (isHeld(m) ? budgetMessage(m) : reserveMessage(m)) + ".";
      var recent = trustedRows(m, "in_year_balance").slice(-3);
      var avg = recent.length ? recent.reduce(function (s, r) { return s + metric(r, "in_year_balance").v; }, 0) / recent.length : null;
      if (isHeld(m)) {
        rt.bullets.push("What helps: asking the trust how much of the pooled reserve is set aside for this school, and how it decides what the reserve is used for.");
      } else if (x.r.v < 0) {
        var need = -x.r.v / 3, pupilsNow = x.row.pupils, parts = [];
        if (isNum(pupilsNow) && pupilsNow > 0) parts.push(fmtExact(need / pupilsNow) + " per pupil at " + x.row.y + " numbers");
        if (x.inc && isNum(x.inc.v) && x.inc.v > 0) parts.push(fmtPct(need / x.inc.v * 100) + " of " + x.row.y + " income");
        rt.bullets.push("Illustration: clearing a deficit of " + fmtExact(-x.r.v) + " over three years would take a surplus of about " + fmtExact(need) + " a year" +
          (parts.length ? " (" + parts.join(", ") + ")" : "") + ". The real plan is agreed with " + m.overseer + ".");
        rt.bullets.push(deficitHelp(m, c)[1]);
        rt.deficitNote = deficitHelp(m, c)[0];
        var fs = framingSource(c, "why_schools_go_into_deficit");
        if (fs) rt.sources.push(fs);
      } else if (isNum(avg) && avg < 0) {
        rt.bullets.push("Illustration: at the average in-year balance of the last " + plural(recent.length, "year") + " (" + fmtExact(avg) + " a year), the reserve would last about " +
          (Math.round(x.r.v / -avg * 10) / 10) + " years. A forecast from the school is the real guide.");
      } else {
        rt.bullets.push("The reserve hasn't been drawn on in recent years; a plan for what it is kept for helps governors judge whether it is the right size.");
      }
    } else {
      rt.lead = noHeadline(m, "revenue_reserve", "Reserve figures for this school");
    }
    rt.note = [rt.deficitNote, suspectNote(m), trustNote(m), rt.deficitNote ? "" : framing(c, "one_deficit_year")].filter(Boolean).join(" ");
    delete rt.deficitNote;
    rt.sources = schoolSources(m, c).slice(0, 1).concat(rt.sources, [framingSource(c, "one_deficit_year")]).filter(Boolean);
    slides.push(rt);

    nearbySlides(m, c).forEach(function (s) { slides.push(s); });

    if (m.similarSchools.length) {
      var sm = slide("similar_schools", "note", "The most similar schools");
      var smm = m.similarMeta;
      sm.lead = "The schools " + SITE + " counts as most like this one, by name. Their figures are on their own pages." +
        (smm && isNum(smm.peers) && smm.peers > 0 ? " The medians in this pack use " + simWords(m) + (smm.method ? ": " + smm.method : ".") : "");
      sm.bullets = m.similarSchools.slice(0, 5).map(function (s) { return s.name; });
      sm.links = m.similarSchools.slice(0, 5).filter(function (s) { return s.p; }).map(function (s) { return { text: s.name, href: s.p }; });
      sm.sources = [AREA_SOURCE + " (similar schools)"];
      slides.push(sm);
    }
    slides.push(questionsSlide(m, c, { falling: trend && trend.falling,
      first: ["Which two spending lines are furthest from similar schools, and is there a reason the school is comfortable with?"] }));
    slides.push(actionsSlide(["Look at the two categories furthest from similar schools and ask why", "Set a date to check progress against this review"]));
    slides.push(packSources(slides, c, m, [], ["DfE Financial Benchmarking and Insights Tool: " + (c.links.fbit || FBIT_HOME) + m.urn]));
    return finish(slides, { title: m.name + ": school review pack", filename: fileSafe(m.name) + " - " + PACKS.review.file + " - " + SITE + ".pptx",
      kind: "review", view: "review", pack: PACKS.review.label, meta: slides[0].meta });
  }

  // Build the pack a view names; null for compare and area views.
  function packDeck(view, m, ctx) {
    var v = packView(view);
    return v === "ptfa" ? ptfaDeck(m, ctx) : v === "review" ? reviewDeck(m, ctx) : v === "governors" ? schoolDeck(m, ctx) : null;
  }

  // ---------------------------------------------------------------- notes and actions kept in this browser
  function notesKey(id, view) { return NOTES_PREFIX + String(id == null ? "" : id) + ":" + (packView(view) || String(view || "")); }
  function loadSaved(storage, key) {
    var out = { notes: {}, actions: null, meeting: null, date: null };
    try {
      var raw = storage && typeof storage.getItem === "function" ? storage.getItem(key) : null;
      var d = raw ? JSON.parse(raw) : null;
      if (isObj(d)) {
        if (isObj(d.notes)) Object.keys(d.notes).forEach(function (k) { if (typeof d.notes[k] === "string") out.notes[k] = d.notes[k]; });
        if (Array.isArray(d.actions)) {
          out.actions = d.actions.filter(isObj).map(function (a) { return { action: String(a.action || ""), owner: String(a.owner || ""), by: String(a.by || "") }; });
        }
        if (typeof d.meeting === "string") out.meeting = d.meeting;
        if (typeof d.date === "string") out.date = d.date;
      }
    } catch (e) { /* storage blocked or unreadable: start empty */ }
    return out;
  }
  function saveSaved(storage, key, saved) {
    try {
      if (!storage || typeof storage.setItem !== "function") return false;
      storage.setItem(key, JSON.stringify(saved));
      return true;
    } catch (e) { return false; }
  }
  // Saved notes, actions and the meeting line go into the model, so print, screen and PowerPoint agree.
  function applySaved(deck, saved) {
    if (!deck || !deck.slides || !isObj(saved)) return deck;
    deck.slides.forEach(function (sl) {
      sl.notes = saved.notes && typeof saved.notes[sl.id] === "string" ? saved.notes[sl.id] : (sl.notes || "");
      if (sl.kind === "actions" && Array.isArray(saved.actions)) sl.actions = saved.actions.map(function (a) { return { action: a.action, owner: a.owner, by: a.by }; });
      if (sl.meta) {
        if (typeof saved.meeting === "string") sl.meta.preparedFor = saved.meeting;
        if (typeof saved.date === "string") sl.meta.date = saved.date;
      }
    });
    return deck;
  }
  function speakerNotes(sl) {
    var notes = String(sl.notes || "").trim();
    var sources = (sl.sources && sl.sources.length ? sl.sources : ["Source: " + SITE]).join("\n");
    return notes ? notes + "\n\nSources:\n" + sources : sources;
  }
  function deckText(deck) {
    var out = [];
    (deck && deck.slides || []).forEach(function (sl) {
      out.push(sl.title, sl.lead, sl.note);
      (sl.messages || []).forEach(function (t) { out.push(t); });
      (sl.ratings || []).forEach(function (r) { out.push(r.text, r.why); });
      sl.bullets.forEach(function (b) { out.push(b); });
      sl.figures.forEach(function (f) { out.push(f.label, f.text); });
      if (sl.table) { out.push(sl.table.caption); sl.table.columns.forEach(function (h) { out.push(h); }); sl.table.rows.forEach(function (r) { r.cells.forEach(function (x) { out.push(x.text); }); }); }
    });
    return out.filter(Boolean).join("\n");
  }

  // ======================================================================
  // Compare deck: 2 to 6 schools
  // ======================================================================
  function compareDeck(list, ctx) {
    var c = ctxOf(ctx);
    var ms = (Array.isArray(list) ? list : []).map(function (x) {
      if (x && x.rows && typeof x.ok === "boolean") return x;
      if (x && (x.s || x.sx)) return adapt(x.s, x.sx, x.council, x.england);
      return adapt(x, null, null, null);
    }).filter(function (m) { return m.ok; });
    if (ms.length < 2 || ms.length > 6) {
      return messageDeck("Compare schools", "Choose between 2 and 6 schools to compare (this link has " + ms.length + ").",
        [{ text: "Pick schools to compare", href: "/compare/" }]);
    }
    // Names needn't be unique, and chart categories are labels, so a shared name carries the URN.
    var names = ms.map(function (m) {
      var twin = ms.some(function (o) { return o !== m && o.name === m.name; });
      return twin ? m.name + " (URN " + m.urn + ")" : m.name;
    });
    var slides = [];
    var s1 = slide("title", "title", "Comparing " + ms.length + " schools");
    s1.lead = names.join(", ");
    ms.forEach(function (m, i) {
      var r = latestRow(m, "total_income");
      s1.bullets.push(names[i] + (m.council.name ? ", " + m.council.name : "") + (r && isNum(r.pupils) ? ": " + fmtPupils(r.pupils) + " pupils, " + r.y + ", " + srcOf(m, r.y) : ""));
    });
    s1.note = "Each school's latest published year is used, so years can differ between schools.";
    s1.sources = ms.map(function (m, i) { return names[i] + ": " + schoolSources(m, c)[0]; });
    slides.push(s1);

    function measure(id, title, key, label) {
      var sl = slide(id, "chart", title);
      var pts = [], years = {};
      ms.forEach(function (m, i) {
        var r = latestRow(m, key);
        var cell = r ? metric(r, key) : null;
        pts.push({ y: names[i], v: cell ? round(cell.pp) : null, suspect: false });
        if (r) years[r.y] = 1;
        if (cell) sl.figures.push(figure(key, names[i], cell.v, cell.pp, r.y, srcOf(m, r.y)));
        else sl.bullets.push(names[i] + ": " + label.toLowerCase() + " isn't published yet.");
      });
      sl.chart = chart("bar", "£ per pupil", [{ key: key, name: label + " per pupil", points: pts }]);
      sl.lead = label + " per pupil, latest published year for each school.";
      if (Object.keys(years).length > 1) sl.note = "The schools' latest years differ (" + Object.keys(years).sort().join(", ") + "), so compare with care.";
      sl.sources = s1.sources.slice();
      return sl;
    }
    slides.push(measure("income", "Income per pupil", "total_income", "Income"));
    slides.push(measure("spending", "Spending per pupil", "total_expenditure", "Spending"));
    var rs = measure("reserve", "Reserve per pupil", "revenue_reserve", "Reserve");
    slides.push(rs);

    var s5 = slide("status", "status-list", "Budget status");
    var anyDeficit = false;
    s5.statuses = [];
    ms.forEach(function (m, i) {
      if (!m.status) { s5.bullets.push(names[i] + ": no full year of figures to assess yet."); return; }
      if (m.status.key === "in_deficit" || m.status.key === "heading_for_deficit") anyDeficit = true;
      s5.statuses.push({ key: m.status.key, label: m.status.label, icon: m.status.icon, name: names[i] });
      s5.bullets.push(m.status.icon + " " + m.status.label + ": " + names[i] + (m.status.reason ? ". " + m.status.reason : "") + (m.status.year ? " (" + m.status.year + ", " + srcOf(m, m.status.year) + ")" : ""));
    });
    s5.lead = "Each school's status from its latest full year.";
    if (anyDeficit) {
      s5.note = "Why this happens: " + (framing(c, "why_schools_go_into_deficit") || "most of a school's money goes on staff, so rising costs or falling rolls squeeze budgets quickly.") +
        " What helps: a recovery plan agreed with the council or trust, and budget forecasts governors see often.";
      s5.sources = [framingSource(c, "why_schools_go_into_deficit")].filter(Boolean).concat(s1.sources);
    } else {
      s5.sources = s1.sources.slice();
    }
    slides.push(s5);

    var s6 = slide("pupils", "chart", "Pupils");
    var pp6 = [];
    ms.forEach(function (m, i) {
      var r = lastTrusted(m, function (row) { return isNum(row.pupils); });
      pp6.push({ y: names[i], v: r ? Math.round(r.pupils * 10) / 10 : null, suspect: false });
      if (r) s6.figures.push(figure("pupils", names[i], r.pupils, null, r.y, srcOf(m, r.y), "pupils"));
    });
    s6.chart = chart("bar", "pupils", [{ key: "pupils", name: "Pupils", points: pp6 }]);
    s6.lead = "Pupil numbers drive most of a school's funding.";
    s6.sources = s1.sources.slice();
    slides.push(s6);

    slides.push(sourcesSlide(slides, c));
    slides.forEach(function (x, i) { x.n = i + 1; });
    var title = "Comparing " + ms.length + " schools";
    return { title: title, filename: "Compare " + ms.length + " schools - " + SITE + ".pptx", kind: "compare", slides: slides };
  }

  // ======================================================================
  // Area deck: council or constituency
  // ======================================================================
  function areaDeck(a, england, ctx) {
    var c = ctxOf(ctx);
    var m = adapt(null, null, a, england);
    var A = m.area, E = m.england;
    if (!A.ok) return messageDeck("Area presentation", "This area's figures couldn't be loaded, so there is nothing to present yet.");
    var slides = [];
    var typeWord = A.type === "council" ? "Council" : A.type === "constituency" ? "Constituency" : A.type === "region" ? "Region" : "Area";
    var years = A.years.filter(function (y) { return A.by[y] && A.by[y].all.schools != null; });
    var ly = years[years.length - 1] || A.years[A.years.length - 1] || null;
    var S = ly && A.by[ly] ? A.by[ly].all : {};
    var ES = ly && E.ok && E.by[ly] ? E.by[ly].all : {};

    var s1 = slide("title", "title", A.name);
    s1.lead = typeWord + " presentation" + (ly ? ", " + ly : "") + (S.schools != null ? ": " + plural(S.schools, "school") : "") +
      (ly && isNum(A.pupils[ly]) ? ", " + fmtPupils(A.pupils[ly]) + " pupils" : "") + ".";
    if (ly && isNum(A.pupils[ly])) s1.figures.push(figure("pupils", "Pupils", A.pupils[ly], null, ly, AREA_SOURCE, "pupils"));
    if (S.schools != null) s1.figures.push(figure("schools", "Schools with published figures", S.schools, null, ly, AREA_SOURCE, "count"));
    s1.bullets.push("Figures cover state schools with a published full-year return: council-run schools (CFR) and academies (AAR).");
    s1.note = "Where an area has fewer than 5 schools with figures, its medians are left out rather than shown from too few schools.";
    s1.sources = [AREA_SOURCE];
    slides.push(s1);

    var s2 = slide("deficits", "chart", "Schools in deficit over the years");
    s2.chart = chart("line", "%", [
      { key: "area", name: A.name, points: years.map(function (y) { return { y: y, v: A.by[y].all.inDeficitPct, suspect: false }; }) },
      { key: "england", name: "England", points: years.map(function (y) { var e = E.ok && E.by[y] ? E.by[y].all.inDeficitPct : null; return { y: y, v: e, suspect: false }; }) }
    ]);
    if (S.inDeficit != null && S.schools != null) {
      s2.figures.push(figure("in_deficit_pct", "Share of schools in deficit", S.inDeficitPct, null, ly, AREA_SOURCE, "%"));
      s2.lead = "In " + ly + ", " + S.inDeficit + " of " + plural(S.schools, "school") + " (" + fmtPct(S.inDeficitPct) + ") were in deficit" +
        (S.heading ? ", and " + S.heading + " more were heading for deficit" : "") + (ES.inDeficitPct != null ? "; across England it was " + fmtPct(ES.inDeficitPct) : "") + ".";
    } else {
      s2.lead = "There aren't enough schools with published figures here to show a share.";
    }
    // Held by the trust is listed on its own, never inside the deficit or tight counts (contract C4).
    var counts = ORDER.filter(function (k) { return A.statuses[k]; }).map(function (k) { return ICONS[k] + " " + LABELS[k] + ": " + A.statuses[k]; });
    if (counts.length) s2.bullets.push("Latest status of each school: " + counts.join(" · ") + ".");
    s2.bullets.push("What helps: recovery plans agreed early, budgets that plan for falling rolls, and governors seeing forecasts often.");
    s2.note = "Why this happens: " + (framing(c, "why_schools_go_into_deficit") || "most of a school's money goes on staff, so rising costs or falling rolls squeeze budgets quickly.");
    s2.sources = [AREA_SOURCE, framingSource(c, "why_schools_go_into_deficit")].filter(Boolean);
    slides.push(s2);

    var s3 = slide("medians", "chart", "Per pupil, compared with England");
    var keys = [["incomePp", "Income"], ["spendPp", "Spending"], ["grantPp", "Government grants"], ["reservePp", "Reserve"]];
    s3.chart = chart("bar", "£ per pupil", [
      { key: "area", name: A.name + " (median)", points: keys.map(function (k) { return { y: k[1], v: round(S[k[0]]), suspect: false }; }) },
      { key: "england", name: "England (median)", points: keys.map(function (k) { return { y: k[1], v: round(ES[k[0]]), suspect: false }; }) }
    ]);
    keys.forEach(function (k) {
      if (S[k[0]] == null) return;
      var w = ES[k[0]] != null ? ratioWords(S[k[0]], ES[k[0]]) : null;
      s3.bullets.push(k[1] + ": median " + fmtExact(S[k[0]]) + " per pupil here" +
        (ES[k[0]] != null ? (w ? ", " + w + " England's " + fmtExact(ES[k[0]]) : ", " + fmtExact(ES[k[0]]) + " across England") : "") + " (" + ly + ", " + AREA_SOURCE + ").");
    });
    if (!s3.bullets.length) s3.bullets.push("There aren't enough schools with published figures here to show medians.");
    s3.lead = "The middle school's figure (the median), so one very large or very small school doesn't skew it.";
    s3.note = framing(c, "funding_vs_spending_per_pupil");
    s3.sources = [AREA_SOURCE, framingSource(c, "funding_vs_spending_per_pupil")].filter(Boolean);
    slides.push(s3);

    if (A.type === "council") {
      var s4 = slide("dsg", "chart", DSG_NAME);
      var dys = Object.keys(A.dsg).sort();
      s4.chart = chart("bar", "£ per pupil", [{ key: "dsg_pp", name: DSG_NAME + " per pupil", points: dys.map(function (y) { return { y: y, v: round(A.dsg[y].pp), suspect: A.dsg[y].provisional }; }) }]);
      var dl = null;
      for (var i = dys.length - 1; i >= 0; i--) { if (isNum(A.dsg[dys[i]].balance)) { dl = dys[i]; break; } }
      if (dl) {
        var d = A.dsg[dl];
        s4.figures.push(figure("dsg", DSG_NAME + " at 31 March" + (d.provisional ? " (provisional)" : ""), d.balance, d.pp, dl, DSG_SOURCE));
        s4.lead = "The council's " + DSG_NAME + " was " + both(d.pp, d.balance) + " at the end of " + dl + (d.provisional ? ", provisional" : "") + " (" + DSG_SOURCE + ")" +
          (d.balance < 0 ? ". A negative balance mostly reflects special needs (high needs) costs running ahead of the grant." : ".");
        s4.bullets.push(dsgDenominator(dl));
      } else {
        s4.lead = "The council's " + DSG_NAME + " isn't published for these years.";
      }
      var hn = ctxLine(c, "council", "high_needs_deficits");
      if (hn) s4.bullets.push(hn.text);
      var tu = ctxLine(c, "council", "high_needs_top_up");
      if (tu) s4.bullets.push(tu.text);
      s4.note = c.dsgNote || "";
      s4.sources = [DSG_SOURCE].concat(hn ? [ifsSource(c, hn.page)] : [], tu ? [ifsSource(c, tu.page)] : []);
      slides.push(s4);
    }

    var s5 = slide("pta", "note", "Parents' associations");
    if (S.ptaPp != null) {
      s5.figures.push(figure("pta_pp_median", "Median raised by a registered parents' association", null, S.ptaPp, ly, CHARITY_SOURCE + "; " + SITE));
      s5.lead = "Among " + (S.ptaSchools != null ? plural(S.ptaSchools, "school") : "schools") + " here with a registered parents' association, the median raised was " +
        fmtExact(S.ptaPp) + " per pupil (" + ly + ", " + CHARITY_SOURCE + ")" + (ES.ptaPp != null ? "; across England it was " + fmtExact(ES.ptaPp) + "." : ".");
    } else {
      s5.lead = "There aren't enough registered parents' associations here with published figures to show a median.";
    }
    if (S.donationsPp != null) {
      s5.figures.push(figure("donations_pp_median", "Median school donations income", null, S.donationsPp, ly, AREA_SOURCE));
      s5.bullets.push("Schools' own donations and voluntary funds: median " + fmtExact(S.donationsPp) + " per pupil (" + ly + ", " + AREA_SOURCE + ").");
    }
    s5.bullets.push("PTA income and school donations can overlap (money a PTA gives the school can appear in both), so they are never added together.");
    s5.bullets.push("Charities with an income of £5,000 or less a year don't have to register, so smaller parents' associations aren't counted.");
    s5.sources = [CHARITY_SOURCE, AREA_SOURCE];
    s5.links = [{ text: "Our guide for PTFAs", href: c.links.ptfa_guide || "/guides/ptfa/" }];
    slides.push(s5);

    slides.push(sourcesSlide(slides, c, A.path ? [SITE + " page: " + (c.links.base || "") + A.path] : []));
    slides.forEach(function (x, i) { x.n = i + 1; });
    return { title: A.name + ": school money", filename: fileSafe(A.name) + " - " + SITE + ".pptx", kind: "area", slides: slides };
  }

  // ======================================================================
  // Keyboard stepping and PowerPoint
  // ======================================================================
  function nextIndex(i, key, n) {
    if (!(n > 0)) return 0;
    i = Math.min(Math.max(0, Math.floor(i) || 0), n - 1);
    if (key === "ArrowRight" || key === " " || key === "Space" || key === "Spacebar" || key === "PageDown") return Math.min(i + 1, n - 1);
    if (key === "ArrowLeft" || key === "PageUp") return Math.max(i - 1, 0);
    if (key === "Home") return 0;
    if (key === "End") return n - 1;
    return i;
  }
  function hex(color, fallback) {
    var s = String(color == null ? "" : color).trim();
    var m3 = /^#([0-9a-f])([0-9a-f])([0-9a-f])$/i.exec(s);
    if (m3) return (m3[1] + m3[1] + m3[2] + m3[2] + m3[3] + m3[3]).toUpperCase();
    var m6 = /^#([0-9a-f]{6})$/i.exec(s);
    if (m6) return m6[1].toUpperCase();
    var rgb = /^rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)/i.exec(s);
    if (rgb) {
      return [rgb[1], rgb[2], rgb[3]].map(function (x) { var h = Math.min(255, +x).toString(16); return h.length < 2 ? "0" + h : h; }).join("").toUpperCase();
    }
    return fallback;
  }
  // Same values, same labels as the model; marked (suspect) years carry the marker in their label.
  // Series line up by label and by how often that label has come up, so a repeated label keeps every point.
  function chartData(ch) {
    if (!ch || !ch.series || !ch.series.length) return [];
    var cats = [], labels = [];
    var keyed = ch.series.map(function (s) {
      var seen = Object.create(null), byKey = Object.create(null);
      s.points.forEach(function (p) {
        seen[p.y] = (seen[p.y] || 0) + 1;
        var k = p.y + "\u0000" + seen[p.y];
        byKey[k] = p;
        if (cats.indexOf(k) === -1) { cats.push(k); labels.push(p.y); }
      });
      return byKey;
    });
    return ch.series.map(function (s, si) {
      var byKey = keyed[si];
      return {
        name: s.name,
        labels: cats.map(function (k, i) { return byKey[k] && byKey[k].suspect ? labels[i] + " " + MARK : labels[i]; }),
        values: cats.map(function (k) { return byKey[k] && isNum(byKey[k].v) ? byKey[k].v : null; })
      };
    });
  }
  function buildPptx(deck, PptxGenJS, palette) {
    var p = isObj(palette) ? palette : {};
    var col = {
      paper: hex(p.paper, "FFFFFF"), ink: hex(p.ink, "222222"), ink2: hex(p["ink-2"] || p.ink2, "555555"), line: hex(p.line, "CCCCCC"),
      grid: hex(p.grid, "E5E5E5"), accent: hex(p.pack || p.accent, "555555"),
      series: [hex(p.c1, "333333"), hex(p.c2, "777777"), hex(p.c3, "999999"), hex(p.c4, "BBBBBB")],
      status: {}
    };
    // Held by the trust is a neutral grey wherever the page doesn't define --held.
    ORDER.forEach(function (k) { col.status[k] = hex(p[TONES[k]], k === HELD ? "6B7280" : col.ink); });
    function toneColor(r) { return hex(p[r.tone], r.tone === "held" ? "6B7280" : col.ink); }
    function cellText(x) { return x && x.text != null ? String(x.text) : "—"; }
    var pptx = new PptxGenJS();
    pptx.layout = "LAYOUT_16x9";
    pptx.title = deck.title;
    pptx.author = SITE;
    pptx.company = "Schools in Reach";
    var types = pptx.ChartType || pptx.charts || {};
    var total = deck.slides.length;
    deck.slides.forEach(function (sl, idx) {
      var s = pptx.addSlide();
      s.background = { color: col.paper };
      s.addText(sl.title, { x: 0.4, y: 0.2, w: 9.2, h: 0.6, fontSize: 24, bold: true, color: col.ink, fontFace: "Arial", fit: "shrink" });
      var y = 0.8;
      if (sl.status) {
        s.addText(sl.status.icon + " " + sl.status.label, { x: 0.4, y: y, w: 3, h: 0.35, fontSize: 13, bold: true, color: col.status[sl.status.key] || col.ink, fontFace: "Arial" });
        y += 0.35;
      }
      if (sl.meta) {
        s.addText("Prepared for: " + (sl.meta.preparedFor || "") + " · " + (sl.meta.date || ""), { x: 0.4, y: y, w: 9.2, h: 0.35, fontSize: 13, color: col.accent, fontFace: "Arial", bold: true });
        y += 0.4;
      }
      if (sl.lead) {
        s.addText(sl.lead, { x: 0.4, y: y, w: 9.2, h: 0.6, fontSize: 13, color: col.ink, fontFace: "Arial", valign: "top", fit: "shrink" });
        y += 0.65;
      }
      var hasChart = !!(sl.chart && sl.chart.series && sl.chart.series.length);
      var canTable = typeof s.addTable === "function";
      var rows = null;
      if (sl.kind === "actions") {
        rows = [sl.columns || ["Action or decision", "Owner", "By when"]].concat((sl.actions || []).map(function (a) { return [a.action || "", a.owner || "", a.by || ""]; }));
      } else if (sl.table) {
        rows = [sl.table.columns].concat(sl.table.rows.map(function (r) { return r.cells.map(cellText); }));
      }
      if (rows && canTable) {
        var head = { bold: true, color: "FFFFFF", fill: { color: col.accent } };
        var tableRows = rows.map(function (r, ri) {
          return r.map(function (t, ci) {
            var o = ri === 0 ? head : {};
            var src = ri > 0 && sl.table ? sl.table.rows[ri - 1].cells[ci] : null;
            if (src && (src.rag || src.status)) o = { bold: true, color: src.rag ? toneColor(src.rag) : col.status[src.status] || col.ink };
            return { text: String(t), options: o };
          });
        });
        var rh = sl.kind === "actions" ? 0.4 : 0.28;
        s.addTable(tableRows, { x: 0.4, y: y, w: 9.2, fontSize: rows[0].length > 6 ? 8 : 10, fontFace: "Arial", color: col.ink, border: { type: "solid", pt: 0.5, color: col.line },
          rowH: rh, autoPage: false });
        y += Math.min(rh * rows.length, 4.55 - y) + 0.1;
      }
      var paras = [];
      (sl.messages || []).forEach(function (t, i) { paras.push({ text: (i + 1) + ". " + t, options: { bold: true, color: col.ink, fontSize: 13, breakLine: true } }); });
      (sl.ratings || []).forEach(function (r) {
        paras.push({ text: r.icon + " " + r.word + " · ", options: { bold: true, color: toneColor(r) } });
        paras.push({ text: r.measure + (r.value ? ": " + r.value : ""), options: { color: col.ink, breakLine: true } });
      });
      sl.figures.forEach(function (f) {
        paras.push({ text: f.label + ": ", options: { bold: true, color: col.ink } });
        paras.push({ text: f.text, options: { color: col.ink, breakLine: true } });
      });
      sl.bullets.forEach(function (b) { paras.push({ text: b, options: { bullet: true, color: col.ink, breakLine: true } }); });
      if (rows && !canTable) rows.forEach(function (r) { paras.push({ text: r.join(" | "), options: { color: col.ink, breakLine: true } }); });
      (sl.links || []).forEach(function (l) {
        var href = /^https?:/.test(l.href) ? l.href : (deck.base || "https://money.schoolsinreach.com") + l.href;
        paras.push({ text: l.text, options: { hyperlink: { url: href }, color: col.accent, breakLine: true } });
      });
      var bodyH = 4.55 - y;
      if (paras.length && bodyH > 0.2) {
        s.addText(paras, { x: 0.4, y: y, w: hasChart ? 4.5 : 9.2, h: bodyH, fontSize: 11, fontFace: "Arial", valign: "top", fit: "shrink", paraSpaceAfter: 3 });
      }
      if (hasChart && bodyH > 0.2) {
        var ch = sl.chart;
        var type = ch.type === "line" ? (types.line || "line") : (types.bar || "bar");
        var fmt = ch.unit === "%" ? '0.0"%"' : ch.unit === "pupils" ? "#,##0.#" : "£#,##0";
        var nPoints = ch.series.reduce(function (t, x) { return t + x.points.length; }, 0);
        s.addChart(type, chartData(ch), {
          x: 5.05, y: y, w: 4.55, h: bodyH, chartColors: col.series.slice(0, Math.max(ch.series.length, 1)),
          barDir: "col", barGrouping: ch.type === "stack" ? "stacked" : "clustered", overlap: ch.type === "stack" ? 100 : undefined,
          showLegend: ch.series.length > 1, legendPos: "b", legendFontSize: 9, legendColor: col.ink2,
          catAxisLabelColor: col.ink2, valAxisLabelColor: col.ink2, catAxisLabelFontSize: 9, valAxisLabelFontSize: 9,
          valAxisLabelFormatCode: fmt, valGridLine: { color: col.grid, size: 0.5 }, catGridLine: { style: "none" },
          showValue: ch.type === "bar" && nPoints <= 12, dataLabelFormatCode: fmt, dataLabelFontSize: 8, dataLabelColor: col.ink,
          lineSize: 2, lineDataSymbol: "circle", lineDataSymbolSize: 6, altText: ch.alt
        });
      }
      if (sl.note) s.addText(sl.note, { x: 0.4, y: 4.6, w: 9.2, h: 0.65, fontSize: 9, color: col.ink2, fontFace: "Arial", valign: "top", fit: "shrink" });
      s.addText(SITE + " · " + deck.title + " · " + (idx + 1) + " / " + total, { x: 0.4, y: 5.28, w: 9.2, h: 0.25, fontSize: 8, color: col.ink2, fontFace: "Arial" });
      s.addNotes(speakerNotes(sl));
    });
    return pptx.writeFile({ fileName: deck.filename });
  }

  var API = {
    adapt: adapt, schoolDeck: schoolDeck, governorsDeck: schoolDeck, ptfaDeck: ptfaDeck, reviewDeck: reviewDeck, packDeck: packDeck, packView: packView,
    compareDeck: compareDeck, areaDeck: areaDeck,
    nextIndex: nextIndex, buildPptx: buildPptx, chartData: chartData, withWarnings: withWarnings, fmtExact: fmtExact, fmtPupils: fmtPupils, fmtDate: fmtDate,
    summaryMessages: summaryMessages, rag: rag, ptaTarget: ptaTarget, notesKey: notesKey, loadSaved: loadSaved, saveSaved: saveSaved, applySaved: applySaved,
    speakerNotes: speakerNotes, deckText: deckText, ratioWords: ratioWords, charityUrl: charityUrl, ptaYearWords: ptaYearWords,
    hex: hex, PPTX_URL: PPTX_URL, LABELS: LABELS, ICONS: ICONS, ORDER: ORDER, TONES: TONES, RAG: RAG, PACKS: PACKS
  };
  root.MoneyDeck = API;
  if (typeof document === "undefined") return;

  // ======================================================================
  // DOM wiring
  // ======================================================================
  var appEl = document.getElementById("deck-app");
  if (!appEl) return;
  var NS = "http://www.w3.org/2000/svg";
  var msgEl = document.getElementById("deck-msg"), liveEl = document.getElementById("deck-live"), countEl = document.getElementById("deck-count");
  var toolbar = document.querySelector(".deck-toolbar");
  var state = { deck: null, i: 0, sections: [], key: null, saved: null, actionCells: [] };
  var ctx = {};
  try { ctx = JSON.parse((document.getElementById("deck-context") || {}).textContent || "{}"); } catch (e) { ctx = {}; }
  if (!ctx.real_label) ctx.real_label = appEl.getAttribute("data-real-label") || null;
  var base = appEl.getAttribute("data-base") || location.origin;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function svgEl(tag, attrs, text) {
    var e = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    if (text != null) e.textContent = text;
    return e;
  }
  function say(text) { if (msgEl) msgEl.textContent = text || ""; }
  // Notes and actions live in localStorage; private windows and blocked storage just don't keep them.
  function storage() {
    try { return typeof localStorage !== "undefined" && localStorage ? localStorage : null; } catch (e) { return null; }
  }
  function persist() { if (state.key && state.saved) saveSaved(storage(), state.key, state.saved); }
  function editable(tag, cls, text, attr, value, label) {
    var e = el(tag, cls, text);
    e.setAttribute("contenteditable", "true");
    e.setAttribute("role", "textbox");
    e.setAttribute("aria-label", label);
    e.setAttribute(attr, value);
    return e;
  }
  function chip(icon, word, tone) {
    var b = el("span", "rag tone-" + tone);
    var i = el("span", "rag-icon", icon);
    i.setAttribute("aria-hidden", "true");
    b.appendChild(i);
    b.appendChild(document.createTextNode(" " + word));
    return b;
  }
  function getJSON(url) {
    if (typeof fetch !== "function") return Promise.resolve({ ok: false, why: "not available" });
    return fetch(url, { credentials: "same-origin" }).then(function (r) {
      if (!r.ok) return { ok: false, why: r.status === 404 ? "not published" : "unavailable (" + r.status + ")" };
      return r.json().then(function (d) { return isObj(d) ? { ok: true, data: d } : { ok: false, why: "not readable" }; },
        function () { return { ok: false, why: "not readable" }; });
    }, function () { return { ok: false, why: "unreachable (are you offline?)" }; });
  }

  function niceStep(range) {
    var raw = range / 4, mag = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10)), r = raw / mag;
    return (r <= 1 ? 1 : r <= 2 ? 2 : r <= 5 ? 5 : 10) * mag;
  }
  function short(s, max) { s = String(s); return s.length > max ? s.slice(0, max - 1) + "…" : s; }
  function svgChart(ch) {
    var W = 480, H = 270, L = 62, R = 10, T = 12, B = 42;
    var svg = svgEl("svg", { viewBox: "0 0 " + W + " " + H, "class": "chart deck-chart", role: "img", "aria-label": ch.alt });
    var data = chartData(ch);
    var cats = data[0].labels.map(function (l) { return l.replace(" " + MARK, ""); });
    var lo = 0, hi = 0;
    cats.forEach(function (c, ci) {
      if (ch.type === "stack") {
        var pos = 0, neg = 0;
        data.forEach(function (s) { var v = s.values[ci]; if (isNum(v)) { if (v >= 0) pos += v; else neg += v; } });
        hi = Math.max(hi, pos); lo = Math.min(lo, neg);
      } else {
        data.forEach(function (s) { var v = s.values[ci]; if (isNum(v)) { hi = Math.max(hi, v); lo = Math.min(lo, v); } });
      }
    });
    if (ch.type === "line" && ch.unit === "pupils" && lo === 0) {
      var vals = [];
      data.forEach(function (s) { s.values.forEach(function (v) { if (isNum(v)) vals.push(v); }); });
      lo = Math.max(0, Math.min.apply(null, vals) * 0.9);
    }
    if (hi === lo) hi = lo + 1;
    var step = niceStep(hi - lo);
    lo = Math.floor(lo / step) * step;
    hi = Math.ceil(hi / step) * step;
    var y = function (v) { return T + (hi - v) / (hi - lo) * (H - T - B); };
    for (var t = lo; t <= hi + step / 2; t += step) {
      svg.appendChild(svgEl("line", { "class": Math.abs(t) < step / 1e6 ? "axis" : "grid", x1: L, x2: W - R, y1: y(t), y2: y(t) }));
      svg.appendChild(svgEl("text", { "class": "tick", x: L - 6, y: y(t) + 4, "text-anchor": "end" }, fmtUnit(t, ch.unit)));
    }
    var band = (W - L - R) / cats.length;
    var cx = function (i) { return L + band * (i + 0.5); };
    var maxChars = Math.max(6, Math.floor(band / 6.5));
    cats.forEach(function (c, i) {
      var label = svgEl("text", { "class": "tick", x: cx(i), y: H - B + 16, "text-anchor": "middle" }, short(c, maxChars) + (data[0].labels[i] !== c ? " " + MARK : ""));
      svg.appendChild(label);
    });
    if (ch.type === "line") {
      data.forEach(function (s, si) {
        var d = "", pen = false;
        s.values.forEach(function (v, i) {
          if (!isNum(v)) { pen = false; return; }
          d += (pen ? "L" : "M") + cx(i).toFixed(1) + " " + y(v).toFixed(1);
          pen = true;
        });
        if (d) svg.appendChild(svgEl("path", { "class": "line s" + (si + 1), d: d }));
        s.values.forEach(function (v, i) {
          if (!isNum(v)) return;
          var marked = s.labels[i] !== cats[i];
          svg.appendChild(marker(si, cx(i), y(v), "dot s" + (si + 1) + (marked ? " suspect" : ""), marked ? 5 : 3.5));
        });
      });
    } else {
      var n = ch.type === "stack" ? 1 : data.length, w = band * 0.72 / n;
      cats.forEach(function (c, i) {
        var up = 0, down = 0;
        data.forEach(function (s, si) {
          var v = s.values[i];
          if (!isNum(v)) return;
          var x0, top, bottom;
          if (ch.type === "stack") {
            x0 = cx(i) - w / 2;
            if (v >= 0) { bottom = up; up += v; top = up; } else { top = down; down += v; bottom = down; }
          } else {
            x0 = cx(i) - band * 0.36 + si * w;
            top = Math.max(v, 0); bottom = Math.min(v, 0);
          }
          var cls = data.length === 1 ? "bar " + (v < 0 ? "neg" : "pos") : "bar s" + (si + 1);
          var marked = s.labels[i] !== cats[i];
          svg.appendChild(svgEl("rect", { "class": cls + (marked ? " suspect" : ""), x: x0.toFixed(1), y: y(top).toFixed(1), width: Math.max(1, w - 2).toFixed(1), height: Math.max(0.5, y(bottom) - y(top)).toFixed(1) }));
          // Direct labels where they fit, so the chart reads without colour (and in greyscale print).
          if (ch.type !== "stack" && w >= 30) {
            svg.appendChild(svgEl("text", { "class": "value", x: (x0 + (w - 2) / 2).toFixed(1), y: (v >= 0 ? y(top) - 4 : y(bottom) + 12).toFixed(1), "text-anchor": "middle" },
              ch.unit === "£" ? fmtMoney(v) : fmtUnit(v, ch.unit)));
          }
        });
      });
    }
    return svg;
  }
  // Line series differ by marker shape as well as colour: circle, square, triangle, diamond.
  function marker(si, x, y, cls, r) {
    var k = si % 4;
    if (k === 0) return svgEl("circle", { "class": cls, cx: x, cy: y, r: r });
    if (k === 1) return svgEl("rect", { "class": cls, x: (x - r).toFixed(1), y: (y - r).toFixed(1), width: (2 * r).toFixed(1), height: (2 * r).toFixed(1) });
    var d = k === 2 ? "M" + x + " " + (y - r * 1.2) + "L" + (x + r * 1.1) + " " + (y + r * 0.8) + "L" + (x - r * 1.1) + " " + (y + r * 0.8) + "Z"
      : "M" + x + " " + (y - r * 1.3) + "L" + (x + r * 1.3) + " " + y + "L" + x + " " + (y + r * 1.3) + "L" + (x - r * 1.3) + " " + y + "Z";
    return svgEl("path", { "class": cls, d: d });
  }
  function legend(ch) {
    var box = el("div", "legend");
    if (ch.series.length < 2) return null;
    ch.series.forEach(function (s, i) {
      var item = el("span");
      var key = el("span", "key " + (ch.type === "line" ? "line" : "swatch") + " s" + (i + 1));
      key.setAttribute("aria-hidden", "true");
      item.appendChild(key);
      item.appendChild(document.createTextNode(s.name));
      box.appendChild(item);
    });
    box.setAttribute("aria-hidden", "true");
    return box;
  }
  function badge(st) {
    var b = el("span", "badge large s-" + st.key);
    var i = el("span", null, st.icon);
    i.setAttribute("aria-hidden", "true");
    b.appendChild(i);
    b.appendChild(document.createTextNode(" " + st.label));
    return b;
  }
  function renderSlide(sl, i, n, deck) {
    var sec = el("section", "slide slide-" + sl.kind);
    sec.id = "slide-" + (i + 1);
    sec.setAttribute("aria-roledescription", "slide");
    sec.setAttribute("aria-label", (i + 1) + " of " + n + ": " + sl.title);
    var head = el("header", "slide-head");
    head.appendChild(el("h2", null, sl.title));
    if (sl.status) head.appendChild(badge(sl.status));
    sec.appendChild(head);
    if (sl.meta) {
      var meta = el("p", "slide-meta");
      meta.appendChild(el("span", "meta-label", "Prepared for: "));
      meta.appendChild(editable("span", "meta-field", sl.meta.preparedFor || "", "data-field", "meeting", "Meeting this pack is prepared for"));
      meta.appendChild(document.createTextNode(" · "));
      meta.appendChild(editable("span", "meta-field", sl.meta.date || "", "data-field", "date", "Date of the meeting"));
      sec.appendChild(meta);
    }
    if (sl.lead) sec.appendChild(el("p", "slide-lead", sl.lead));
    var tabled = !!(sl.table || sl.kind === "actions");
    var body = el("div", "slide-body" + (sl.chart ? " has-chart" : "") + (tabled ? " has-table" : "") + (sl.messages && sl.ratings && sl.ratings.length ? " has-ratings" : ""));
    if (sl.table) body.appendChild(renderTable(sl.table));
    if (sl.kind === "actions") body.appendChild(renderActions(sl));
    var text = el("div", "slide-text");
    if (sl.messages && sl.messages.length) {
      var ol = el("ol", "slide-messages");
      sl.messages.forEach(function (t) { ol.appendChild(el("li", null, t)); });
      text.appendChild(ol);
    }
    if (sl.figures.length) {
      var dl = el("ul", "slide-figs");
      sl.figures.forEach(function (f) {
        var li = el("li");
        li.appendChild(el("span", "fig-label", f.label));
        var meta = [f.year, f.source].filter(Boolean).join(", ");
        var cut = meta && f.text.slice(-(meta.length + 2)) === ", " + meta ? f.text.length - meta.length - 2 : f.text.length;
        li.appendChild(el("span", "fig-text", f.text.slice(0, cut)));
        if (cut < f.text.length) li.appendChild(el("span", "fig-meta", meta));
        dl.appendChild(li);
      });
      text.appendChild(dl);
    }
    var ratingsBox = null;
    if (sl.ratings && sl.ratings.length) {
      ratingsBox = el("ul", "slide-ratings");
      ratingsBox.setAttribute("aria-label", "Ratings");
      sl.ratings.forEach(function (r) {
        var li = el("li");
        li.appendChild(chip(r.icon, r.word, r.tone));
        li.appendChild(el("span", "rag-measure", " " + r.measure));
        if (r.value) li.appendChild(el("span", "rag-value", r.value));
        if (r.why) li.setAttribute("title", r.why);
        ratingsBox.appendChild(li);
      });
      if (!sl.messages) text.appendChild(ratingsBox);
    }
    if (sl.statuses && sl.statuses.length) {
      var sl2 = el("ul", "slide-statuses");
      sl.statuses.forEach(function (s) { var li = el("li"); li.appendChild(badge(s)); li.appendChild(document.createTextNode(" " + s.name)); sl2.appendChild(li); });
      text.appendChild(sl2);
    }
    if (sl.bullets.length) {
      var ul = el("ul", "slide-bullets" + (sl.bullets.length > 4 ? " many" : ""));
      sl.bullets.forEach(function (b) { ul.appendChild(el("li", null, b)); });
      text.appendChild(ul);
    }
    if (sl.links && sl.links.length) {
      var p = el("p", "slide-links");
      sl.links.forEach(function (l, k) {
        if (k) p.appendChild(document.createTextNode(" · "));
        var a = el("a", null, l.text);
        a.setAttribute("href", l.href);
        if (/^https?:/.test(l.href)) a.setAttribute("rel", "noopener");
        p.appendChild(a);
      });
      text.appendChild(p);
    }
    if (text.children.length) body.appendChild(text);
    if (ratingsBox && sl.messages) body.appendChild(ratingsBox);
    if (sl.chart) {
      var fig = el("figure", "slide-chart");
      fig.appendChild(svgChart(sl.chart));
      var lg = legend(sl.chart);
      if (lg) fig.appendChild(lg);
      fig.appendChild(el("figcaption", "visually-hidden", sl.chart.alt));
      body.appendChild(fig);
    }
    sec.appendChild(body);
    if (sl.note) sec.appendChild(el("p", "slide-note", sl.note));
    if (deck.view || state.key) {
      var notes = editable("div", "slide-notes", sl.notes || "", "data-notes", sl.id, "Notes for slide " + (i + 1));
      notes.setAttribute("aria-multiline", "true");
      notes.setAttribute("data-placeholder", "Notes for this slide: kept in this browser, printed, and added to the PowerPoint as speaker notes");
      sec.appendChild(notes);
    }
    var foot = el("footer", "slide-foot");
    foot.appendChild(el("span", null, SITE + " · " + deck.title));
    foot.appendChild(el("span", null, (i + 1) + " / " + n));
    sec.appendChild(foot);
    return sec;
  }
  function renderTable(t) {
    var wrap = el("div", "slide-table-wrap");
    var table = el("table", "slide-table");
    if (t.caption) table.appendChild(el("caption", "visually-hidden", t.caption));
    var thead = el("thead"), hr = el("tr");
    t.columns.forEach(function (h) { var th = el("th", null, h); th.setAttribute("scope", "col"); hr.appendChild(th); });
    thead.appendChild(hr);
    table.appendChild(thead);
    var tbody = el("tbody");
    t.rows.forEach(function (r) {
      var tr = el("tr", [r.self ? "is-self" : "", r.median ? "is-median" : "", r.suspect ? "is-suspect" : ""].filter(Boolean).join(" "));
      r.cells.forEach(function (c, k) {
        var td = el(k === 0 ? "th" : "td");
        if (k === 0) td.setAttribute("scope", "row");
        if (c.rag) td.appendChild(chip(c.rag.icon, c.rag.word, c.rag.tone));
        else if (c.status) td.appendChild(chip(ICONS[c.status], LABELS[c.status], TONES[c.status]));
        else td.textContent = c.text;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }
  function rowButton(text, act, row, label) {
    var b = el("button", "deck-row-btn", text);
    b.setAttribute("type", "button");
    b.setAttribute("data-deck-row", act);
    if (row != null) b.setAttribute("data-row", String(row));
    if (label) b.setAttribute("aria-label", label);
    return b;
  }
  function renderActions(sl) {
    var wrap = el("div", "slide-actions");
    var table = el("table", "slide-table actions-table");
    var thead = el("thead"), hr = el("tr");
    (sl.columns || ["Action or decision", "Owner", "By when"]).forEach(function (h) { var th = el("th", null, h); th.setAttribute("scope", "col"); hr.appendChild(th); });
    var th0 = el("th", "action-tools", "");
    th0.appendChild(el("span", "visually-hidden", "Remove"));
    hr.appendChild(th0);
    thead.appendChild(hr);
    table.appendChild(thead);
    var tbody = el("tbody");
    state.actionCells = [];
    (sl.actions || []).forEach(function (a, r) {
      var tr = el("tr");
      var cells = [["action", "Action or decision"], ["owner", "Owner"], ["by", "By when"]].map(function (f) {
        var td = el("td");
        var box = editable("div", "action-cell", a[f[0]] || "", "data-action-row", String(r), f[1] + ", row " + (r + 1));
        box.setAttribute("data-action-field", f[0]);
        td.appendChild(box);
        tr.appendChild(td);
        return box;
      });
      var tools = el("td", "action-tools");
      tools.appendChild(rowButton("Remove", "remove", r, "Remove row " + (r + 1)));
      tr.appendChild(tools);
      tbody.appendChild(tr);
      state.actionCells.push(cells);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    var bar = el("p", "action-bar");
    bar.appendChild(rowButton("Add a row", "add", null, null));
    wrap.appendChild(bar);
    return wrap;
  }
  function actionsOf(deck) {
    var list = deck && deck.slides ? deck.slides.filter(function (s) { return s.kind === "actions"; }) : [];
    return list[0] || null;
  }
  function render(deck, at) {
    state.deck = deck;
    deck.base = base;
    appEl.textContent = "";
    appEl.classList.add("is-paged");
    ["governors", "ptfa", "review"].forEach(function (v) { appEl.classList.toggle("pack-" + v, deck.view === v); });
    var n = deck.slides.length;
    state.sections = deck.slides.map(function (sl, i) { var s = renderSlide(sl, i, n, deck); appEl.appendChild(s); return s; });
    var h1 = document.querySelector("h1.deck-title");
    if (h1) h1.textContent = deck.title;
    if (deck.title) document.title = deck.title + " | Presentation | " + SITE;
    if (toolbar) toolbar.hidden = false;
    var pptxBtn = document.querySelector('[data-deck="pptx"]');
    if (pptxBtn) pptxBtn.disabled = !!deck.message;
    var fromHash = /^#s(\d+)$/.exec(location.hash || "");
    go(at != null ? at : fromHash ? Math.min(+fromHash[1] - 1, n - 1) : 0, true);
  }
  function go(i, quiet) {
    var n = state.sections.length;
    if (!n) return;
    state.i = Math.max(0, Math.min(i, n - 1));
    state.sections.forEach(function (s, k) {
      var on = k === state.i;
      s.classList.toggle("is-current", on);
      if (on) s.setAttribute("aria-current", "step"); else s.removeAttribute("aria-current");
    });
    var text = "Slide " + (state.i + 1) + " of " + n;
    if (countEl) countEl.textContent = text;
    if (!quiet && liveEl) liveEl.textContent = text + ": " + state.deck.slides[state.i].title;
    var prev = document.querySelector('[data-deck="prev"]'), next = document.querySelector('[data-deck="next"]');
    if (prev) prev.disabled = state.i === 0;
    if (next) next.disabled = state.i === n - 1;
    if (!quiet && history.replaceState) history.replaceState(null, "", location.pathname + location.search + "#s" + (state.i + 1));
  }

  function readPalette() {
    var cs = getComputedStyle(document.documentElement), out = {};
    ["paper", "card", "card-2", "line", "grid", "ink", "ink-2", "ink-3", "accent", "c1", "c2", "c3", "c4",
      "critical", "serious", "warning", "good", "plenty", "held"].forEach(function (k) { out[k] = cs.getPropertyValue("--" + k).trim(); });
    var pack = getComputedStyle(appEl).getPropertyValue("--pack").trim();
    if (pack) out.pack = pack;
    return out;
  }
  var pptxLoading = null;
  function loadPptx() {
    if (root.PptxGenJS) return Promise.resolve(root.PptxGenJS);
    if (pptxLoading) return pptxLoading;
    pptxLoading = new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = PPTX_URL;
      s.integrity = PPTX_SRI;
      s.crossOrigin = "anonymous";
      s.onload = function () { if (root.PptxGenJS) resolve(root.PptxGenJS); else reject(new Error("missing")); };
      s.onerror = function () { reject(new Error("blocked")); };
      document.head.appendChild(s);
    }).catch(function (e) { pptxLoading = null; throw e; });
    return pptxLoading;
  }
  function downloadPptx(btn) {
    if (!state.deck || state.deck.message) return;
    var label = btn.textContent;
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
    btn.textContent = "Preparing PowerPoint…";
    say("Preparing the PowerPoint file…");
    loadPptx().then(function (Ctor) {
      return buildPptx(state.deck, Ctor, readPalette());
    }).then(function () {
      say("PowerPoint saved as “" + state.deck.filename + "”.");
    }, function () {
      say("The PowerPoint maker couldn't be loaded (it comes from a public CDN, which may be blocked or offline). You can still print the slides or save them as a PDF.");
    }).then(function () {
      btn.disabled = false;
      btn.removeAttribute("aria-busy");
      btn.textContent = label;
    });
  }
  function copyLink() {
    var url = location.href;
    function fallback() {
      var input = el("input", "deck-copy");
      input.value = url;
      input.readOnly = true;
      input.setAttribute("aria-label", "Link to this presentation");
      if (msgEl) { msgEl.textContent = "Copy this link: "; msgEl.appendChild(input); }
      input.focus();
      input.select();
      var ok = false;
      try { ok = document.execCommand && document.execCommand("copy"); } catch (e) { ok = false; }
      if (ok) say("Link copied.");
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(function () { say("Link copied."); }, fallback);
    } else {
      fallback();
    }
  }
  function toggleFull() {
    var full = document.fullscreenElement;
    if (full && document.exitFullscreen) { document.exitFullscreen(); return; }
    if (appEl.requestFullscreen) {
      appEl.requestFullscreen().catch(function () { say("Full screen isn't available in this browser."); });
    } else {
      say("Full screen isn't available in this browser.");
    }
  }
  document.addEventListener("fullscreenchange", function () {
    var btn = document.querySelector('[data-deck="full"]');
    if (btn) btn.setAttribute("aria-pressed", document.fullscreenElement ? "true" : "false");
  });

  document.addEventListener("click", function (e) {
    var rb = e.target.closest && e.target.closest("[data-deck-row]");
    var acts = rb ? actionsOf(state.deck) : null;
    if (acts) {
      if (rb.getAttribute("data-deck-row") === "add") acts.actions.push({ action: "", owner: "", by: "" });
      else acts.actions.splice(+rb.getAttribute("data-row"), 1);
      if (state.saved) state.saved.actions = acts.actions.map(function (a) { return { action: a.action, owner: a.owner, by: a.by }; });
      persist();
      render(state.deck, state.i);
      var last = state.actionCells[state.actionCells.length - 1];
      if (rb.getAttribute("data-deck-row") === "add" && last && last[0].focus) last[0].focus();
      say(rb.getAttribute("data-deck-row") === "add" ? "Row added." : "Row removed.");
      return;
    }
    var b = e.target.closest && e.target.closest("[data-deck]");
    if (!b || b.disabled) return;
    var act = b.getAttribute("data-deck");
    if (act === "prev") go(state.i - 1);
    else if (act === "next") go(state.i + 1);
    else if (act === "print") window.print();
    else if (act === "pptx") downloadPptx(b);
    else if (act === "copy") copyLink();
    else if (act === "full") toggleFull();
  });
  // Typing in a notes box, the meeting line or the actions table updates the model and is saved at once.
  document.addEventListener("input", function (e) {
    var t = e.target;
    if (!t || !t.getAttribute || !state.deck) return;
    var text = typeof t.innerText === "string" ? t.innerText.replace(/\n$/, "") : String(t.textContent || "");
    var id = t.getAttribute("data-notes"), field = t.getAttribute("data-field"), row = t.getAttribute("data-action-row");
    if (!state.saved) state.saved = { notes: {}, actions: null, meeting: null, date: null };
    if (id != null) {
      state.saved.notes[id] = text;
      state.deck.slides.forEach(function (sl) { if (sl.id === id) sl.notes = text; });
    } else if (field === "meeting" || field === "date") {
      state.saved[field] = text;
      state.deck.slides.forEach(function (sl) { if (sl.meta) sl.meta[field === "meeting" ? "preparedFor" : "date"] = text; });
    } else if (row != null) {
      var acts = actionsOf(state.deck), a = acts ? acts.actions[+row] : null;
      if (!a) return;
      a[t.getAttribute("data-action-field")] = text;
      state.saved.actions = acts.actions.map(function (x) { return { action: x.action, owner: x.owner, by: x.by }; });
    } else {
      return;
    }
    persist();
  });
  var STEP_KEYS = ["ArrowRight", "ArrowLeft", " ", "Spacebar", "PageDown", "PageUp", "Home", "End"];
  document.addEventListener("keydown", function (e) {
    if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || !state.sections.length) return;
    var t = e.target, tag = t && t.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || (t && t.isContentEditable)) return;
    if ((e.key === " " || e.key === "Spacebar") && (tag === "BUTTON" || tag === "A" || tag === "SUMMARY")) return;
    if (e.key === "f" || e.key === "F") { e.preventDefault(); toggleFull(); return; }
    if (STEP_KEYS.indexOf(e.key) === -1) return;
    e.preventDefault();
    var j = nextIndex(state.i, e.key, state.sections.length);
    if (j !== state.i) go(j);
  });

  function showMessage(title, text, links) { state.key = null; state.saved = null; render(messageDeck(title, text, links)); say(text); }
  // A failed fetch (404, bad JSON, offline) is said on the first slide as well as in the toolbar message.
  // Notes, actions and the meeting line saved for this school and pack (or this compare/area deck) are put back.
  function present(deck, warnings, key) {
    warnings = warnings.filter(Boolean);
    state.key = deck && !deck.message ? key || null : null;
    state.saved = state.key ? loadSaved(storage(), state.key) : null;
    if (state.saved) applySaved(deck, state.saved);
    render(withWarnings(deck, warnings));
    if (warnings.length) say(warnings.join(" "));
  }
  function failed(r, text) { return !r.ok && r.why ? text.replace("{why}", r.why) : null; }
  function load() {
    var q = new URLSearchParams(location.search);
    var view = (q.get("view") || "").toLowerCase();
    var urnsQ = q.get("urns"), areaQ = q.get("area"), urnQ = q.get("urn");
    appEl.textContent = "";
    appEl.appendChild(el("p", "deck-wait", "Building the slides…"));
    if (urnsQ || view === "compare") {
      var urns = String(urnsQ || urnQ || "").split(",").map(function (u) { return u.trim(); })
        .filter(function (u, i, a) { return /^\d{1,8}$/.test(u) && a.indexOf(u) === i; });
      return Promise.all(urns.map(function (u) {
        return Promise.all([getJSON("/data/s/" + u + ".json"), getJSON("/data/sx/" + u + ".json")]);
      })).then(function (res) {
        var warnings = [];
        var list = res.filter(function (r, i) {
          if (!r[0].ok) warnings.push(failed(r[0], "Figures for school " + urns[i] + " are {why}, so it is left out."));
          return r[0].ok;
        }).map(function (r) {
          var name = r[0].data.name || "school " + r[0].data.urn;
          warnings.push(failed(r[1], "Year-by-year detail for " + name + " is {why}, so its slides use the summary figures."));
          return { s: r[0].data, sx: r[1].ok ? r[1].data : null };
        });
        present(compareDeck(list, ctx), warnings, notesKey(urns.join(","), "compare"));
      });
    }
    // The page's breadcrumb says Home > Presentation; once we know whose figures these are, lead back to them:
    // School Money > Hackney > William Patten Primary School > Governors' finance pack.
    function setCrumbs(trail, here) {
      var nav = document.querySelector("nav.crumbs");
      if (!nav) return;
      nav.textContent = "";
      trail.filter(function (t) { return t && t.name && t.path; }).forEach(function (t) {
        var a = document.createElement("a"); a.href = t.path; a.textContent = t.name; nav.appendChild(a);
        var sep = document.createElement("span"); sep.setAttribute("aria-hidden", "true"); sep.textContent = " › "; nav.appendChild(sep);
      });
      var cur = document.createElement("span"); cur.setAttribute("aria-current", "page"); cur.textContent = here; nav.appendChild(cur);
    }
    if (areaQ) {
      if (!/^[A-Za-z0-9-]{1,60}$/.test(areaQ)) { showMessage("Area presentation", "That area link doesn't look right. Choose a council or constituency instead."); return Promise.resolve(); }
      return Promise.all([getJSON("/data/a/" + encodeURIComponent(areaQ) + ".json"), getJSON("/data/a/england.json")]).then(function (r) {
        if (!r[0].ok) { showMessage("Area presentation", "Figures for this area are " + r[0].why + ", so there is nothing to present yet."); return; }
        var ad = r[0].data || {};
        setCrumbs([{ name: "School Money", path: "/" }, { name: ad.name, path: ad.path }], "Presentation");
        present(areaDeck(r[0].data, r[1].ok ? r[1].data : null, ctx),
          [failed(r[1], "England figures are {why}, so the England comparisons are left out.")], notesKey(areaQ, "area"));
      });
    }
    if (urnQ && /^\d{1,8}$/.test(urnQ)) {
      return Promise.all([getJSON("/data/s/" + urnQ + ".json"), getJSON("/data/sx/" + urnQ + ".json")]).then(function (r) {
        if (!r[0].ok) {
          showMessage("School presentation", "Figures for school " + urnQ + " are " + r[0].why + ". Check the link, or search for the school.");
          return;
        }
        var s = r[0].data, code = s.council && s.council.code != null ? String(s.council.code) : null;
        return Promise.all([code ? getJSON("/data/a/council-" + encodeURIComponent(code) + ".json") : Promise.resolve({ ok: false }), getJSON("/data/a/england.json")]).then(function (a) {
          var m = adapt(s, r[1].ok ? r[1].data : null, a[0].ok ? a[0].data : null, a[1].ok ? a[1].data : null);
          var pack = packView(view) || "governors";
          setCrumbs([{ name: "School Money", path: "/" }, { name: m.council.name, path: m.council.path }, { name: m.name, path: m.path }],
            (PACKS[pack] && PACKS[pack].label) || "Presentation");
          present(packDeck(pack, m, ctx), [
            failed(r[1], "Year-by-year detail for this school is {why}, so the slides use the summary figures."),
            failed(a[0], "Figures for the council are {why}, so the council comparisons are left out."),
            failed(a[1], "England figures are {why}, so the England comparisons are left out.")
          ], notesKey(urnQ, pack));
        });
      });
    }
    var pins = [];
    try { pins = JSON.parse(localStorage.getItem("moneyPinned") || "[]") || []; } catch (e) { pins = []; }
    var schools = (Array.isArray(pins) ? pins : []).filter(function (p) { return p && p.type === "school" && /^\d{1,8}$/.test(String(p.id)); });
    var links = [{ text: "Search for a school", href: "/search/" }, { text: "Browse councils", href: "/council/" }];
    schools.slice(0, 6).forEach(function (p) { links.push({ text: PACKS.governors.label + ": " + p.name, href: "/deck/?urn=" + p.id + "&view=governors" }); });
    if (schools.length >= 2) links.push({ text: "Compare your " + Math.min(schools.length, 6) + " pinned schools", href: "/deck/?urns=" + schools.slice(0, 6).map(function (p) { return p.id; }).join(",") + "&view=compare" });
    showMessage("Choose what to present", "Open a school, council or constituency page and choose its presentation, or pick from your pinned schools.", links);
    return Promise.resolve();
  }
  load().catch(function () { showMessage("Presentation", "Something went wrong building the slides. Reload the page to try again."); });
})(typeof globalThis !== "undefined" ? globalThis : this);
