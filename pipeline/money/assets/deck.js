/* School Money — deck.js (unit C2). Defer-loaded on /deck/ only; the page says what to do without it.
   Builds presentation decks in the browser: a school deck, a PTFA deck, a compare deck and an area deck.
   One slide model feeds the on-screen slides, the print layout and the PowerPoint file.
   Pure model exported as globalThis.MoneyDeck (tested under node); DOM wiring runs only in a browser.

   Reads: /data/s/<urn>.json, /data/sx/<urn>.json, /data/a/<id>.json and the #deck-context JSON block
          that deck.py writes (IFS framings, questions and context lines with page numbers, real-terms label).
   Query: ?urn=<urn>&view=school|ptfa, ?urns=a,b,c&view=compare, ?area=<area id>.
   Loads PptxGenJS from the CDN only when "Download PowerPoint" is pressed. */
(function (root) {
  "use strict";

  // Pinned library. Hash checked against the jsDelivr data API and a fresh download on 2026-11-07.
  var PPTX_URL = "https://cdn.jsdelivr.net/npm/pptxgenjs@3.12.0/dist/pptxgen.bundle.js";
  var PPTX_SRI = "sha384-Cck14aA9cifjYolcnjebXRfWGkz5ltHMBiG4px/j8GS+xQcb7OhNQWZYyWjQ+UwQ";

  var ORDER = ["in_deficit", "heading_for_deficit", "tight", "healthy", "large_reserves"];
  var LABELS = { in_deficit: "In deficit", heading_for_deficit: "Heading for deficit", tight: "Tight", healthy: "Healthy", large_reserves: "Large reserves" };
  var ICONS = { in_deficit: "▼", heading_for_deficit: "↘", tight: "●", healthy: "✓", large_reserves: "▲" };
  var SITE = "School Money";
  var CHARITY_SOURCE = "Charity Commission register";
  var AREA_SOURCE = "School Money medians of DfE returns";
  var DSG_SOURCE = "DfE section 251 outturn";
  var REGISTER_HOME = "https://register-of-charities.charitycommission.gov.uk/";
  var MARK = "◆";
  var MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  // Finance-row metrics the decks read from /data/sx (m) with /data/s years[] as the fallback.
  var METRICS = ["total_income", "total_expenditure", "in_year_balance", "revenue_reserve", "grant_funding", "self_generated",
    "sen_funding", "pupil_premium", "donations_revenue", "staff_total"];
  var S_FALLBACK = { total_income: "income", total_expenditure: "spend", in_year_balance: "balance", revenue_reserve: "reserve" };
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
        Object.keys(f).forEach(function (y) {
          var list = Array.isArray(f[y]) ? f[y] : [f[y]];
          if (!list.length) add(y, "");
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
        dsg[y] = isObj(d) ? { balance: n(d.balance), pp: n(d.per_pupil) } : { balance: n(d), pp: null };
      });
      var pta = isObj(A.pta) ? A.pta : null;
      var bands = null;
      if (pta && isObj(pta.by_band || pta.bands)) bands = pta.by_band || pta.bands;
      var statuses = {};
      var sl = isObj(A.statuses_latest) ? A.statuses_latest : {};
      Object.keys(sl).forEach(function (k) { if (n(sl[k]) != null) statuses[k] = n(sl[k]); });
      return {
        ok: true, id: id, type: type, name: str(a.name || A.name) || "This area", path: str(a.path),
        years: Object.keys(years).sort(), by: by, pupils: pupils, schools: schools, dsg: dsg,
        statuses: statuses, ptaBands: bands, ptaGap: pta ? (pta.gap != null ? pta.gap : null) : null,
        ptaText: pta && typeof pta.text === "string" ? pta.text : null
      };
    }

    var m = { ok: !!s, urn: null, name: null, rows: [], pta: [], area: area(council), england: area(england) };
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
    var src = str((sx && sx.source) || s.source) || (m.academy ? "AAR" : "CFR");
    m.sourceKey = /AAR/i.test(src) ? "AAR" : "CFR";
    m.source = "DfE " + m.sourceKey + " return";
    m.sx = !!(sx && isObj(sx.m));

    // Yearly rows: labels from sx.years, else s.years[].y; metrics from sx.m, else the s.years fields.
    var sYears = Array.isArray(s.years) ? s.years.filter(isObj) : [];
    var sByYear = {};
    sYears.forEach(function (r) { if (r.y) sByYear[String(r.y)] = r; });
    var labels = sx && Array.isArray(sx.years) && sx.years.length ? sx.years.map(String) : sYears.map(function (r) { return String(r.y); });
    var flagged = flags(sx && sx.flags);
    var sxm = m.sx ? sx.m : {};
    var sxp = sx && isObj(sx.pupils) ? sx.pupils : {};
    m.rows = labels.filter(function (y, i) { return y && labels.indexOf(y) === i; }).map(function (y) {
      var sr = sByYear[y] || {};
      var pupils = n(sxp[y]);
      if (pupils == null) pupils = n(sr.pupils);
      var row = { y: y, pupils: pupils, suspect: y in flagged, flag: flagged[y] || "", metrics: {}, status: str(sr.status) };
      METRICS.forEach(function (k) {
        var cell = isObj(sxm[k]) ? sxm[k][y] : null;
        var v = null, pp = null, r = null, rpp = null;
        if (isObj(cell)) { v = n(cell.v); pp = n(cell.pp); r = n(cell.r); rpp = n(cell.rpp); } else if (n(cell) != null) v = n(cell);
        if (v == null && S_FALLBACK[k]) v = n(sr[S_FALLBACK[k]]);
        if (pp == null) pp = perPupil(v, pupils);
        if (v != null || pp != null) row.metrics[k] = { v: v, pp: pp, r: r, rpp: rpp };
      });
      return row;
    });

    // Parents' associations: register history from /data/s, per-pupil figures from sx.pta where given.
    var sxPta = sx && isObj(sx.pta) ? sx.pta : {};
    var rowPupils = {};
    m.rows.forEach(function (r) { rowPupils[r.y] = r.pupils; });
    function charityYear(end) {
      var d = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(end || ""));
      if (!d) return null;
      var y = +d[1], mo = +d[2], day = +d[3];
      return { y: mo === 12 ? String(y) : (y - 1) + "-" + String(y).slice(2), end: day + " " + MONTHS[mo - 1].slice(0, 3) + " " + y, fye: day + " " + MONTHS[mo - 1] };
    }
    var charities = (Array.isArray(s.pta) ? s.pta : []).filter(function (p) { return isObj(p) && !p.review; });
    m.pta = charities.map(function (p) {
      var num = str(p.charity_number);
      var years = [], fye = null;
      (Array.isArray(p.history) ? p.history : []).forEach(function (h) {
        if (!isObj(h)) return;
        var cy = charityYear(h.period_end);
        if (!cy) return;
        fye = cy.fye;
        years.push({ y: cy.y, end: cy.end, income: n(h.income), spend: n(h.expenditure != null ? h.expenditure : h.spend) });
      });
      if (!years.length) {
        Object.keys(sxPta).sort().forEach(function (y) {
          var e = sxPta[y];
          if (isObj(e) && (!e.charity_number || String(e.charity_number) === num || charities.length === 1)) {
            years.push({ y: y, end: null, income: n(e.income), spend: n(e.spend) });
          }
        });
      }
      years.sort(function (a, b) { return a.y < b.y ? -1 : a.y > b.y ? 1 : 0; });
      years.forEach(function (e) {
        var x = sxPta[e.y];
        var match = isObj(x) && (!x.charity_number || String(x.charity_number) === num);
        e.incomePp = match && n(x.income_pp) != null ? n(x.income_pp) : perPupil(e.income, rowPupils[e.y]);
        e.spendPp = match && n(x.spend_pp) != null ? n(x.spend_pp) : perPupil(e.spend, rowPupils[e.y]);
      });
      return { number: num, name: str(p.name) || "Parents' association", status: str(p.status), latestIncome: n(p.latest_income), fye: fye, years: years };
    }).sort(function (a, b) { return (b.latestIncome || 0) - (a.latestIncome || 0); });
    m.gap = sx && sx.gap != null ? sx.gap : null;
    m.trustCentralPp = n(sx && sx.trust_central_pp);
    return m;
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
      links: isObj(ctx.links) ? ctx.links : {}, notInReport: Array.isArray(ctx.not_in_report) ? ctx.not_in_report : []
    };
  }
  function framing(c, key) {
    var f = c.framings[key];
    if (!f || !f.text) return "";
    var p = pages(f.pages);
    return f.text + (p ? " (" + p + ")" : "");
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
    return { id: id, kind: kind, title: title, lead: "", bullets: [], figures: [], chart: null, note: "", sources: [], links: [] };
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
  function schoolSources(m, c) {
    var out = [m.source.replace("return", "returns") + ", " + yearSpan(m) + " (DfE Financial Benchmarking and Insights Tool data)"];
    if (m.path) out.push(SITE + " page: " + (c.links.base || "") + m.path);
    return out;
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
  // School deck: 10 slides
  // ======================================================================
  function schoolDeck(m, ctx) {
    var c = ctxOf(ctx);
    if (!m || !m.ok) return messageDeck("School presentation", "This school's figures couldn't be loaded, so there is nothing to present yet.");
    var slides = [];
    var latest = latestRow(m, "total_income") || m.rows[m.rows.length - 1] || null;
    var year = latest ? latest.y : m.year;
    var src = m.source;
    var where = m.council.name ? m.council.name + (m.council.code ? " (LA " + m.council.code + ")" : "") : "";

    // 1. Title
    var s1 = slide("title", "title", m.name);
    s1.lead = "School money presentation" + (m.council.name ? ": " + m.council.name : "") + (year ? ", " + year : "") +
      (latest && isNum(latest.pupils) ? ", " + fmtPupils(latest.pupils) + " pupils" : "");
    if (latest && isNum(latest.pupils)) s1.figures.push(figure("pupils", "Pupils", latest.pupils, null, year, src, "pupils"));
    if (where) s1.bullets.push("Council: " + where);
    s1.bullets.push(m.academy ? "An academy" + (m.trust ? " in " + m.trust : "") + ": its accounts go to the DfE through the trust." : "Council-run: its budget is set and checked through the council.");
    if (year) s1.bullets.push("Latest year with published figures: " + year + ", " + src + ".");
    s1.note = "Figures are a starting point for a conversation with the school, not a verdict on it.";
    s1.sources = schoolSources(m, c);
    slides.push(s1);

    // 2. Status and what it means
    var st = m.status;
    var s2 = slide("status", "status", "Where the budget stands");
    var reserveRow = latestRow(m, "revenue_reserve");
    if (st) {
      s2.status = { key: st.key, label: st.label, icon: st.icon };
      var said = st.reason && st.reason.toLowerCase().indexOf(st.label.toLowerCase()) === 0;
      s2.lead = st.icon + " " + (said ? st.reason : st.label + (st.reason ? ": " + st.reason : "")) + (st.year ? " (" + st.year + ", " + src + ")" : "");
    } else {
      s2.lead = "There isn't a full year of published figures to assess this school's budget yet.";
    }
    if (reserveRow) {
      var rv = metric(reserveRow, "revenue_reserve");
      s2.figures.push(figure("revenue_reserve", "Reserve at the end of the year", rv.v, rv.pp, reserveRow.y, src));
      var bal = metric(reserveRow, "in_year_balance");
      if (bal && isNum(bal.v)) s2.figures.push(figure("in_year_balance", bal.v < 0 ? "Spent more than it received" : "Received more than it spent", bal.v, bal.pp, reserveRow.y, src));
    }
    if (st && (st.key === "in_deficit" || st.key === "heading_for_deficit")) {
      var why = framing(c, "why_schools_go_into_deficit") ||
        "Most of a school's money goes on staff, so when costs rise faster than funding, or pupil numbers fall, a budget is squeezed quickly.";
      s2.bullets.push("Why this happens: " + why);
      s2.bullets.push("What helps: a recovery plan agreed with " + m.overseer + " that says how many years it will take, budget forecasts that governors see often and check against what happened, and an open conversation with parents about what the plan changes. Slide 9 has questions to start with.");
      s2.links = [{ text: "How to read a deficit", href: "/guides/parents/#how-to-read-a-deficit" }];
      if (st.key === "heading_for_deficit") s2.note = framing(c, "one_deficit_year");
      s2.sources.push(framingSource(c, "why_schools_go_into_deficit"), st.key === "heading_for_deficit" ? framingSource(c, "one_deficit_year") : null);
    } else if (st && st.key === "tight") {
      var tightLine = ctxLine(c, "school", "costs_outpaced_funding");
      if (tightLine) s2.bullets.push("Context: " + tightLine.text);
      s2.bullets.push("What helps: a small contingency in the budget, knowing which costs are likely to rise next year, and not relying on one-off money to balance.");
      s2.note = framing(c, "one_deficit_year");
      s2.sources.push(tightLine ? ifsSource(c, tightLine.page) : null, framingSource(c, "one_deficit_year"));
    } else {
      s2.bullets.push("The status is worked out from the reserve as a share of a year's income and the run of years spending more than received.");
      if (m.streak >= 2) s2.bullets.push("It has spent more than it received for " + m.streak + " years running, so the trend is worth watching.");
      s2.note = framing(c, "one_deficit_year");
      s2.sources.push(framingSource(c, "one_deficit_year"));
    }
    s2.sources = s2.sources.filter(Boolean).concat(schoolSources(m, c).slice(0, 1));
    slides.push(s2);

    // 3. Government funding vs spending per pupil
    var s3 = slide("funding", "chart", "Funding and spending per pupil");
    s3.chart = chart("line", "£ per pupil", [
      { key: "grant_funding", name: "Government grants", points: points(m, "grant_funding", "pp") },
      { key: "total_income", name: "All income", points: points(m, "total_income", "pp") },
      { key: "total_expenditure", name: "Spending", points: points(m, "total_expenditure", "pp") }
    ]);
    var inc = latestRow(m, "total_income");
    if (inc) {
      var ci = metric(inc, "total_income"), cg = metric(inc, "grant_funding"), ce = metric(inc, "total_expenditure");
      s3.figures.push(figure("total_income", "All income", ci.v, ci.pp, inc.y, src));
      if (cg && isNum(cg.v)) s3.figures.push(figure("grant_funding", "Government grants", cg.v, cg.pp, inc.y, src));
      if (ce && isNum(ce.v)) s3.figures.push(figure("total_expenditure", "Spending", ce.v, ce.pp, inc.y, src));
    } else {
      s3.lead = "Figures for this school's income aren't published yet.";
    }
    var f0 = firstRow(m, "total_expenditure"), f1 = latestRow(m, "total_expenditure");
    if (f0 && f1 && f0 !== f1) {
      s3.bullets.push("Spending per pupil went from " + fmtExact(metric(f0, "total_expenditure").pp) + " in " + f0.y + " to " +
        fmtExact(metric(f1, "total_expenditure").pp) + " in " + f1.y + " in cash terms (" + src.replace("return", "returns") + ").");
    }
    var r0 = firstRow(m, "total_income"), r1 = inc;
    var rpp0 = r0 && metric(r0, "total_income").rpp, rpp1 = r1 && metric(r1, "total_income").rpp;
    if (c.realLabel && r0 && r1 && r0 !== r1 && isNum(rpp0) && isNum(rpp1)) {
      s3.bullets.push("In real terms, " + c.realLabel + ", all income per pupil went from " + fmtExact(rpp0) + " in " + r0.y + " to " + fmtExact(rpp1) + " in " + r1.y + ".");
      s3.sources.push(c.realLabel.replace(/^in /, "Real terms: "));
    }
    s3.note = [suspectNote(m), framing(c, "funding_vs_spending_per_pupil")].filter(Boolean).join(" ");
    s3.sources = schoolSources(m, c).slice(0, 1).concat(s3.sources, [framingSource(c, "funding_vs_spending_per_pupil")]).filter(Boolean);
    slides.push(s3);

    // 4. Reserve per pupil over the years, totals beside
    var s4 = slide("reserve", "chart", "Reserve per pupil over the years");
    s4.chart = chart("bar", "£ per pupil", [{ key: "revenue_reserve", name: "Reserve per pupil", points: points(m, "revenue_reserve", "pp") }]);
    m.rows.forEach(function (r) {
      var cr = metric(r, "revenue_reserve");
      if (cr && isNum(cr.v)) s4.bullets.push((r.suspect ? MARK + " " : "") + r.y + ": " + both(cr.pp, cr.v, true));
    });
    if (reserveRow) {
      var rr = metric(reserveRow, "revenue_reserve");
      s4.figures.push(figure("revenue_reserve", "Latest reserve", rr.v, rr.pp, reserveRow.y, src));
      s4.lead = rr.v < 0
        ? "The reserve is the savings a school carries from year to year. Below zero means it has spent more over the years than it received; the slides that follow show why that can happen and what helps."
        : "The reserve is the savings a school carries from year to year, for example to cover a pay rise before funding catches up.";
    } else {
      s4.lead = "Reserve figures for this school aren't published yet.";
    }
    s4.note = [suspectNote(m), "Each year is the reserve at the end of that year (" + src + ")."].filter(Boolean).join(" ");
    s4.sources = schoolSources(m, c).slice(0, 1);
    slides.push(s4);

    // 5. Where the money comes from
    var s5 = slide("income", "chart", "Where the money comes from");
    var ly = latestRow(m, "total_income");
    var lyY = ly ? ly.y : m.year;
    var useRow = ly && m.sx;
    function line5(key) {
      if (useRow && metric(ly, key) && isNum(metric(ly, key).v)) return { v: metric(ly, key).v, pp: metric(ly, key).pp };
      var v = m.incomeLines[key];
      return isNum(v) ? { v: v, pp: perPupil(v, ly ? ly.pupils : m.pupilsLatest) } : null;
    }
    var g5 = line5("grant_funding"), sg5 = line5("self_generated"), sen5 = line5("sen_funding"), pp5 = line5("pupil_premium"), don5 = line5("donations_revenue");
    var cat = [];
    if (g5) cat.push({ y: "Government grants", v: round(g5.pp), suspect: false });
    if (sg5) cat.push({ y: "Self-generated income", v: round(sg5.pp), suspect: false });
    s5.chart = chart("bar", "£ per pupil", [{ key: "income_lines", name: lyY ? "Per pupil, " + lyY : "Per pupil", points: cat }]);
    if (g5) s5.figures.push(figure("grant_funding", "Government grants", g5.v, g5.pp, lyY, src));
    if (sg5) s5.figures.push(figure("self_generated", "Self-generated income (lettings, catering, donations)", sg5.v, sg5.pp, lyY, src));
    var within = [];
    if (sen5) within.push("special needs (SEN) funding " + both(sen5.pp, sen5.v, true));
    if (pp5) within.push("pupil premium " + both(pp5.pp, pp5.v, true));
    if (within.length) s5.bullets.push("Within the grants: " + within.join(" and ") + ", " + lyY + ", " + src + ".");
    if (don5) s5.bullets.push("Within self-generated income: donations and voluntary funds " + both(don5.pp, don5.v, true) + ", " + lyY + ", " + src + ", which can include money from a parents' association.");
    if (!g5 && !sg5) s5.lead = "A breakdown of this school's income isn't published for this year.";
    else s5.lead = "Most of a school's money is government grants, paid mainly per pupil.";
    s5.note = framing(c, "pass_through_grants");
    s5.sources = schoolSources(m, c).slice(0, 1).concat([framingSource(c, "pass_through_grants")]).filter(Boolean);
    slides.push(s5);

    // 6. Where it goes: staff share
    var s6 = slide("spending", "chart", "Where the money goes");
    var sp = latestRow(m, "total_expenditure");
    var staffLine = ctxLine(c, "school", "staff_share");
    if (sp) {
      var ce6 = metric(sp, "total_expenditure"), cs6 = metric(sp, "staff_total");
      s6.figures.push(figure("total_expenditure", "Spending", ce6.v, ce6.pp, sp.y, src));
      if (cs6 && isNum(cs6.v) && isNum(ce6.v) && ce6.v > 0) {
        var share = cs6.v / ce6.v;
        s6.figures.push(figure("staff_total", "Staff costs", cs6.v, cs6.pp, sp.y, src, "£", { share: share }));
        s6.lead = "Staff costs were " + Math.round(share * 100) + "% of spending in " + sp.y + ": " + both(cs6.pp, cs6.v) + " (" + src + ", 'Staff Total').";
      } else {
        s6.lead = "A staff-cost total isn't published for this school's latest year.";
      }
    } else {
      s6.lead = "Spending figures for this school aren't published yet.";
    }
    var staffPts = [], otherPts = [];
    m.rows.forEach(function (r) {
      var e = metric(r, "total_expenditure"), stf = metric(r, "staff_total");
      var sv = stf && isNum(stf.pp) ? Math.round(stf.pp) : null;
      staffPts.push({ y: r.y, v: sv, suspect: r.suspect });
      otherPts.push({ y: r.y, v: sv != null && e && isNum(e.pp) ? Math.round(e.pp) - sv : null, suspect: r.suspect });
    });
    if (staffPts.some(function (p) { return p.v != null; })) {
      s6.chart = chart("stack", "£ per pupil", [{ key: "staff_total", name: "Staff costs", points: staffPts }, { key: "other_spending", name: "Everything else", points: otherPts }]);
    } else {
      var bars = SPEND_LINES.filter(function (l) { return isNum(m.pp[l[0]]); }).map(function (l) { return { y: l[1], v: round(m.pp[l[0]]), suspect: false }; });
      s6.chart = chart("bar", "£ per pupil", [{ key: "spend_lines", name: "Per pupil, " + (m.year || ""), points: bars }]);
    }
    if (staffLine) s6.bullets.push(staffLine.text);
    s6.bullets.push("The DfE staff total counts teachers, support, admin and supply staff. Premises and catering staff are counted under those headings, so the share can read lower than the national figure.");
    s6.note = suspectNote(m);
    s6.sources = schoolSources(m, c).slice(0, 1).concat(staffLine ? [ifsSource(c, staffLine.page)] : []);
    slides.push(s6);

    // 7. Compared with similar schools and the council
    var s7 = slide("compare", "chart", "Compared with similar schools and the council");
    var cy = latestRow(m, "total_expenditure");
    var y7 = cy ? cy.y : m.year;
    var group = areaGroup(m);
    var councilName = (m.area.ok && m.area.name) || m.council.name || "the council";
    var cmp = [["total_income", "incomePp", "Income"], ["total_expenditure", "spendPp", "Spending"]];
    var seriesSchool = [], seriesSimilar = [], seriesCouncil = [], seriesEngland = [];
    var usedGroup = null;
    cmp.forEach(function (k) {
      var mine = cy ? metric(cy, k[0]) : null;
      var minePp = mine && isNum(mine.pp) ? mine.pp : m.pp[k[0]];
      var sim = m.similar[k[0]];
      var ca = areaStat(m.area, y7, group, k[1]), en = areaStat(m.england, y7, group, k[1]);
      if (ca) usedGroup = ca.group;
      seriesSchool.push({ y: k[2] + " per pupil", v: round(minePp), suspect: false });
      seriesSimilar.push({ y: k[2] + " per pupil", v: round(sim), suspect: false });
      seriesCouncil.push({ y: k[2] + " per pupil", v: ca ? round(ca.v) : null, suspect: false });
      seriesEngland.push({ y: k[2] + " per pupil", v: en ? round(en.v) : null, suspect: false });
      var parts = [k[2] + ": " + fmtExact(minePp) + " per pupil here"];
      if (isNum(sim)) parts.push("similar schools' median " + fmtExact(sim));
      if (ca) parts.push(groupWords(ca.group, councilName) + " " + fmtExact(ca.v));
      if (en) parts.push(groupWords(en.group, "England") + " " + fmtExact(en.v));
      if (isNum(minePp)) s7.bullets.push(parts.join("; ") + " (" + y7 + ", " + src + "; medians from " + SITE + ").");
    });
    s7.chart = chart("bar", "£ per pupil", [
      { key: "school", name: m.name, points: seriesSchool },
      { key: "similar", name: "Similar schools (median)", points: seriesSimilar },
      { key: "council", name: councilName + " (median)", points: seriesCouncil },
      { key: "england", name: "England (median)", points: seriesEngland }
    ]);
    if (!Object.keys(m.similar).length) s7.bullets.push("Similar schools: there aren't enough comparable schools with published figures yet.");
    if (!m.area.ok || !m.area.by[y7]) s7.bullets.push("Council figures for " + (y7 || "this year") + " aren't published yet.");
    var diffs = SPEND_LINES.filter(function (l) { return isNum(m.pp[l[0]]) && isNum(m.similar[l[0]]); })
      .map(function (l) { return { label: l[1], mine: m.pp[l[0]], sim: m.similar[l[0]] }; })
      .sort(function (a, b) { return Math.abs(b.mine - b.sim) - Math.abs(a.mine - a.sim); }).slice(0, 2);
    diffs.forEach(function (d) {
      s7.bullets.push(d.label + ": " + fmtExact(d.mine) + " per pupil here, similar schools' median " + fmtExact(d.sim) + " (" + (m.year || y7) + ", " + src + ").");
    });
    s7.lead = "Similar schools are the same phase and size with a similar intake. A difference is a reason to ask why, not a judgement.";
    var mva = ctxLine(c, "school", "maintained_vs_academy");
    s7.note = mva ? mva.text : "";
    s7.sources = schoolSources(m, c).slice(0, 1).concat([AREA_SOURCE + (usedGroup ? " (" + usedGroup + " schools)" : "")], mva ? [ifsSource(c, mva.page)] : []);
    slides.push(s7);

    // 8. Pupils over the years
    var s8 = slide("pupils", "chart", "Pupils over the years");
    var withP = m.rows.filter(function (r) { return isNum(r.pupils); });
    s8.chart = chart("line", "pupils", [{ key: "pupils", name: "Pupils", points: m.rows.map(function (r) { return { y: r.y, v: isNum(r.pupils) ? Math.round(r.pupils * 10) / 10 : null, suspect: r.suspect }; }) }]);
    var falling = false;
    if (withP.length >= 2) {
      var p0 = withP[0], p1 = withP[withP.length - 1];
      var change = p1.pupils / p0.pupils - 1;
      var last4 = withP.slice(-4);
      var fellEach = last4.length === 4 && last4.every(function (r, i) { return i === 0 || r.pupils < last4[i - 1].pupils; });
      falling = change <= -0.05 || fellEach;
      s8.figures.push(figure("pupils", "Pupils", p1.pupils, null, p1.y, src, "pupils"));
      s8.lead = fmtPupils(p1.pupils) + " pupils in " + p1.y + ", " + (Math.abs(change) < 0.005 ? "about the same as" : (change < 0 ? "down " : "up ") +
        fmtPct(Math.abs(change) * 100) + " from") + " " + fmtPupils(p0.pupils) + " in " + p0.y + " (" + src + ").";
    } else {
      s8.lead = "Pupil numbers for this school aren't published for enough years to show a trend.";
    }
    var phaseLine = ctxLine(c, "school", m.phase === "secondary" ? "secondary_rolls" : "primary_rolls");
    if (falling) {
      s8.bullets.push("Schools are mostly funded per pupil, so fewer pupils means less money, while costs don't fall in step.");
      s8.note = framing(c, "falling_rolls");
      s8.sources.push(framingSource(c, "falling_rolls"));
    } else {
      s8.bullets.push("Schools are mostly funded per pupil, so pupil numbers drive most of the budget.");
      if (phaseLine && (m.phase === "primary" || m.phase === "secondary")) {
        s8.note = phaseLine.text;
        s8.sources.push(ifsSource(c, phaseLine.page));
      }
    }
    s8.sources = schoolSources(m, c).slice(0, 1).concat(s8.sources).filter(Boolean);
    slides.push(s8);

    // 9. IFS context and questions to ask
    var s9 = slide("questions", "questions", "Questions to ask");
    var reserveV = reserveRow ? metric(reserveRow, "revenue_reserve").v : null;
    var fill = function (t) {
      return String(t || "").replace(/\{name\}/g, m.name).replace(/\{overseer\}/g, m.overseer)
        .replace(/\{reserve\}/g, fmtMoney(reserveV)).replace(/\{years\}/g, String(m.streak));
    };
    var sets = [];
    if (st) sets.push(st.key);
    if (falling) sets.push("falling_rolls");
    if (m.academy) sets.push("academy");
    sets.push("any");
    var qs = [];
    sets.forEach(function (k) { (c.questions[k] || []).forEach(function (q) { if (q && q.text) qs.push(q); }); });
    qs.slice(0, 6).forEach(function (q) {
      var tail = q.why || q.page ? " (" + [q.why, q.page ? pages(q.page) : ""].filter(Boolean).join(" ") + ")" : "";
      s9.bullets.push(fill(q.text) + tail);
      if (q.page) s9.sources.push(ifsSource(c, q.page));
    });
    if (!qs.length) s9.bullets.push("What is the school's budget plan for the next three years, and what does it assume about pupil numbers and pay?");
    s9.lead = "Questions a parent, governor or PTFA member might ask, with context from the IFS annual report on education spending.";
    var notes = [];
    if (st && (st.key === "in_deficit" || st.key === "heading_for_deficit" || st.key === "tight")) {
      var cl = ctxLine(c, "school", "costs_outpaced_funding");
      if (cl) { notes.push(cl.text); s9.sources.push(ifsSource(c, cl.page)); }
    }
    var pl = ctxLine(c, "school", m.phase === "secondary" ? "per_pupil_secondary" : (m.phase === "primary" ? "per_pupil_primary" : ""));
    if (pl) { notes.push(pl.text); s9.sources.push(ifsSource(c, pl.page)); }
    if (m.academy) {
      var tl = ctxLine(c, "school", "trust_central");
      if (tl) { notes.push(tl.text); s9.sources.push(ifsSource(c, tl.page)); }
    }
    s9.note = notes.join(" ");
    s9.links = [{ text: "Guides for parents and governors", href: "/guides/" },
      { text: "The parents' association presentation", href: "/deck/?urn=" + encodeURIComponent(m.urn) + "&view=ptfa" }];
    if (m.path) s9.links.push({ text: "The school's page", href: m.path });
    slides.push(s9);

    // 10. Sources
    slides.push(sourcesSlide(slides, c, ["DfE Financial Benchmarking and Insights Tool: " + (c.links.fbit || "") + m.urn]));
    slides.forEach(function (x, i) { x.n = i + 1; });
    return { title: m.name + ": school money", filename: fileSafe(m.name) + " - " + SITE + ".pptx", kind: "school", slides: slides };
  }

  // ======================================================================
  // PTFA deck: 8 slides with a registered PTA, 6 without
  // ======================================================================
  function ptfaDeck(m, ctx) {
    var c = ctxOf(ctx);
    if (!m || !m.ok) return messageDeck("PTFA presentation", "This school's figures couldn't be loaded, so there is nothing to present yet.");
    var slides = [];
    var main = m.pta[0] || null;
    var registerBase = c.links.register || REGISTER_HOME;
    var guide = c.links.ptfa_guide || "/guides/ptfa/";
    var donRow = latestRow(m, "donations_revenue");
    var don = donRow ? metric(donRow, "donations_revenue") : null;
    var donY = donRow ? donRow.y : m.year;
    if (!don && isNum(m.incomeLines.donations_revenue)) {
      don = { v: m.incomeLines.donations_revenue, pp: perPupil(m.incomeLines.donations_revenue, m.pupilsLatest) };
    }
    var councilName = (m.area.ok && m.area.name) || m.council.name || "the council";

    var s1 = slide("title", "title", main ? main.name : m.name + ": parents' association");
    s1.lead = main
      ? "Parents' association money at " + m.name + (m.council.name ? ", " + m.council.name : "") + ". Charity " + main.number + "."
      : "Parents' association money at " + m.name + (m.council.name ? ", " + m.council.name : "") + ".";
    s1.bullets.push("Parents' associations (PTAs, PTFAs, friends' groups) raise money for extras the budget doesn't stretch to.");
    s1.bullets.push("Their figures come from the " + CHARITY_SOURCE + "; the school's own figures come from the " + m.source + ".");
    s1.sources = [CHARITY_SOURCE + (main ? ", charity " + main.number + ": " + registerBase + main.number : ": " + REGISTER_HOME)];
    slides.push(s1);

    var ideas = slide("ideas", "ideas", "Ideas that help");
    ideas.lead = "Suggestions other parents' associations have found useful. Pick what fits your school.";
    ideas.bullets = [
      "Claim Gift Aid on eligible donations from UK taxpayers: it adds 25p to every £1 given, at no cost to the giver.",
      "Ask parents and carers whether their employers offer match funding: many match what staff raise or volunteer for.",
      "Use the Gift Aid small donations scheme for cash and contactless gifts of £30 or less, where no declaration is needed (the association must also be claiming Gift Aid).",
      "Agree a wish-list with the school each year, so money goes where it helps most, and tell parents what it paid for.",
      main ? "Share the register figures with parents: seeing what last year paid for helps people give." :
        "If the association's income goes over £5,000 a year, it must register with the Charity Commission; the guide explains how."
    ];
    ideas.links = [{ text: "Our guide for PTFAs", href: guide }];
    ideas.sources = ["HMRC Gift Aid and Gift Aid small donations scheme guidance (GOV.UK)", "Charity Commission: registering a charity (GOV.UK)"];

    if (!main) {
      var n1 = slide("not_found", "note", "No registered parents' association found");
      n1.lead = "No registered parents' association found for " + m.name + " on the " + CHARITY_SOURCE + ".";
      n1.bullets = [
        "Charities with an income of £5,000 or less a year don't have to register with the Charity Commission, so a smaller PTA may not appear on the register.",
        "A PTA may be registered under another name, such as 'Friends of " + m.name + "', or run as part of the school rather than as its own charity.",
        "How registration works: once its income is over £5,000 a year, a parents' association applies to the Charity Commission with its constitution, then files figures every year. Those yearly figures are what this site reads. Charitable incorporated organisations register whatever their income.",
        "The school's own donations line may still show parents' giving (next slide)."
      ];
      n1.links = [{ text: "Search the charity register", href: REGISTER_HOME }, { text: "Does a PTA need to register?", href: guide + "#do-you-need-to-register" }];
      n1.sources = [CHARITY_SOURCE + ": " + REGISTER_HOME];
      slides.push(n1);

      var n2 = slide("donations", "note", "Parents' giving in the school's own accounts");
      if (don && isNum(don.v)) {
        n2.figures.push(figure("donations_revenue", "Donations and voluntary funds", don.v, don.pp, donY, m.source));
        n2.lead = "The school's donations and voluntary funds line was " + both(don.pp, don.v) + " in " + donY + " (" + m.source + "). It includes fundraising and parents' contributions paid into the school budget.";
      } else {
        n2.lead = "The school's donations figure isn't published for this year.";
      }
      n2.note = "This line can include money a parents' association passes to the school, which is why the two are never added together.";
      n2.sources = schoolSources(m, c).slice(0, 1);
      slides.push(n2);
      slides.push(ptaCompareSlide(m, c, null, councilName));
      slides.push(ideas);
      slides.push(sourcesSlide(slides, c));
      slides.forEach(function (x, i) { x.n = i + 1; });
      return { title: m.name + ": parents' association", filename: fileSafe(m.name) + " - PTFA - " + SITE + ".pptx", kind: "ptfa", slides: slides };
    }

    // Income and spending over the years
    var yrs = main.years;
    var last = null;
    for (var i = yrs.length - 1; i >= 0; i--) { if (isNum(yrs[i].income)) { last = yrs[i]; break; } }
    var yearText = function (e) { return e.y + (e.end ? " (charity year to " + e.end + ")" : " (charity year)"); };
    var s2 = slide("pta_money", "chart", "Money raised and spent");
    s2.chart = chart("bar", "£", [
      { key: "pta_income", name: "Income", points: yrs.map(function (e) { return { y: e.y, v: round(e.income), suspect: false }; }) },
      { key: "pta_spend", name: "Spending", points: yrs.map(function (e) { return { y: e.y, v: round(e.spend), suspect: false }; }) }
    ]);
    if (last) s2.figures.push(figure("pta_income", "Latest income", last.income, last.incomePp, yearText(last), CHARITY_SOURCE));
    yrs.forEach(function (e) {
      s2.bullets.push(e.y + ": raised " + both(e.incomePp, e.income, true) + (isNum(e.spend) ? ", spent " + both(e.spendPp, e.spend, true) : ""));
    });
    s2.lead = "Years are the charity's own financial years" + (main.fye ? ", ending " + main.fye : "") + ", as filed with the " + CHARITY_SOURCE + ".";
    s2.note = "Charity years don't line up with the school's " + (m.academy ? "September-to-August" : "April-to-March") + " years. Per-pupil figures use the school's pupil count for the matching school year.";
    s2.sources = [CHARITY_SOURCE + ", charity " + main.number + ": " + registerBase + main.number];
    slides.push(s2);

    // The charity and its registration
    var s3 = slide("charity", "note", "The charity and its registration");
    s3.lead = main.name + " is registered with the Charity Commission as charity " + main.number + ".";
    s3.bullets = ["Charity number: " + main.number];
    if (main.status) s3.bullets.push("Register status: " + main.status);
    if (main.fye) s3.bullets.push("Financial year ends: " + main.fye);
    if (last) s3.bullets.push("Latest income: " + both(last.incomePp, last.income) + ", " + yearText(last) + ", " + CHARITY_SOURCE + ".");
    if (m.pta.length > 1) {
      s3.bullets.push("Also linked to the school: " + m.pta.slice(1).map(function (p) { return p.name + " (" + p.number + ")"; }).join(", ") + ".");
    }
    s3.bullets.push("Registered charities report their income and spending to the Charity Commission every year; above £25,000 they also send their accounts.");
    s3.links = [{ text: "Charity " + main.number + " on the register", href: registerBase + main.number }];
    s3.sources = s2.sources.slice();
    slides.push(s3);

    slides.push(ptaCompareSlide(m, c, last, councilName));

    // The PTA gap in context
    var s5 = slide("pta_gap", "note", "The PTA gap in context");
    var gapLines = [];
    function gapLine(g, where) {
      if (isNum(g)) return "Gap" + (where ? " (" + where + ")" : "") + ": " + fmtExact(g) + " per pupil.";
      if (isObj(g)) {
        if (typeof g.text === "string" && g.text) return g.text;
        var v = isNum(g.pp) ? g.pp : isNum(g.gap_pp) ? g.gap_pp : isNum(g.value) ? g.value : null;
        if (v != null) return "Gap compared with " + (g.vs || g.label || "the comparison group") + ": " + fmtExact(v) + " per pupil" + (g.year ? ", " + g.year : "") + ".";
      }
      return null;
    }
    var gl = gapLine(m.gap, null);
    if (gl) gapLines.push(gl + " (" + CHARITY_SOURCE + "; " + SITE + ")");
    var al = m.area.ok ? (m.area.ptaText || gapLine(m.area.ptaGap, councilName)) : null;
    if (al) gapLines.push(al + " (" + CHARITY_SOURCE + "; " + SITE + ")");
    s5.bullets = gapLines.concat([
      "Parents' associations raise very different amounts from school to school, often in step with how much families can give rather than how much the school needs.",
      "The IFS annual report on education spending, the main national analysis, doesn't cover money raised by parents' associations.",
      "A PTA's income is extra, not a measure of the school; it pays for things the budget doesn't stretch to."
    ]);
    s5.lead = "What parents raise depends on who the parents are as much as on the effort they put in.";
    s5.sources = [CHARITY_SOURCE, c.cite + (c.url ? ": " + c.url : "")];
    slides.push(s5);

    // Overlap note
    var s6 = slide("overlap", "note", "PTA money and the school's own accounts");
    s6.lead = "Money a PTA gives the school can also appear in the school's own donations income, so the two are never added together here.";
    if (last) s6.figures.push(figure("pta_income", "Parents' association income", last.income, last.incomePp, yearText(last), CHARITY_SOURCE));
    if (don && isNum(don.v)) s6.figures.push(figure("donations_revenue", "School donations and voluntary funds", don.v, don.pp, donY, m.source));
    s6.bullets = [
      "The school's donations line counts fundraising and parents' contributions paid into its budget, which can include money from the PTA.",
      "The charity's year (to " + (main.fye || "its year end") + ") and the school's year differ, so the overlap can't be measured from published figures."
    ];
    s6.note = "Show them side by side, never as a sum.";
    s6.sources = s2.sources.concat(schoolSources(m, c).slice(0, 1));
    slides.push(s6);

    slides.push(ideas);
    slides.push(sourcesSlide(slides, c));
    slides.forEach(function (x, i) { x.n = i + 1; });
    return { title: main.name, filename: fileSafe(m.name) + " - PTFA - " + SITE + ".pptx", kind: "ptfa", slides: slides };
  }

  function ptaCompareSlide(m, c, last, councilName) {
    var sl = slide("pta_compare", "chart", "How it compares");
    var y = last ? last.y : null;
    var years = m.area.ok ? m.area.years.slice().reverse() : [];
    var yA = y && m.area.ok && m.area.by[y] ? y : null;
    if (!yA) {
      for (var i = 0; i < years.length; i++) { if (areaStat(m.area, years[i], "all", "ptaPp")) { yA = years[i]; break; } }
    }
    var ca = yA ? areaStat(m.area, yA, "all", "ptaPp") : null;
    var en = yA ? areaStat(m.england, yA, "all", "ptaPp") : null;
    var caN = yA ? areaStat(m.area, yA, "all", "ptaSchools") : null;
    var pts = [];
    if (last && isNum(last.incomePp)) pts.push({ y: "This PTA", v: round(last.incomePp), suspect: false });
    if (ca) pts.push({ y: councilName + " median", v: round(ca.v), suspect: false });
    if (en) pts.push({ y: "England median", v: round(en.v), suspect: false });
    sl.chart = chart("bar", "£ per pupil", [{ key: "pta_pp", name: "Parents' association income per pupil", points: pts }]);
    if (last && isNum(last.incomePp)) sl.figures.push(figure("pta_income", "This PTA", last.income, last.incomePp, last.y + " (charity year)", CHARITY_SOURCE));
    if (ca) {
      sl.figures.push(figure("pta_council_median", "Median in " + councilName, null, ca.v, yA, CHARITY_SOURCE + "; " + SITE));
      sl.bullets.push("Among " + (caN ? plural(caN.v, "school") + " in " + councilName + " with a registered parents' association" : "schools in " + councilName + " with a registered parents' association") +
        ", the median raised was " + fmtExact(ca.v) + " per pupil (" + yA + ", " + CHARITY_SOURCE + ").");
    } else {
      sl.bullets.push("There aren't enough registered parents' associations in " + councilName + " with published figures to show a median.");
    }
    if (en) sl.figures.push(figure("pta_england_median", "Median in England", null, en.v, yA, CHARITY_SOURCE + "; " + SITE));
    var bands = m.area.ok && m.area.ptaBands ? m.area.ptaBands : (m.england.ok ? m.england.ptaBands : null);
    if (!bands && yA) {
      var sb = areaStat(m.area, yA, "all", "ptaBands") || areaStat(m.england, yA, "all", "ptaBands");
      bands = sb ? sb.v : null;
    }
    var bandV = bands && m.band != null ? bands[String(m.band)] : null;
    if (typeof bandV === "number" && isFinite(bandV)) {
      sl.bullets.push("Schools with a similar intake (band " + m.band + " of 5, where 1 is the most affluent): median " + fmtExact(bandV) + " per pupil (" + (yA || "latest year") + ", " + CHARITY_SOURCE + ").");
    } else {
      sl.bullets.push("A comparison with schools of a similar intake (free school meals band) isn't available yet.");
    }
    sl.lead = "What this parents' association raises per pupil, beside the typical figure nearby.";
    sl.note = "Medians count only schools whose parents' association is registered and has filed figures.";
    sl.sources = [CHARITY_SOURCE, AREA_SOURCE];
    return sl;
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
    var slides = [];
    var s1 = slide("title", "title", "Comparing " + ms.length + " schools");
    s1.lead = ms.map(function (m) { return m.name; }).join(", ");
    ms.forEach(function (m) {
      var r = latestRow(m, "total_income");
      s1.bullets.push(m.name + (m.council.name ? ", " + m.council.name : "") + (r && isNum(r.pupils) ? ": " + fmtPupils(r.pupils) + " pupils, " + r.y + ", " + m.source : ""));
    });
    s1.note = "Each school's latest published year is used, so years can differ between schools.";
    s1.sources = ms.map(function (m) { return m.name + ": " + schoolSources(m, c)[0]; });
    slides.push(s1);

    function measure(id, title, key, label) {
      var sl = slide(id, "chart", title);
      var pts = [], years = {};
      ms.forEach(function (m) {
        var r = latestRow(m, key);
        var cell = r ? metric(r, key) : null;
        pts.push({ y: m.name, v: cell ? round(cell.pp) : null, suspect: false });
        if (r) years[r.y] = 1;
        if (cell) sl.figures.push(figure(key, m.name, cell.v, cell.pp, r.y, m.source));
        else sl.bullets.push(m.name + ": " + label.toLowerCase() + " isn't published yet.");
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
    ms.forEach(function (m) {
      if (!m.status) { s5.bullets.push(m.name + ": no full year of figures to assess yet."); return; }
      if (m.status.key === "in_deficit" || m.status.key === "heading_for_deficit") anyDeficit = true;
      s5.statuses.push({ key: m.status.key, label: m.status.label, icon: m.status.icon, name: m.name });
      s5.bullets.push(m.status.icon + " " + m.status.label + ": " + m.name + (m.status.reason ? ". " + m.status.reason : "") + (m.status.year ? " (" + m.status.year + ", " + m.source + ")" : ""));
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
    ms.forEach(function (m) {
      var r = null;
      for (var i = m.rows.length - 1; i >= 0; i--) { if (isNum(m.rows[i].pupils) && !m.rows[i].suspect) { r = m.rows[i]; break; } }
      pp6.push({ y: m.name, v: r ? Math.round(r.pupils * 10) / 10 : null, suspect: false });
      if (r) s6.figures.push(figure("pupils", m.name, r.pupils, null, r.y, m.source, "pupils"));
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
      s3.bullets.push(k[1] + ": median " + fmtExact(S[k[0]]) + " per pupil here" + (ES[k[0]] != null ? ", " + fmtExact(ES[k[0]]) + " across England" : "") + " (" + ly + ", " + AREA_SOURCE + ").");
    });
    if (!s3.bullets.length) s3.bullets.push("There aren't enough schools with published figures here to show medians.");
    s3.lead = "The middle school's figure (the median), so one very large or very small school doesn't skew it.";
    s3.note = framing(c, "funding_vs_spending_per_pupil");
    s3.sources = [AREA_SOURCE, framingSource(c, "funding_vs_spending_per_pupil")].filter(Boolean);
    slides.push(s3);

    if (A.type === "council") {
      var s4 = slide("dsg", "chart", "High-needs money (Dedicated Schools Grant)");
      var dys = Object.keys(A.dsg).sort();
      s4.chart = chart("bar", "£ per pupil", [{ key: "dsg_pp", name: "DSG balance per pupil", points: dys.map(function (y) { return { y: y, v: round(A.dsg[y].pp), suspect: false }; }) }]);
      var dl = null;
      for (var i = dys.length - 1; i >= 0; i--) { if (isNum(A.dsg[dys[i]].balance)) { dl = dys[i]; break; } }
      if (dl) {
        var d = A.dsg[dl];
        s4.figures.push(figure("dsg", "DSG balance at 31 March", d.balance, d.pp, dl, DSG_SOURCE));
        s4.lead = "The council's Dedicated Schools Grant balance was " + both(d.pp, d.balance) + " at the end of " + dl + " (" + DSG_SOURCE + ")" +
          (d.balance < 0 ? ". A negative balance mostly reflects special needs (high needs) costs running ahead of the grant." : ".");
      } else {
        s4.lead = "The council's Dedicated Schools Grant balance isn't published for these years.";
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
  function chartData(ch) {
    if (!ch || !ch.series || !ch.series.length) return [];
    var labels = [];
    ch.series.forEach(function (s) { s.points.forEach(function (p) { if (labels.indexOf(p.y) === -1) labels.push(p.y); }); });
    return ch.series.map(function (s) {
      var byY = {};
      s.points.forEach(function (p) { byY[p.y] = p; });
      return {
        name: s.name,
        labels: labels.map(function (y) { return byY[y] && byY[y].suspect ? y + " " + MARK : y; }),
        values: labels.map(function (y) { return byY[y] && isNum(byY[y].v) ? byY[y].v : null; })
      };
    });
  }
  function buildPptx(deck, PptxGenJS, palette) {
    var p = isObj(palette) ? palette : {};
    var col = {
      paper: hex(p.paper, "FFFFFF"), ink: hex(p.ink, "222222"), ink2: hex(p["ink-2"] || p.ink2, "555555"), line: hex(p.line, "CCCCCC"),
      grid: hex(p.grid, "E5E5E5"), accent: hex(p.accent, "555555"),
      series: [hex(p.c1, "333333"), hex(p.c2, "777777"), hex(p.c3, "999999"), hex(p.c4, "BBBBBB")],
      status: {}
    };
    ORDER.forEach(function (k, i) { col.status[k] = hex(p[["critical", "serious", "warning", "good", "plenty"][i]], col.ink); });
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
      if (sl.lead) {
        s.addText(sl.lead, { x: 0.4, y: y, w: 9.2, h: 0.6, fontSize: 13, color: col.ink, fontFace: "Arial", valign: "top", fit: "shrink" });
        y += 0.65;
      }
      var hasChart = !!(sl.chart && sl.chart.series && sl.chart.series.length);
      var paras = [];
      sl.figures.forEach(function (f) {
        paras.push({ text: f.label + ": ", options: { bold: true, color: col.ink } });
        paras.push({ text: f.text, options: { color: col.ink, breakLine: true } });
      });
      sl.bullets.forEach(function (b) { paras.push({ text: b, options: { bullet: true, color: col.ink, breakLine: true } }); });
      (sl.links || []).forEach(function (l) {
        var href = /^https?:/.test(l.href) ? l.href : (deck.base || "https://money.schoolsinreach.com") + l.href;
        paras.push({ text: l.text, options: { hyperlink: { url: href }, color: col.accent, breakLine: true } });
      });
      var bodyH = 4.55 - y;
      if (paras.length) {
        s.addText(paras, { x: 0.4, y: y, w: hasChart ? 4.5 : 9.2, h: bodyH, fontSize: 11, fontFace: "Arial", valign: "top", fit: "shrink", paraSpaceAfter: 3 });
      }
      if (hasChart) {
        var ch = sl.chart;
        var type = ch.type === "line" ? (types.line || "line") : (types.bar || "bar");
        var fmt = ch.unit === "%" ? '0.0"%"' : ch.unit === "pupils" ? "#,##0.#" : "£#,##0";
        s.addChart(type, chartData(ch), {
          x: 5.05, y: y, w: 4.55, h: bodyH, chartColors: col.series.slice(0, Math.max(ch.series.length, 1)),
          barDir: "col", barGrouping: ch.type === "stack" ? "stacked" : "clustered", overlap: ch.type === "stack" ? 100 : undefined,
          showLegend: ch.series.length > 1, legendPos: "b", legendFontSize: 9, legendColor: col.ink2,
          catAxisLabelColor: col.ink2, valAxisLabelColor: col.ink2, catAxisLabelFontSize: 9, valAxisLabelFontSize: 9,
          valAxisLabelFormatCode: fmt, valGridLine: { color: col.grid, size: 0.5 }, catGridLine: { style: "none" },
          lineSize: 2, lineDataSymbol: "circle", lineDataSymbolSize: 6, altText: ch.alt
        });
      }
      if (sl.note) s.addText(sl.note, { x: 0.4, y: 4.6, w: 9.2, h: 0.65, fontSize: 9, color: col.ink2, fontFace: "Arial", valign: "top", fit: "shrink" });
      s.addText(SITE + " · " + deck.title + " · " + (idx + 1) + " / " + total, { x: 0.4, y: 5.28, w: 9.2, h: 0.25, fontSize: 8, color: col.ink2, fontFace: "Arial" });
      s.addNotes((sl.sources && sl.sources.length ? sl.sources : ["Source: " + SITE]).join("\n"));
    });
    return pptx.writeFile({ fileName: deck.filename });
  }

  var API = {
    adapt: adapt, schoolDeck: schoolDeck, ptfaDeck: ptfaDeck, compareDeck: compareDeck, areaDeck: areaDeck,
    nextIndex: nextIndex, buildPptx: buildPptx, chartData: chartData, fmtExact: fmtExact, fmtPupils: fmtPupils,
    hex: hex, PPTX_URL: PPTX_URL, LABELS: LABELS, ICONS: ICONS
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
  var state = { deck: null, i: 0, sections: [] };
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
          svg.appendChild(svgEl("circle", { "class": "dot s" + (si + 1) + (marked ? " suspect" : ""), cx: cx(i), cy: y(v), r: marked ? 5 : 3.5 }));
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
        });
      });
    }
    return svg;
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
    if (sl.lead) sec.appendChild(el("p", "slide-lead", sl.lead));
    var body = el("div", "slide-body" + (sl.chart ? " has-chart" : ""));
    var text = el("div", "slide-text");
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
    body.appendChild(text);
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
    var foot = el("footer", "slide-foot");
    foot.appendChild(el("span", null, SITE + " · " + deck.title));
    foot.appendChild(el("span", null, (i + 1) + " / " + n));
    sec.appendChild(foot);
    return sec;
  }
  function render(deck) {
    state.deck = deck;
    deck.base = base;
    appEl.textContent = "";
    appEl.classList.add("is-paged");
    var n = deck.slides.length;
    state.sections = deck.slides.map(function (sl, i) { var s = renderSlide(sl, i, n, deck); appEl.appendChild(s); return s; });
    var h1 = document.querySelector("h1.deck-title");
    if (h1) h1.textContent = deck.title;
    if (deck.title) document.title = deck.title + " | Presentation | " + SITE;
    if (toolbar) toolbar.hidden = false;
    var pptxBtn = document.querySelector('[data-deck="pptx"]');
    if (pptxBtn) pptxBtn.disabled = !!deck.message;
    var fromHash = /^#s(\d+)$/.exec(location.hash || "");
    go(fromHash ? Math.min(+fromHash[1] - 1, n - 1) : 0, true);
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
      "critical", "serious", "warning", "good", "plenty"].forEach(function (k) { out[k] = cs.getPropertyValue("--" + k).trim(); });
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

  function showMessage(title, text, links) { render(messageDeck(title, text, links)); say(text); }
  function load() {
    var q = new URLSearchParams(location.search);
    var view = (q.get("view") || "school").toLowerCase();
    var urnsQ = q.get("urns"), areaQ = q.get("area"), urnQ = q.get("urn");
    appEl.textContent = "";
    appEl.appendChild(el("p", "deck-wait", "Building the slides…"));
    if (urnsQ || view === "compare") {
      var urns = String(urnsQ || urnQ || "").split(",").map(function (u) { return u.trim(); })
        .filter(function (u, i, a) { return /^\d{1,8}$/.test(u) && a.indexOf(u) === i; });
      return Promise.all(urns.map(function (u) {
        return Promise.all([getJSON("/data/s/" + u + ".json"), getJSON("/data/sx/" + u + ".json")]);
      })).then(function (res) {
        var missing = [];
        var list = res.filter(function (r, i) { if (!r[0].ok) missing.push(urns[i]); return r[0].ok; })
          .map(function (r) { return { s: r[0].data, sx: r[1].ok ? r[1].data : null }; });
        render(compareDeck(list, ctx));
        if (missing.length) say("Figures for " + missing.join(", ") + " aren't published, so " + (missing.length === 1 ? "that school is" : "those schools are") + " left out.");
      });
    }
    if (areaQ) {
      if (!/^[A-Za-z0-9-]{1,60}$/.test(areaQ)) { showMessage("Area presentation", "That area link doesn't look right. Choose a council or constituency instead."); return Promise.resolve(); }
      return Promise.all([getJSON("/data/a/" + encodeURIComponent(areaQ) + ".json"), getJSON("/data/a/england.json")]).then(function (r) {
        if (!r[0].ok) { showMessage("Area presentation", "Figures for this area are " + r[0].why + ", so there is nothing to present yet."); return; }
        render(areaDeck(r[0].data, r[1].ok ? r[1].data : null, ctx));
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
          render(view === "ptfa" ? ptfaDeck(m, ctx) : schoolDeck(m, ctx));
          if (!r[1].ok) say("Year-by-year detail for this school isn't published yet, so the slides use the summary figures.");
        });
      });
    }
    var pins = [];
    try { pins = JSON.parse(localStorage.getItem("moneyPinned") || "[]") || []; } catch (e) { pins = []; }
    var schools = (Array.isArray(pins) ? pins : []).filter(function (p) { return p && p.type === "school" && /^\d{1,8}$/.test(String(p.id)); });
    var links = [{ text: "Search for a school", href: "/search/" }, { text: "Browse councils", href: "/council/" }];
    schools.slice(0, 6).forEach(function (p) { links.push({ text: "Present " + p.name, href: "/deck/?urn=" + p.id + "&view=school" }); });
    if (schools.length >= 2) links.push({ text: "Compare your " + Math.min(schools.length, 6) + " pinned schools", href: "/deck/?urns=" + schools.slice(0, 6).map(function (p) { return p.id; }).join(",") + "&view=compare" });
    showMessage("Choose what to present", "Open a school, council or constituency page and choose its presentation, or pick from your pinned schools.", links);
    return Promise.resolve();
  }
  load().catch(function () { showMessage("Presentation", "Something went wrong building the slides. Reload the page to try again."); });
})(typeof globalThis !== "undefined" ? globalThis : this);
