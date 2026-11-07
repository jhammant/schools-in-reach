/* School Money — wrapped.js (unit C3): School Wrapped and PTFA Wrapped.
   A tap-through story of one school's year in money, drawn on a 1080x1920 canvas, that can be saved as a
   vertical MP4 (WebCodecs + mp4-muxer), a WebM (MediaRecorder) or one PNG per card, and shared.

   Pure model exported as globalThis.MoneyWrapped (tested under node); DOM wiring runs only in a browser.
   Reads: /data/s/<urn>.json, /data/sx/<urn>.json, /data/a/council-<code>.json, /data/a/england.json,
          /data/wrapped/context.json (IFS lines with page numbers, real_label, base_url; written by wrapped.py).
   Every field of those documents is read in adapt(), so a contract change is one edit there.
   Data reaches the DOM through textContent and setAttribute only. */
(function (root) {
  "use strict";

  // Pinned libraries, loaded on first use. Hashes checked against the jsDelivr data API and the cdnjs API.
  // mp4-muxer 5.2.1 ships no .min.js file (jsDelivr would minify on the fly, with no stable hash), so the
  // published build/mp4-muxer.js is used.
  var MP4_MUXER_URL = "https://cdn.jsdelivr.net/npm/mp4-muxer@5.2.1/build/mp4-muxer.js";
  var MP4_MUXER_SRI = "sha256-zE0wvSC5/+CxX1nPDePhkwYmzNRqUUbjbk1hnX/s9j0=";
  var QRCODE_URL = "https://cdnjs.cloudflare.com/ajax/libs/qrcode-generator/1.4.4/qrcode.min.js";
  var QRCODE_SRI = "sha512-ZDSPMa/JM1D+7kdg2x3BsruQ6T/JpJo3jWDWkCZsP+5yVyp1KfESqLI+7RqB5k24F7p2cV7i2YHh/890y6P6Sw==";

  var W = 1080, H = 1920;
  var FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif";
  var CODECS = ["avc1.640028", "avc1.4d0028", "avc1.42e028"];
  var BITRATE = 6e6;
  var BASE_URL = "https://money.schoolsinreach.com";
  var CHARITY_URL = "https://register-of-charities.charitycommission.gov.uk/charity-search/-/charity-details/";
  var FBIT_URL = "https://financial-benchmarking-and-insights-tool.education.gov.uk/school/";
  var STATUS = {
    in_deficit: { label: "In deficit", icon: "▼", colour: "critical" },
    heading_for_deficit: { label: "Heading for deficit", icon: "↘", colour: "serious" },
    tight: { label: "Tight", icon: "●", colour: "warning" },
    healthy: { label: "Healthy", icon: "✓", colour: "good" },
    large_reserves: { label: "Large reserves", icon: "▲", colour: "plenty" }
  };
  var PALETTE_KEYS = ["paper", "card", "card-2", "line", "line-strong", "ink", "ink-2", "ink-3", "accent", "accent-ink",
    "accent-soft", "critical", "serious", "warning", "good", "plenty", "c1", "c2", "grid", "band"];
  // Used only when context.json can't be read: plain wording with no page references.
  var FALLBACK_CTX = {
    staff: { line: { text: "Most of a school's money goes on staff.", page: null } },
    framings: {},
    what_helps: {},
    pta: {
      not_found: "No registered parents' association found",
      register_note: "Charities with an income of £5,000 or less don't have to register with the Charity Commission, so a small parents' association may still exist.",
      overlap_note: "Money a parents' association gives the school can also appear in the school's own donations income, so the two are never added together.",
      source: "Charity Commission register",
      register_url: "https://www.gov.uk/setting-up-charity/register-your-charity"
    },
    why_fallback: "A deficit usually comes from several pressures at once: pay and other costs rising faster than funding, fewer pupils, or more support for special needs.",
    help_fallback: "What helps: a plan agreed with the council or trust, and parents and governors who know what it protects."
  };

  // ======================================================================
  // Small pure helpers
  // ======================================================================
  function obj(v) { return v && typeof v === "object" && !Array.isArray(v) ? v : {}; }
  function arr(v) { return Array.isArray(v) ? v : []; }
  function num(v) {
    if (typeof v === "number" && isFinite(v)) return v;
    if (typeof v === "string" && v.trim() !== "" && isFinite(Number(v))) return Number(v);
    return null;
  }
  function first(o, keys) {
    o = obj(o);
    for (var i = 0; i < keys.length; i++) if (o[keys[i]] != null) return o[keys[i]];
    return null;
  }
  function firstNum(o, keys) {
    o = obj(o);
    for (var i = 0; i < keys.length; i++) { var v = num(o[keys[i]]); if (v != null) return v; }
    return null;
  }
  function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }
  function app() { return root.MoneyApp || null; }
  function group(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ","); }
  function fmtExact(v, signed) {
    if (v == null || typeof v !== "number" || !isFinite(v)) return "—";
    var r = Math.round(v), sign = r < 0 ? "-" : (signed && r > 0 ? "+" : "");
    return sign + "£" + group(Math.abs(r));
  }
  function fmtMoney(v, signed) {
    var A = app();
    if (A && A.fmtMoney) return A.fmtMoney(v, signed);
    if (v == null || typeof v !== "number" || !isFinite(v)) return "—";
    var sign = v < 0 ? "-" : (signed && v > 0 ? "+" : ""), a = Math.abs(v);
    if (a >= 1e9) return sign + "£" + (a / 1e9).toFixed(2) + "bn";
    if (a >= 1e6) return sign + "£" + (a / 1e6).toFixed(1) + "m";
    if (a >= 1e3) return sign + "£" + Math.round(a / 1e3) + "k";
    return sign + "£" + Math.round(a);
  }
  function perPupil(v, pupils) {
    if (v == null || !isFinite(v) || !pupils || !(pupils > 0)) return null;
    return Math.round(v / pupils);
  }
  function fmtPupils(v) {
    if (v == null || !isFinite(v)) return "—";
    var t = (Math.round(v * 10) / 10).toFixed(1);
    if (/\.0$/.test(t)) t = t.slice(0, -2);
    var parts = t.split(".");
    return group(parts[0]) + (parts[1] ? "." + parts[1] : "");
  }
  function pct(a) { return Math.round(a * 100) + "%"; }
  function pence(share) { return Math.round(share * 100) + "p"; }
  function slugify(s) {
    var A = app();
    if (A && A.slugify) return A.slugify(s);
    return String(s || "").toLowerCase().replace(/&/g, " and ").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80) || "school";
  }
  function titleCase(s) {
    s = String(s || "");
    if (s !== s.toUpperCase()) return s;
    var small = { and: 1, of: 1, the: 1, for: 1, at: 1, "&": 1 };
    return s.toLowerCase().split(" ").map(function (w, i) {
      return i > 0 && small[w] ? w : w.charAt(0).toUpperCase() + w.slice(1);
    }).join(" ");
  }
  function ref(pages) {
    var p = arr(pages).filter(function (x) { return x != null; });
    if (!p.length) return "";
    return " (IFS, " + (p.length > 1 ? "pp." + p.join(", ") : "p." + p[0]) + ")";
  }
  function withRef(line) {
    if (!line || !line.text) return null;
    return line.text + ref(line.pages || (line.page != null ? [line.page] : []));
  }
  function sentences(text) {
    return String(text || "").match(/[^.!?]+[.!?]+(?=\s|$)/g) || (text ? [String(text)] : []);
  }
  // A year label ("2024-25") from a period end date: years ending January to August belong to the
  // academic or financial year that started the previous calendar year.
  function yearOfPeriodEnd(d) {
    var m = /^(\d{4})-(\d{2})/.exec(String(d || ""));
    if (!m) return null;
    var y = Number(m[1]), start = Number(m[2]) <= 8 ? y - 1 : y;
    return start + "-" + String((start + 1) % 100).replace(/^(\d)$/, "0$1");
  }
  function monthYear(d) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(d || ""));
    if (!m) return null;
    var names = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
    return Number(m[3]) + " " + names[Number(m[2]) - 1] + " " + m[1];
  }
  function sourceLabel(src, academy) {
    var s = String(src || "").toUpperCase();
    if (s.indexOf("AAR") !== -1) return "DfE AAR return";
    if (s.indexOf("CFR") !== -1) return "DfE CFR return";
    return academy ? "DfE AAR return" : "DfE CFR return";
  }
  // flags: ["2022-23"], [{year, code, text}] or {"2022-23": [...]}. Returns {year: [notes]}.
  function suspectYears(flags) {
    var out = {};
    function add(y, note) {
      if (y == null || y === "") return;
      y = String(y);
      if (!out[y]) out[y] = [];
      if (note) out[y].push(String(note));
    }
    function noteOf(x) { return typeof x === "string" ? x : (x && typeof x === "object" ? (x.text || x.code || null) : null); }
    if (Array.isArray(flags)) {
      flags.forEach(function (f) {
        if (typeof f === "string" || typeof f === "number") add(f);
        else if (f && typeof f === "object") add(f.year != null ? f.year : f.y, f.text || f.code);
      });
    } else if (flags && typeof flags === "object") {
      Object.keys(flags).forEach(function (y) {
        add(y);
        (Array.isArray(flags[y]) ? flags[y] : [flags[y]]).forEach(function (x) { var n = noteOf(x); if (n) out[y].push(n); });
      });
    }
    return out;
  }
  function fill(text, vars) {
    return String(text || "").replace(/\{(\w+)\}/g, function (m, k) { return vars[k] != null ? vars[k] : m; });
  }

  // ======================================================================
  // adapt(): the single reader of the data contracts
  // ======================================================================
  // [SERIES keys in /data/sx (first found wins; series.METRICS names first), /data/s years-row key]
  var METRICS = {
    income: [["total_income"], "income"], spend: [["total_expenditure"], "spend"], balance: [["in_year_balance"], "balance"],
    reserve: [["revenue_reserve"], "reserve"], grant: [["grant_funding_government", "grant_funding"], "grant"],
    staff: [["total_staff", "staff_total"], "staff"], donations: [["donations_revenue"], "donations"],
    premises: [["premises"], "premises"], energy: [["energy"], "energy"], supplies: [["educational_supplies"], "supplies"],
    services: [["bought_in_services"], "services"], sen: [["sen_funding"], "sen"],
    self: [["self_generated_income", "self_generated"], "self"]
  };

  function areaView(a, wantYear) {
    a = obj(a);
    if (!Object.keys(a).length) return null;
    var byYear = obj(a.by_year), years = Object.keys(byYear).sort(), year = null, S = {};
    for (var i = years.length - 1; i >= 0; i--) {
      var all = obj(first(byYear[years[i]], ["all", "All"]));
      if (num(all.schools) != null && (!wantYear || years[i] <= wantYear || i === 0)) { year = years[i]; S = all; break; }
    }
    // Charity returns lag the DfE ones, so the PTA figures come from the latest year that has them.
    var pta = obj(a.pta), ptaYear = null, P = {}, ptaBands = {};
    for (var k = years.length - 1; k >= 0; k--) {
      var row = obj(first(byYear[years[k]], ["all", "All"]));
      var bands = obj(first(row, ["pta_pp_by_band", "pta_band_medians", "fsm_band_pta_pp"]));
      if (firstNum(row, ["pta_pp_median", "pta_median_pp"]) != null || Object.keys(bands).length) { ptaYear = years[k]; P = row; ptaBands = bands; break; }
    }
    if (!Object.keys(ptaBands).length) ptaBands = obj(first(pta, ["bands", "by_band"]));
    if (!ptaYear && Object.keys(ptaBands).length) ptaYear = pta.year || year;
    var dsgYears = Object.keys(obj(a.dsg)).sort(), dsg = null;
    for (var j = dsgYears.length - 1; j >= 0; j--) {
      var d = obj(a.dsg[dsgYears[j]]);
      if (num(d.balance) != null || num(d.per_pupil) != null) { dsg = { year: dsgYears[j], balance: num(d.balance), pp: num(d.per_pupil) }; break; }
    }
    return {
      id: a.id || null, name: a.name || null, path: a.path || null, year: year,
      schools: num(S.schools), inDeficit: num(S.in_deficit), inDeficitPct: num(S.in_deficit_pct),
      ptaYear: ptaYear, ptaPP: firstNum(P, ["pta_pp_median", "pta_median_pp"]), ptaSchools: num(P.pta_schools), ptaSchoolsOf: num(P.schools),
      ptaBands: ptaBands,
      ptaRanking: arr(first(pta, ["ranking", "schools", "rank"])),
      dsg: dsg
    };
  }

  function rankIn(list, urn) {
    var rows = arr(list).map(function (r) {
      r = obj(r);
      return { urn: String(r.urn != null ? r.urn : r.id), v: firstNum(r, ["income_pp", "pp", "v"]) };
    }).filter(function (r) { return r.v != null; });
    rows.sort(function (a, b) { return b.v - a.v; });
    for (var i = 0; i < rows.length; i++) if (rows[i].urn === String(urn)) return { rank: i + 1, of: rows.length };
    return null;
  }

  // Per-pupil PTA figures use the published sx value or the same year's pupils; never another year's.
  function ptaView(s, sx, years) {
    var charities = arr(s.pta).filter(function (c) { return c && !c.review; });
    var main = obj(charities[0]);
    var rows = {}, sxp = obj(sx.pta);
    Object.keys(sxp).forEach(function (y) {
      var c = obj(sxp[y]), lines = obj(c.lines);
      if (num(c.income) == null) return;
      rows[y] = {
        y: y, income: num(c.income), spend: num(first(c, ["spend", "expenditure"])),
        givenPP: num(c.income_pp), givenSpendPP: firstNum(c, ["spend_pp", "expenditure_pp"]),
        number: c.charity_number || null, confidence: c.confidence || null, volunteers: num(c.volunteers),
        incomeLines: obj(first(c, ["income_lines"]) || lines.income), spendLines: obj(first(c, ["expenditure_lines", "spend_lines"]) || lines.spend),
        periodEnd: c.period_end || null
      };
    });
    if (!Object.keys(rows).length) {
      arr(main.history).forEach(function (h) {
        h = obj(h);
        var y = yearOfPeriodEnd(h.period_end);
        if (!y || num(h.income) == null) return;
        rows[y] = { y: y, income: num(h.income), spend: num(h.expenditure), periodEnd: h.period_end, volunteers: num(h.volunteers), incomeLines: {}, spendLines: {} };
      });
    }
    var breakdown = obj(main.breakdown);
    Object.keys(breakdown).forEach(function (y) {
      if (!rows[y]) return;
      var b = obj(breakdown[y]);
      if (!Object.keys(rows[y].spendLines || {}).length) rows[y].spendLines = obj(b.expenditure_lines);
      if (!Object.keys(rows[y].incomeLines || {}).length) rows[y].incomeLines = obj(b.income_lines);
    });
    var list = Object.keys(rows).sort().map(function (y) {
      var r = rows[y], yr = years.filter(function (x) { return x.y === y; })[0], pupils = yr && yr.pupils;
      r.pupils = pupils || null;
      r.pp = r.givenPP != null ? Math.round(r.givenPP) : perPupil(r.income, pupils);
      r.spendPP = r.givenSpendPP != null ? Math.round(r.givenSpendPP) : perPupil(r.spend, pupils);
      return r;
    });
    if (!list.length && num(main.latest_income) != null) {
      list = [{ y: "latest return", income: num(main.latest_income), spend: null, pp: null, incomeLines: {}, spendLines: {} }];
    }
    if (!list.length && !charities.length) return null;
    var withLines = list.filter(function (r) { return Object.keys(r.spendLines || {}).length; });
    var withVolunteers = list.filter(function (r) { return r.volunteers != null; });
    var lastV = withVolunteers[withVolunteers.length - 1];
    var number = main.charity_number || (list.length && list[list.length - 1].number) || null;
    return {
      name: titleCase(main.name || "") || "The parents' association", number: number ? String(number) : null,
      status: main.status || null, years: list, latest: list.length ? list[list.length - 1] : null,
      lines: withLines.length ? withLines[withLines.length - 1] : null,
      volunteers: lastV ? { n: lastV.volunteers, y: lastV.y } : (num(main.volunteers) != null ? { n: num(main.volunteers), y: null } : null)
    };
  }

  function adapt(s, sx, council, england, ctx) {
    s = obj(s); sx = obj(sx); ctx = Object.keys(obj(ctx)).length ? ctx : FALLBACK_CTX;
    var m = obj(sx.m), sYears = arr(s.years), seen = {}, labels = [];
    arr(sx.years).concat(sYears.map(function (r) { return obj(r).y; })).forEach(function (y) {
      if (y && !seen[y]) { seen[y] = true; labels.push(String(y)); }
    });
    labels.sort();
    var suspect = suspectYears(sx.flags), tags = obj(s.tags);
    var academy = !!(s.academy || tags.governance === "academy" || tags.governance === "free school");
    var source = sourceLabel(sx.source || s.source, academy);
    var years = labels.map(function (y) {
      var row = obj(sYears.filter(function (r) { return obj(r).y === y; })[0]);
      var out = { y: y, pupils: num(obj(sx.pupils)[y]), suspect: !!suspect[y], notes: suspect[y] || [], real: {} };
      if (out.pupils == null) out.pupils = num(row.pupils);
      Object.keys(METRICS).forEach(function (k) {
        var cell = {};
        for (var j = 0; j < METRICS[k][0].length; j++) {
          var found = obj(m[METRICS[k][0][j]])[y];
          if (found) { cell = obj(found); break; }
        }
        var v = num(cell.v);
        if (v == null) v = num(row[METRICS[k][1]]);
        out[k] = v;
        if (num(cell.rpp) != null || num(cell.r) != null) out.real[k] = { r: num(cell.r), rpp: num(cell.rpp) };
      });
      if (row.suspect) out.suspect = true;
      return out;
    });
    var usable = years.filter(function (r) { return !r.suspect && (r.income != null || r.pupils != null || r.reserve != null); });
    var latest = usable.length ? usable[usable.length - 1] : null;
    var st = typeof s.status === "object" && s.status ? s.status.status : s.status;
    var councilInfo = obj(s.council);
    var area = areaView(council, latest && latest.y);
    var path = s.path || ("/school/" + s.urn + "-" + slugify(s.name) + "/");
    var base = String(ctx.base_url || BASE_URL).replace(/\/$/, "");
    // s.similar (and s.pp) describe s.year, so the school's side is that year's row or nothing.
    // A marked year has no trustworthy figure to compare, so the comparison is left out.
    var compare = [], cmpYear = s.year || (latest && latest.y) || null;
    var cmpRow = years.filter(function (r) { return r.y === cmpYear; })[0] || null;
    if (cmpYear && !suspect[cmpYear] && !(cmpRow && cmpRow.suspect)) {
      [["spend", ["total_expenditure", "spend", "expenditure"], "Spending"], ["grant", ["grant_funding", "grant", "gov"], "Government funding"],
        ["income", ["total_income", "income"], "Income"]].forEach(function (p) {
        var theirs = firstNum(s.similar, p[1]);
        var mineV = cmpRow ? cmpRow[p[0]] : null, mine = cmpRow ? perPupil(mineV, cmpRow.pupils) : null;
        if (mine == null) mine = firstNum(s.pp, p[1]);
        if (mine != null && theirs != null) compare.push({ key: p[0], metric: p[1][0], label: p[2], mine: mine, v: mineV, theirs: Math.round(theirs), year: cmpYear });
      });
    }
    var rankBlock = obj(first(s, ["pta_rank"]) || first(sx, ["pta_rank"]));
    var councilRank = Object.keys(obj(rankBlock.council)).length ? obj(rankBlock.council) : (area ? rankIn(area.ptaRanking, s.urn) : null);
    var bandRank = Object.keys(obj(rankBlock.band)).length ? obj(rankBlock.band) : null;
    return {
      urn: String(s.urn || ""), name: s.name || "This school", path: path,
      url: base + path, wrappedUrl: base + path + "wrapped/",
      council: { code: councilInfo.code != null ? String(councilInfo.code) : null, name: councilInfo.name || (area && area.name) || null, path: councilInfo.path || (area && area.path) || null },
      status: STATUS[st] ? { key: st, label: s.label || STATUS[st].label, icon: STATUS[st].icon, colour: STATUS[st].colour, reason: s.reason || null, year: s.year || null } : null,
      academy: academy, trust: s.trust || null, governance: tags.governance || (academy ? "academy" : "council-run"),
      phase: s.phase || tags.phase || null, band: num(s.band), streak: num(s.streak),
      source: source, years: years, latest: latest, suspect: suspect,
      compare: compare, similarYear: s.year || null,
      pta: ptaView(s, sx, years),
      ptaRank: { council: councilRank && num(councilRank.rank) != null ? { rank: num(councilRank.rank), of: num(councilRank.of) } : null,
        band: bandRank && num(bandRank.rank) != null ? { rank: num(bandRank.rank), of: num(bandRank.of), band: num(bandRank.band) || num(s.band) } : null },
      area: area, england: areaView(england),
      ctx: ctx, realLabel: ctx.real_label || null, error: null
    };
  }

  // ======================================================================
  // buildCards(): the story, as plain data
  // ======================================================================
  function fig(key, label, v, pp, year, source) { return { key: key, label: label, v: v, pp: pp, year: year, source: source }; }

  function finish(c, kicker) {
    var seen = {}, src = [];
    c.figures.forEach(function (f) {
      var s = (f.year ? f.year + ", " : "") + f.source;
      if (f.source && !seen[s]) { seen[s] = true; src.push(s); }
    });
    c.kicker = kicker;
    c.source = src.join(" · ");
    var chartAlt = c.chart ? c.chart.label + ": " + c.chart.points.map(function (p) {
      return p.y + " " + (c.chart.format === "pupils" ? fmtPupils(p.v) : fmtExact(p.v)) + (p.suspect ? " (marked year)" : "");
    }).join("; ") + "." : "";
    c.alt = [c.title, c.status ? c.status.icon + " " + c.status.label : "", c.big ? c.big.text + (c.big.unit ? " " + c.big.unit : "") : ""]
      .concat(c.lines, [chartAlt, c.source ? "Source: " + c.source : ""])
      .filter(Boolean).join(". ").replace(/\.\./g, ".");
    return c;
  }

  function newCard(id, kind, title) {
    return { id: id, kind: kind, title: title, big: null, lines: [], figures: [], chart: null, alt: "", status: null, qr: null };
  }

  function suspectCaption(d) {
    var ys = Object.keys(d.suspect).filter(function (y) { return d.years.some(function (r) { return r.y === y; }); }).sort();
    if (!ys.length) return null;
    var notes = [];
    ys.forEach(function (y) { (d.suspect[y] || []).forEach(function (n) { if (notes.indexOf(n) === -1) notes.push(n); }); });
    return "Marked year" + (ys.length > 1 ? "s" : "") + ": " + ys.join(", ") + ". The published figures look unusual, so they are shown but not used as a headline" +
      (notes.length ? " (" + notes.join("; ") + ")" : "") + ".";
  }

  function whyLines(d) {
    var ctx = d.ctx, f = obj(obj(ctx.framings).why_schools_go_into_deficit);
    if (f.text) {
      var parts = sentences(f.text);
      return [(parts[0] + " " + parts[parts.length - 1]).trim() + ref(f.pages)];
    }
    var staff = withRef(obj(obj(ctx.staff).line));
    return [staff, ctx.why_fallback || FALLBACK_CTX.why_fallback].filter(Boolean);
  }

  function helpOf(d) {
    var key = d.status ? d.status.key : "healthy";
    return obj(obj(d.ctx.what_helps)[key]);
  }

  function schoolLine(d, id) {
    var l = arr(d.ctx.school_lines).filter(function (x) { return x && x.id === id; })[0];
    return l ? withRef(l) : null;
  }
  function councilLine(d, id) {
    var l = arr(d.ctx.council_lines).filter(function (x) { return x && x.id === id; })[0];
    return l ? withRef(l) : null;
  }

  function introCard(d, mode) {
    var c = newCard("intro", "intro", mode === "ptfa" ? d.name + ": PTFA Wrapped" : d.name + ": your year in money");
    var kind = d.governance === "council-run" ? "Council-run" : titleCase(d.governance.charAt(0).toUpperCase() + d.governance.slice(1));
    var where = d.council.name ? " in " + d.council.name : "";
    var phase = d.phase ? " " + String(d.phase).replace(/_/g, " ") : "";
    if (mode === "ptfa") {
      c.big = { v: null, text: d.pta && d.pta.latest ? d.pta.latest.y : "PTFA", fmt: "text" };
      c.lines.push(d.pta ? d.pta.name + (d.pta.number ? ", registered charity " + d.pta.number : "") : "Parents, teachers and friends");
      c.lines.push("What parents and friends raised for " + d.name + ", from the Charity Commission register.");
    } else {
      c.big = { v: null, text: d.latest ? d.latest.y : "Year in money", fmt: "text" };
      c.lines.push(kind + phase + " school" + where + ".");
      c.lines.push("A short story from published figures. Tap or press the right arrow to go on.");
    }
    return c;
  }

  // A card with no usable figure. With no usable year at all, figures that exist but are all marked
  // aren't "unpublished", so the card says what they are instead.
  function noHeadline(c, d, keys, unpublished) {
    var marked = d.latest ? [] : d.years.filter(function (r) { return r.suspect && keys.some(function (k) { return r[k] != null; }); });
    c.big = { v: null, text: marked.length ? (marked.length > 1 ? "Marked years" : "Marked year") : "Not published", fmt: "text" };
    c.lines.push(marked.length ? "The published figures look unusual, so they aren't used as a headline. Every figure is on the school's page." : unpublished);
    return c;
  }

  function pupilsCard(d) {
    var c = newCard("pupils", "stat", "Pupils"), L = d.latest;
    var withPupils = d.years.filter(function (r) { return r.pupils != null; });
    if (!L || L.pupils == null) return noHeadline(c, d, ["pupils"], "Pupil numbers for this school aren't published yet.");
    c.big = { v: L.pupils, text: fmtPupils(L.pupils), fmt: "pupils", unit: "pupils" };
    c.lines.push("pupils in " + L.y + ".");
    var firstRow = withPupils[0];
    if (firstRow && firstRow !== L && firstRow.y < L.y) {
      var change = L.pupils / firstRow.pupils - 1;
      c.lines.push(Math.abs(change) < 0.01 ? "About the same as " + fmtPupils(firstRow.pupils) + " in " + firstRow.y + "." :
        (change > 0 ? "Up " : "Down ") + pct(Math.abs(change)) + " from " + fmtPupils(firstRow.pupils) + " in " + firstRow.y + ".");
      if (change <= -0.05) {
        var rolls = obj(obj(d.ctx.framings).falling_rolls);
        c.lines.push((d.phase === "primary" || d.phase === "secondary" ? schoolLine(d, d.phase + "_rolls") : null) ||
          (rolls.text ? sentences(rolls.text)[0].trim() + ref(rolls.pages) : "Schools are mostly funded per pupil, so fewer pupils means less money while many costs stay the same."));
      }
    }
    c.figures.push(fig("pupils", "Pupils", L.pupils, null, L.y, d.source));
    c.chart = { label: "Pupils by year", format: "pupils", points: withPupils.map(function (r) { return { y: r.y, v: r.pupils, suspect: r.suspect }; }) };
    return c;
  }

  function fundingCard(d) {
    var L = d.latest, useGrant = L && L.grant != null;
    var c = newCard("funding", "stat", useGrant ? "Government funding per pupil" : "Income per pupil");
    var v = L ? (useGrant ? L.grant : L.income) : null, pp = L ? perPupil(v, L.pupils) : null;
    if (v == null || pp == null) return noHeadline(c, d, ["grant", "income"], "Figures for this year aren't published yet.");
    c.big = { v: pp, text: fmtExact(pp), fmt: "exact", unit: "per pupil" };
    c.lines.push((useGrant ? "Government funding" : "Income") + " per pupil in " + L.y + ".");
    c.lines.push(fmtMoney(v) + " in total for " + fmtPupils(L.pupils) + " pupils.");
    c.figures.push(fig(useGrant ? "grant_funding" : "total_income", useGrant ? "Government funding" : "Income", v, pp, L.y, d.source));
    if (useGrant && L.income) {
      c.lines.push("Government grants were " + pct(L.grant / L.income) + " of all income (" + fmtMoney(L.income) + ").");
      c.figures.push(fig("total_income", "Total income", L.income, perPupil(L.income, L.pupils), L.y, d.source));
    }
    var key = useGrant ? "grant" : "income", firstReal = d.years.filter(function (r) { return !r.suspect && r.real[key] && r.real[key].rpp != null; })[0];
    var nowReal = L.real[key];
    if (d.realLabel && firstReal && nowReal && nowReal.rpp != null && firstReal.y < L.y) {
      var ch = nowReal.rpp / firstReal.real[key].rpp - 1;
      c.lines.push("Shown " + d.realLabel + ": " + fmtExact(firstReal.real[key].rpp) + " per pupil in " + firstReal.y + " and " + fmtExact(nowReal.rpp) +
        " in " + L.y + ", " + (Math.abs(ch) < 0.01 ? "about the same" : (ch > 0 ? "up " : "down ") + pct(Math.abs(ch))) + ".");
    }
    return c;
  }

  function staffCard(d) {
    var c = newCard("staff", "split", "Where each £1 goes"), L = d.latest;
    var staffLine = withRef(obj(obj(d.ctx.staff).line));
    if (!L || L.staff == null || !L.spend) {
      noHeadline(c, d, ["staff"], "A breakdown of this school's spending isn't published yet.");
      c.big = { v: null, text: "Mostly people", fmt: "text" };
      if (staffLine) c.lines.push(staffLine);
      return c;
    }
    var share = L.staff / L.spend;
    c.big = { v: share, text: pence(share), fmt: "pence", unit: "of every £1 on staff" };
    c.lines.push("Of every £1 spent in " + L.y + ", " + pence(share) + " went on staff: " + fmtMoney(L.staff) + ", " + fmtExact(perPupil(L.staff, L.pupils)) + " per pupil.");
    if (staffLine) c.lines.push(staffLine);
    var parts = [["premises", "buildings"], ["energy", "energy"], ["supplies", "learning resources"], ["services", "bought-in services"]]
      .filter(function (p) { return L[p[0]] != null && L[p[0]] > 0; });
    if (parts.length) c.lines.push("Also: " + parts.map(function (p) { return p[1] + " " + pence(L[p[0]] / L.spend); }).join(", ") + ".");
    else c.lines.push("The rest pays for buildings, energy, learning resources and services.");
    c.split = [{ label: "Staff", share: share }].concat(parts.map(function (p) { return { label: p[1], share: L[p[0]] / L.spend }; }));
    c.figures.push(fig("staff_total", "Staff costs", L.staff, perPupil(L.staff, L.pupils), L.y, d.source));
    c.figures.push(fig("total_expenditure", "Spending", L.spend, perPupil(L.spend, L.pupils), L.y, d.source));
    return c;
  }

  function reserveCard(d) {
    var c = newCard("reserve", "chart", "The reserve story"), L = d.latest;
    var pts = d.years.filter(function (r) { return r.reserve != null; });
    if (!pts.length) {
      c.big = { v: null, text: "Not published", fmt: "text" };
      c.lines.push("Reserve figures for this school aren't published yet.");
      return c;
    }
    var pressed = false;
    if (L && L.reserve != null) {
      var pp = perPupil(L.reserve, L.pupils);
      c.big = { v: L.reserve, text: fmtMoney(L.reserve), fmt: "money", unit: "reserve" };
      c.status = d.status;
      c.lines.push("Reserve at the end of " + L.y + ": " + fmtExact(L.reserve) + (pp != null ? ", or " + fmtExact(pp) + " per pupil" : "") + ".");
      c.figures.push(fig("revenue_reserve", "Reserve", L.reserve, pp, L.y, d.source));
      var clean = pts.filter(function (r) { return !r.suspect && r !== L; });
      var peak = clean.reduce(function (b, r) { return !b || r.reserve > b.reserve ? r : b; }, null);
      if (peak && peak.reserve !== L.reserve) {
        var ppk = perPupil(peak.reserve, peak.pupils);
        c.lines.push("It was " + fmtExact(peak.reserve) + (ppk != null ? " (" + fmtExact(ppk) + " per pupil)" : "") + " in " + peak.y + ".");
        c.figures.push(fig("revenue_reserve", "Reserve", peak.reserve, ppk, peak.y, d.source));
      }
      pressed = L.reserve < 0 || (d.status && (d.status.key === "in_deficit" || d.status.key === "heading_for_deficit"));
    } else {
      // Published reserves with no year usable as a headline: the chart still shows them, marked.
      var span = pts[0].y === pts[pts.length - 1].y ? pts[0].y : pts[0].y + " to " + pts[pts.length - 1].y;
      c.big = { v: null, text: span, fmt: "text", unit: "reserve figures" };
      c.lines.push(L ? "The reserve for " + L.y + " isn't published yet, so the chart shows the years that are." : "The chart shows the reserve at the end of each year.");
    }
    if (pressed) {
      c.lines = c.lines.concat(whyLines(d));
      c.lines.push(helpOf(d).text || d.ctx.help_fallback || FALLBACK_CTX.help_fallback);
    } else {
      c.lines.push("A reserve is the savings a school carries from year to year, for surprises and plans.");
    }
    var cap = suspectCaption(d);
    if (cap) c.lines.push(cap);
    c.chart = { label: "Reserve at the end of each year", format: "money", points: pts.map(function (r) { return { y: r.y, v: r.reserve, suspect: r.suspect }; }) };
    return c;
  }

  function compareCard(d) {
    if (!d.compare.length) return null;
    var c = newCard("similar", "compare", "Compared with similar schools"), main = d.compare[0];
    function word(a, b) {
      var r = a / b - 1;
      if (Math.abs(r) < 0.03) return "about the same as";
      return (Math.abs(r) < 0.1 ? "a little " : "") + (r > 0 ? "more than" : "less than");
    }
    c.big = { v: main.mine, text: fmtExact(main.mine), fmt: "exact", unit: main.label.toLowerCase() + " per pupil" };
    d.compare.forEach(function (p) {
      c.lines.push(p.label + ": " + fmtExact(p.mine) + " per pupil, " + word(p.mine, p.theirs) + " the middle of similar schools (" + fmtExact(p.theirs) + ").");
      c.figures.push(fig(p.metric, p.label, p.v, p.mine, p.year, d.source));
      c.figures.push(fig("similar_" + p.key, "Similar schools' middle value", null, p.theirs, p.year, "DfE similar-schools comparison"));
    });
    c.lines.push("Spending more can mean extra support or higher costs; spending less can mean leaner running. Both are worth asking about.");
    var nat = schoolLine(d, d.phase === "secondary" ? "per_pupil_secondary" : (d.phase === "primary" ? "per_pupil_primary" : ""));
    if (nat) c.lines.push(nat);
    return c;
  }

  function councilCard(d) {
    var A = d.area, name = d.council.name || (A && A.name) || "the council";
    var c = newCard("council", "area", "The " + name + " picture");
    if (!A) {
      c.big = { v: null, text: name, fmt: "text" };
      c.lines.push("The council's figures aren't published yet.");
      return c;
    }
    if (A.inDeficit != null && A.schools != null) {
      c.big = { v: A.inDeficit, text: A.inDeficit + " of " + A.schools, fmt: "text", unit: "schools in deficit" };
      c.lines.push(A.inDeficit + " of " + A.schools + " schools in " + name + (A.inDeficitPct != null ? " (" + Math.round(A.inDeficitPct) + "%)" : "") +
        " ended " + A.year + " with a deficit (DfE returns).");
      c.lines.push(schoolLine(d, "costs_outpaced_funding") || whyLines(d)[0]);
    } else {
      c.big = { v: null, text: name, fmt: "text" };
      c.lines.push(name + " has too few schools in this group to show a fair figure.");
    }
    if (A.dsg) {
      c.lines.push("The council's high needs (Dedicated Schools Grant) balance at the end of " + A.dsg.year + ": " +
        (A.dsg.balance != null ? fmtMoney(A.dsg.balance) : "not published") + (A.dsg.pp != null ? ", " + fmtExact(A.dsg.pp) + " per pupil" : "") + ".");
      c.figures.push(fig("dsg_balance", "High needs balance", A.dsg.balance, A.dsg.pp, A.dsg.year, "DfE section 251 outturn"));
    }
    var override = councilLine(d, "high_needs_deficits");
    if (override) c.lines.push(override);
    c.lines.push("What helps: councils and schools planning special needs support together, and families knowing who to ask.");
    return c;
  }

  function ptaRaisedCard(d, id, title) {
    var P = d.pta, ctxp = obj(d.ctx.pta);
    var c = newCard(id, P && P.latest ? "chart" : "notice", P && P.latest ? title : "Parents' association");
    if (P && !P.latest) {
      c.big = { v: null, text: "Registered", fmt: "text" };
      c.lines.push(P.name + (P.number ? " (registered charity " + P.number + ")" : "") + " is on the Charity Commission register, but its income figures aren't published yet.");
      c.lines.push(ctxp.overlap_note || FALLBACK_CTX.pta.overlap_note);
      return c;
    }
    if (!P) {
      c.big = { v: null, text: "Not found", fmt: "text" };
      c.lines.push((ctxp.not_found || FALLBACK_CTX.pta.not_found) + " for " + d.name + ".");
      c.lines.push(ctxp.register_note || FALLBACK_CTX.pta.register_note);
      c.lines.push("Ask the school office how parents and friends can help.");
      return c;
    }
    var L = P.latest, src = ctxp.source || FALLBACK_CTX.pta.source;
    c.big = L.pp != null ? { v: L.pp, text: fmtExact(L.pp), fmt: "exact", unit: "per pupil" } : { v: L.income, text: fmtExact(L.income), fmt: "exact", unit: "raised" };
    c.lines.push(fmtExact(L.income) + " raised in " + L.y + (L.periodEnd ? " (year to " + monthYear(L.periodEnd) + ")" : "") +
      (L.pp != null ? ", " + fmtExact(L.pp) + " per pupil" : "") + (L.spend != null ? "; " + fmtExact(L.spend) + " spent" : "") + ".");
    var firstRow = P.years[0];
    if (firstRow && firstRow !== L && firstRow.income) {
      var ch = L.income / firstRow.income - 1;
      c.lines.push(Math.abs(ch) < 0.05 ? "About the same as " + fmtExact(firstRow.income) + " in " + firstRow.y + "." :
        (ch > 0 ? "Up from " : "Down from ") + fmtExact(firstRow.income) + " in " + firstRow.y + ".");
    }
    if (d.ptaRank.council && d.ptaRank.council.of) {
      c.lines.push("Number " + d.ptaRank.council.rank + " of " + d.ptaRank.council.of + " registered parents' associations in " + (d.council.name || "the council") + " for money raised per pupil.");
    }
    c.lines.push(ctxp.overlap_note || FALLBACK_CTX.pta.overlap_note);
    c.figures.push(fig("pta_income", "Raised", L.income, L.pp, L.y, src));
    if (L.spend != null) c.figures.push(fig("pta_spend", "Spent", L.spend, L.spendPP, L.y, src));
    c.chart = { label: "Money raised each year", format: "money", points: P.years.filter(function (r) { return r.income != null; }).map(function (r) { return { y: r.y, v: r.income, suspect: false }; }) };
    return c;
  }

  function helpsCard(d) {
    var c = newCard("helps", "list", "What helps"), h = helpOf(d), f = obj(h.framing);
    c.status = d.status;
    c.big = { v: null, text: "Good questions", fmt: "text" };
    c.lines.push(h.text || (d.status && (d.status.key === "in_deficit" || d.status.key === "heading_for_deficit") ? FALLBACK_CTX.help_fallback :
      "What helps: keeping an eye on the trend, and asking how the money supports pupils."));
    if (f.title && f.text) {
      var parts = sentences(f.text);
      c.lines.push(f.title + ": " + parts[parts.length - 1].trim() + ref(f.pages));
    }
    var reserve = d.latest && d.latest.reserve != null ? fmtMoney(d.latest.reserve) : "its";
    var vars = { name: d.name, overseer: d.academy ? (d.trust || "the trust") : "the council", reserve: reserve, years: d.streak != null ? String(d.streak) : "several" };
    arr(h.questions).concat(arr(d.ctx.any_questions)).slice(0, 2).forEach(function (q) {
      if (q && q.text) c.lines.push("Ask: " + fill(q.text, vars) + (q.page != null ? ref([q.page]) : ""));
    });
    return c;
  }

  function outroCard(d, mode) {
    var c = newCard("outro", "outro", mode === "ptfa" ? "Thank you for reading" : "See every figure");
    var short = d.url.replace(/^https?:\/\//, "");
    c.big = { v: null, text: short, fmt: "url" };
    c.lines.push("Scan the code or visit the school's page for every figure, with its year and source.");
    c.lines.push("Figures: " + d.source + "s" + (d.pta && d.pta.latest ? " and the Charity Commission register" : "") + ".");
    var cite = obj(d.ctx.ifs).cite;
    if (cite) c.lines.push("Context: " + cite + ".");
    c.qr = { url: d.url };
    c.link = d.url;
    return c;
  }

  function ptaRankCard(d) {
    var R = d.ptaRank;
    if (!d.pta || !d.pta.latest || (!R.council && !R.band)) return null;
    var c = newCard("pta-rank", "stat", "How it compares");
    var main = R.council || R.band;
    c.big = { v: main.rank, text: "Number " + main.rank, fmt: "text", unit: "of " + main.of };
    if (R.council) c.lines.push("Number " + R.council.rank + " of " + R.council.of + " registered parents' associations in " + (d.council.name || "the council") + " for money raised per pupil.");
    if (R.band) c.lines.push("Number " + R.band.rank + " of " + R.band.of + " among schools with a similar intake (band " + (R.band.band || "?") + " of 5, where 1 is the most affluent).");
    c.lines.push("Rankings use money raised per pupil from the Charity Commission register.");
    c.figures.push(fig("pta_income", "Raised", d.pta.latest.income, d.pta.latest.pp, d.pta.latest.y, "Charity Commission register"));
    return c;
  }

  function ptaGapCard(d) {
    var E = d.england;
    if (!E || (E.ptaPP == null && !Object.keys(E.ptaBands).length)) return null;
    var c = newCard("pta-gap", "stat", "Across England");
    var bands = E.ptaBands, b1 = num(first(bands, ["1", "band1", "b1"])), b5 = num(first(bands, ["5", "band5", "b5"]));
    if (b1 != null && b5 != null) {
      c.big = { v: null, text: fmtExact(b1) + " vs " + fmtExact(b5), fmt: "text", unit: "per pupil" };
      c.lines.push("Parents' associations at schools with the most affluent intakes raised a middle value of " + fmtExact(b1) +
        " per pupil in " + E.ptaYear + "; at schools with the least affluent intakes, " + fmtExact(b5) + ".");
      c.figures.push(fig("pta_band1", "Most affluent intakes", null, b1, E.ptaYear, "Charity Commission register"));
      c.figures.push(fig("pta_band5", "Least affluent intakes", null, b5, E.ptaYear, "Charity Commission register"));
    } else {
      c.big = { v: E.ptaPP, text: fmtExact(E.ptaPP), fmt: "exact", unit: "per pupil" };
    }
    if (E.ptaPP != null) {
      c.lines.push("The middle registered parents' association in England raised " + fmtExact(E.ptaPP) + " per pupil in " + E.ptaYear + ".");
      c.figures.push(fig("pta_pp_median", "England middle value", null, E.ptaPP, E.ptaYear, "Charity Commission register"));
    }
    if (E.ptaSchools != null && E.ptaSchoolsOf) c.lines.push(E.ptaSchools + " of " + E.ptaSchoolsOf + " schools have a registered parents' association we could match.");
    c.lines.push("Parent fundraising is not in the IFS report on school spending, so these figures come from the charity register alone.");
    return c;
  }

  function ptaLinesCard(d) {
    var P = d.pta;
    if (!P || !P.lines) return null;
    var row = P.lines, c = newCard("pta-spend", "list", "What the money paid for");
    var src = "parents' association accounts filed with the Charity Commission";
    var spend = Object.keys(row.spendLines).map(function (k) { return [k, num(row.spendLines[k])]; }).filter(function (x) { return x[1] != null && x[1] > 0; })
      .sort(function (a, b) { return b[1] - a[1]; });
    var income = Object.keys(row.incomeLines || {}).map(function (k) { return [k, num(row.incomeLines[k])]; }).filter(function (x) { return x[1] != null && x[1] > 0; })
      .sort(function (a, b) { return b[1] - a[1]; });
    if (!spend.length) return null;
    c.big = { v: null, text: row.y, fmt: "text" };
    spend.slice(0, 5).forEach(function (x) {
      c.lines.push(x[0] + ": " + fmtExact(x[1]) + ".");
      c.figures.push(fig("pta_line", x[0], x[1], perPupil(x[1], row.pupils), row.y, src));
    });
    if (income.length) c.lines.push("Raised from: " + income.slice(0, 4).map(function (x) { return x[0] + " " + fmtExact(x[1]); }).join(", ") + ".");
    return c;
  }

  function thanksCard(d) {
    var c = newCard("thanks", "notice", "Thank you");
    c.big = { v: null, text: "Thank you", fmt: "text" };
    c.lines.push("To everyone who ran a stall, baked, counted coins, gave or simply turned up: thank you.");
    var V = d.pta && d.pta.volunteers;
    if (V && V.n) {
      c.lines.push("About " + V.n + " volunteers helped" + (V.y ? " in " + V.y : "") + ".");
      c.figures.push({ key: "pta_volunteers", label: "Volunteers", v: null, pp: null, year: V.y, source: "Charity Commission annual return" });
    }
    c.lines.push("Every pound raised is on top of what the school receives from the government.");
    return c;
  }

  function registerCard(d) {
    var c = newCard("register", "notice", "Starting or registering one"), ctxp = obj(d.ctx.pta);
    c.big = { v: null, text: "£5,000", fmt: "text", unit: "a year" };
    c.lines.push("A parents' association must register with the Charity Commission once its income goes over £5,000 a year.");
    c.lines.push("Smaller groups can still do a lot: organise events, welcome new families and support school trips.");
    c.lines.push("How to register: " + (ctxp.register_url || FALLBACK_CTX.pta.register_url));
    return c;
  }

  function errorModel(d, mode) {
    var c = newCard("notice", "notice", d && d.name ? d.name : "School Wrapped");
    c.big = { v: null, text: "Not ready yet", fmt: "text" };
    c.lines.push((d && d.error) || "Figures for this school aren't published yet.");
    c.lines.push("Every published figure is on the school's own page.");
    var path = (d && d.path) || "/search/";
    c.link = path;
    return { mode: mode, title: "School Wrapped", cards: [finish(c, mode === "ptfa" ? "PTFA Wrapped" : "School Wrapped")],
      share: { title: "School Wrapped", text: "A school's year in money, from published figures.", url: BASE_URL + path } };
  }

  function buildCards(data, mode) {
    mode = mode === "ptfa" ? "ptfa" : "school";
    if (!data || data.error) return errorModel(data, mode);
    var d = data, kicker = mode === "ptfa" ? "PTFA Wrapped" : "School Wrapped", cards;
    if (mode === "ptfa") {
      if (d.pta && d.pta.latest) {
        cards = [introCard(d, mode), ptaRaisedCard(d, "pta-money", "Raised over the years"), ptaRankCard(d), ptaGapCard(d), ptaLinesCard(d), thanksCard(d), outroCard(d, mode)];
      } else {
        cards = [introCard(d, mode), ptaRaisedCard(d, "pta-money", ""), registerCard(d), ptaGapCard(d), thanksCard(d), outroCard(d, mode)];
      }
    } else {
      cards = [introCard(d, mode), pupilsCard(d), fundingCard(d), staffCard(d), reserveCard(d), compareCard(d), councilCard(d),
        ptaRaisedCard(d, "pta", "What the PTFA raised"), helpsCard(d), outroCard(d, mode)];
    }
    cards = cards.filter(Boolean).map(function (c) { return finish(c, kicker); });
    var url = d.wrappedUrl + (mode === "ptfa" ? "?mode=ptfa" : "");
    var L = d.latest, text;
    if (mode === "ptfa") {
      text = d.pta && d.pta.latest ? "What " + d.name + "'s parents' association raised: " + fmtExact(d.pta.latest.income) + " in " + d.pta.latest.y +
        " (Charity Commission register). Thank you to every volunteer." : "Parents and friends at " + d.name + ": a story about getting involved.";
    } else {
      var g = L && L.grant != null ? perPupil(L.grant, L.pupils) : null;
      text = d.name + "'s year in money" + (L && L.pupils != null ? ": " + fmtPupils(L.pupils) + " pupils" + (g != null ? " and " + fmtExact(g) + " government funding per pupil" : "") +
        " in " + L.y + " (DfE)" : "") + ". Every figure is from published data.";
    }
    return { mode: mode, title: d.name + ": " + kicker, cards: cards, share: { title: d.name + ": " + kicker, text: text, url: url } };
  }

  // ======================================================================
  // Video frames, drawing and encoding
  // ======================================================================
  // One entry per frame: t runs 0 to 1 within a card; the last 0.4 s of each card (bar the last) fades to the next.
  function planFrames(cardCount, fps, seconds) {
    fps = fps || 30; seconds = seconds || 3;
    var per = Math.max(1, Math.round(fps * seconds)), fadeFrames = Math.max(1, Math.round(0.4 * fps)), out = [];
    for (var c = 0; c < cardCount; c++) {
      for (var i = 0; i < per; i++) {
        var inFade = i >= per - fadeFrames;
        out.push({ frame: c * per + i, card: c, t: per > 1 ? i / (per - 1) : 1, key: i === 0, transition: inFade,
          fade: inFade && c < cardCount - 1 ? (i - (per - fadeFrames) + 1) / fadeFrames : 0 });
      }
    }
    return out;
  }

  function ease(x) { x = clamp(x, 0, 1); return 1 - Math.pow(1 - x, 3); }
  function col(pal, key, fallback) { var v = pal && pal[key]; return v ? String(v).trim() : fallback; }

  function wrapText(g, text, maxWidth) {
    var words = String(text == null ? "" : text).split(/\s+/).filter(Boolean), lines = [], cur = "";
    function push(word) {
      if (g.measureText(word).width <= maxWidth) return word;
      var piece = "";
      for (var i = 0; i < word.length; i++) {
        if (g.measureText(piece + word[i]).width > maxWidth && piece) { lines.push(piece); piece = ""; }
        piece += word[i];
      }
      return piece;
    }
    words.forEach(function (w) {
      var next = cur ? cur + " " + w : w;
      if (g.measureText(next).width <= maxWidth) { cur = next; return; }
      if (cur) lines.push(cur);
      cur = push(w);
    });
    if (cur) lines.push(cur);
    return lines;
  }

  // A URL has no spaces: break after "/", "-" or "." (or mid-piece when one piece is too wide),
  // never adding or dropping a character, so the lines read back as the whole address.
  function wrapUrl(g, text, maxWidth) {
    var pieces = String(text == null ? "" : text).match(/[^\/.\-]+[\/.\-]*|[\/.\-]+/g) || [], lines = [], cur = "";
    pieces.forEach(function (p) {
      if (g.measureText(cur + p).width <= maxWidth) { cur += p; return; }
      if (cur) lines.push(cur);
      cur = "";
      for (var i = 0; i < p.length; i++) {
        if (cur && g.measureText(cur + p[i]).width > maxWidth) { lines.push(cur); cur = ""; }
        cur += p[i];
      }
    });
    if (cur) lines.push(cur);
    return lines;
  }

  function paragraph(g, text, x, y, maxWidth, size, colour, weight, maxLines, lineHeight) {
    g.font = (weight || "400") + " " + Math.round(size) + "px " + FONT;
    g.fillStyle = colour;
    g.textAlign = "left";
    g.textBaseline = "top";
    var lines = wrapText(g, text, maxWidth);
    if (maxLines && lines.length > maxLines) {
      lines = lines.slice(0, maxLines);
      lines[maxLines - 1] = lines[maxLines - 1].replace(/\s*\S*$/, "") + "…";
    }
    var lh = size * (lineHeight || 1.3);
    lines.forEach(function (line, i) { g.fillText(line, x, y + i * lh); });
    return y + lines.length * lh;
  }
  function bigText(card, k) {
    var b = card.big;
    if (!b) return "";
    if (b.v == null || k >= 1 || b.fmt === "text" || b.fmt === "url") return b.text;
    var v = b.v * k;
    if (b.fmt === "exact") return fmtExact(v);
    if (b.fmt === "money") return fmtMoney(v);
    if (b.fmt === "pupils") return fmtPupils(Math.round(v * 10) / 10);
    if (b.fmt === "pence") return pence(v);
    return b.text;
  }

  function linesHeight(g, lines, size, maxWidth, s) {
    g.font = "400 " + Math.round(size) + "px " + FONT;
    return lines.reduce(function (sum, l) { return sum + wrapText(g, l, maxWidth).length * size * 1.3 + 22 * s; }, 0);
  }

  function fitFont(g, text, maxWidth, size, weight) {
    for (var s = size; s > 28; s -= 6) {
      g.font = weight + " " + Math.round(s) + "px " + FONT;
      if (g.measureText(text).width <= maxWidth) return s;
    }
    return 28;
  }

  function drawChart(g, chart, x, y, w, h, reveal, pal, scale) {
    var pts = chart.points;
    if (!pts.length) return;
    var vals = pts.map(function (p) { return p.v; }), lo = Math.min.apply(null, vals.concat([0])), hi = Math.max.apply(null, vals.concat([0]));
    if (hi === lo) hi = lo + 1;
    var padTop = 50 * scale, padBottom = (lo < 0 ? 100 : 60) * scale, ih = h - padTop - padBottom;
    function px(i) { return pts.length === 1 ? x + w / 2 : x + (i / (pts.length - 1)) * w; }
    function py(v) { return y + padTop + (1 - (v - lo) / (hi - lo)) * ih; }
    function label(v) { return chart.format === "pupils" ? fmtPupils(v) : fmtMoney(v); }
    // zero line
    g.strokeStyle = col(pal, "line-strong", "#888");
    g.lineWidth = 2 * scale;
    g.beginPath(); g.moveTo(x, py(0)); g.lineTo(x + w, py(0)); g.stroke();
    // line, revealed left to right
    var upto = reveal * (pts.length - 1);
    g.strokeStyle = col(pal, "accent", "#000");
    g.lineWidth = 8 * scale;
    g.lineJoin = "round"; g.lineCap = "round";
    g.beginPath();
    g.moveTo(px(0), py(pts[0].v));
    for (var i = 1; i < pts.length && i - 1 < upto; i++) {
      var f = Math.min(1, upto - (i - 1));
      g.lineTo(px(i - 1) + (px(i) - px(i - 1)) * f, py(pts[i - 1].v) + (py(pts[i].v) - py(pts[i - 1].v)) * f);
    }
    g.stroke();
    var step = pts.length > 8 ? 2 : 1;
    pts.forEach(function (p, i) {
      if (i > upto + 0.001) return;
      g.beginPath();
      g.arc(px(i), py(p.v), (p.suspect ? 14 : 11) * scale, 0, Math.PI * 2);
      if (p.suspect) {
        g.fillStyle = col(pal, "paper", "#fff"); g.fill();
        g.lineWidth = 5 * scale; g.strokeStyle = col(pal, "serious", "#000"); g.stroke();
      } else {
        g.fillStyle = p.v < 0 ? col(pal, "critical", "#000") : col(pal, "accent", "#000"); g.fill();
      }
      g.font = "400 " + Math.round(24 * scale) + "px " + FONT;
      g.fillStyle = col(pal, "ink-2", "#444");
      g.textAlign = "center"; g.textBaseline = "top";
      if (i % step === 0 || i === pts.length - 1) g.fillText(p.y + (p.suspect ? "*" : ""), px(i), y + h - 34 * scale);
      if (i === 0 || i === pts.length - 1 || p.suspect) {
        g.font = "700 " + Math.round(28 * scale) + "px " + FONT;
        g.fillStyle = col(pal, "ink", "#000");
        var below = p.v < 0; // labels for negative values sit under the point, clear of the line coming down to it
        g.textBaseline = below ? "top" : "bottom";
        g.textAlign = i === 0 ? "left" : (i === pts.length - 1 ? "right" : "center");
        g.fillText(label(p.v), i === 0 ? px(i) - 10 * scale : (i === pts.length - 1 ? px(i) + 10 * scale : px(i)), py(p.v) + (below ? 20 : -20) * scale);
      }
    });
    g.textAlign = "left";
  }

  function drawQr(g, qr, x, y, size) {
    var n = qr.size, quiet = 4, cell = size / (n + quiet * 2);
    g.fillStyle = "#ffffff"; // a QR code needs a light ground and dark modules in either colour scheme
    g.fillRect(x, y, size, size);
    g.fillStyle = "#000000";
    for (var r = 0; r < n; r++) for (var c = 0; c < n; c++) {
      if (qr.dark(r, c)) g.fillRect(x + (c + quiet) * cell, y + (r + quiet) * cell, Math.ceil(cell), Math.ceil(cell));
    }
  }

  // Draws one card at progress t (0..1) on a width x height canvas (default 1080x1920). opts: {index, count,
  // fade, reducedMotion, qr: {size, dark(r, c)}}. palette: {paper, ink, accent, ...} read from the CSS tokens.
  function drawCard(g, card, t, pal, opts) {
    opts = opts || {}; pal = pal || {};
    var w = opts.width || W, h = opts.height || H, s = w / W;
    if (opts.reducedMotion) t = 1;
    t = clamp(t == null ? 1 : t, 0, 1);
    var k = ease(t / 0.55), M = 96 * s, inner = w - 2 * M, footY = h - 150 * s;
    g.save();
    g.globalAlpha = 1;
    g.fillStyle = col(pal, "paper", "#fff"); g.fillRect(0, 0, w, h);
    g.fillStyle = col(pal, "accent", "#000"); g.fillRect(0, 0, w, 18 * s);
    g.font = "700 " + Math.round(34 * s) + "px " + FONT;
    g.fillStyle = col(pal, "accent", "#000"); g.textAlign = "left"; g.textBaseline = "top";
    g.fillText(card.kicker || "School Wrapped", M, 110 * s);
    if (opts.count) {
      g.textAlign = "right"; g.fillStyle = col(pal, "ink-2", "#444");
      g.fillText((opts.index || 0) + 1 + " / " + opts.count, w - M, 110 * s);
      g.textAlign = "left";
    }
    var y = paragraph(g, card.title, M, (card.kind === "intro" ? 480 : 200) * s, inner, 68 * s, col(pal, "ink", "#000"), "700", 3, 1.15) + 30 * s;
    if (card.status) {
      var label = card.status.icon + " " + card.status.label;
      g.font = "700 " + Math.round(36 * s) + "px " + FONT;
      var bw = g.measureText(label).width + 48 * s, bh = 64 * s;
      g.lineWidth = 4 * s; g.strokeStyle = col(pal, card.status.colour, "#000"); g.fillStyle = col(pal, "card", "#fff");
      g.beginPath();
      if (g.roundRect) g.roundRect(M, y, bw, bh, bh / 2); else g.rect(M, y, bw, bh);
      g.fill(); g.stroke();
      g.fillStyle = col(pal, "ink", "#000"); g.textBaseline = "middle";
      g.fillText(label, M + 24 * s, y + bh / 2);
      g.textBaseline = "top";
      y += bh + 30 * s;
    }
    if (card.big) {
      var text = bigText(card, k), isUrl = card.big.fmt === "url";
      if (isUrl) {
        // The address is the way in when the QR can't load, so it shrinks to fit and is never cut.
        var urlSize, urlLines, urlSizes = [48, 44, 40, 36];
        for (var ui = 0; ui < urlSizes.length; ui++) {
          urlSize = urlSizes[ui] * s;
          g.font = "700 " + Math.round(urlSize) + "px " + FONT;
          urlLines = wrapUrl(g, text, inner);
          if (urlLines.length <= 3) break;
        }
        g.fillStyle = col(pal, "accent", "#000"); g.textAlign = "left"; g.textBaseline = "top";
        urlLines.forEach(function (line, i) { g.fillText(line, M, y + i * urlSize * 1.2); });
        y += urlLines.length * urlSize * 1.2 + 20 * s;
      } else {
        var size = fitFont(g, card.big.text, inner, 150 * s, "800");
        g.font = "800 " + Math.round(size) + "px " + FONT;
        g.fillStyle = col(pal, "accent", "#000"); g.textBaseline = "top";
        g.fillText(text, M, y);
        y += size * 1.1;
        if (card.big.unit) y = paragraph(g, card.big.unit, M, y, inner, 40 * s, col(pal, "ink-2", "#444"), "600", 2) + 10 * s;
      }
      y += 20 * s;
    }
    var qrSize = card.qr && opts.qr ? 380 * s : 0, limit = footY - (qrSize ? qrSize + 40 * s : 0) - 20 * s;
    if (card.chart && card.chart.points.length) {
      // The chart gives up height (down to 340 px) before the text has to shrink below 31 px.
      var ch = clamp(limit - y - 30 * s - linesHeight(g, card.lines, 31 * s, inner, s), 340 * s, 520 * s);
      drawChart(g, card.chart, M + 20 * s, y, inner - 40 * s, ch, opts.reducedMotion ? 1 : ease(t / 0.7), pal, s);
      y += ch + 30 * s;
    } else if (card.split) {
      var x0 = M;
      card.split.forEach(function (p, i) {
        var bwid = inner * p.share * k;
        g.fillStyle = col(pal, i === 0 ? "accent" : ["c2", "c3", "c4", "band"][(i - 1) % 4], "#888");
        g.fillRect(x0, y, Math.max(0, bwid), 60 * s);
        x0 += inner * p.share;
      });
      y += 100 * s;
    }
    var size2 = 28 * s, sizes = [40, 37, 34, 31, 28];
    for (var si = 0; si < sizes.length; si++) {
      if (linesHeight(g, card.lines, sizes[si] * s, inner, s) <= limit - y) { size2 = sizes[si] * s; break; }
    }
    for (var i = 0; i < card.lines.length && y < limit; i++) {
      var alpha = opts.reducedMotion ? 1 : clamp((t - 0.1 - i * 0.06) / 0.2, 0, 1);
      g.globalAlpha = alpha;
      var maxL = Math.max(1, Math.floor((limit - y) / (size2 * 1.3)));
      y = paragraph(g, card.lines[i], M, y, inner, size2, col(pal, "ink", "#000"), "400", maxL) + 22 * s;
    }
    g.globalAlpha = 1;
    if (qrSize) drawQr(g, opts.qr, M, footY - qrSize - 30 * s, qrSize);
    if (card.source) paragraph(g, card.source, M, footY, inner, 28 * s, col(pal, "ink-3", "#666"), "400", 3);
    if (opts.fade > 0) {
      g.globalAlpha = clamp(opts.fade, 0, 1);
      g.fillStyle = col(pal, "paper", "#fff"); g.fillRect(0, 0, w, h);
      g.globalAlpha = 1;
    }
    g.restore();
  }

  function pickCodec(VE, width, height, fps) {
    var i = 0;
    function next() {
      if (i >= CODECS.length) return Promise.resolve(null);
      var config = { codec: CODECS[i++], width: width, height: height, bitrate: BITRATE, framerate: fps, avc: { format: "avc" } };
      if (typeof VE.isConfigSupported !== "function") return Promise.resolve(config);
      return Promise.resolve(VE.isConfigSupported(config)).then(function (r) { return r && r.supported ? config : next(); }, next);
    }
    return next();
  }

  function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  // MP4 via WebCodecs and mp4-muxer; every dependency is passed in. Resolves {blob, type: "video/mp4"}.
  function encodeVideo(o) {
    o = o || {};
    var cards = arr(o.cards), fps = o.fps || 30, seconds = o.seconds || 3, width = o.width || W, height = o.height || H;
    var VE = o.VideoEncoder, VF = o.VideoFrame, progress = typeof o.onProgress === "function" ? o.onProgress : function () {};
    if (!VE || !VF || !o.Muxer || !o.ArrayBufferTarget || typeof o.render !== "function") {
      return Promise.reject(new Error("Making an MP4 needs WebCodecs and the MP4 muxer."));
    }
    var frames = planFrames(cards.length, fps, seconds), target, muxer, encoder, failure = null, duration = Math.round(1e6 / fps);
    function step(i) {
      if (failure) return Promise.reject(failure);
      if (i >= frames.length) return Promise.resolve();
      var f = frames[i];
      return Promise.resolve(o.render(f, cards[f.card])).then(function (source) {
        var frame = new VF(source, { timestamp: Math.round(f.frame * 1e6 / fps), duration: duration });
        try { encoder.encode(frame, { keyFrame: f.key }); } finally { frame.close(); }
        progress(((i + 1) / frames.length) * 0.97);
        var busy = (encoder.encodeQueueSize || 0) > 24;
        return busy || i % 10 === 9 ? drain().then(function () { return step(i + 1); }) : step(i + 1);
      });
    }
    function drain() {
      return wait(0).then(function () { return (encoder.encodeQueueSize || 0) > 24 ? wait(8).then(drain) : null; });
    }
    progress(0);
    return pickCodec(VE, width, height, fps).then(function (config) {
      if (!config) throw new Error("This browser can't make an MP4 of this size.");
      target = new o.ArrayBufferTarget();
      muxer = new o.Muxer({ target: target, video: { codec: "avc", width: width, height: height }, fastStart: "in-memory" });
      encoder = new VE({ output: function (chunk, meta) { muxer.addVideoChunk(chunk, meta); }, error: function (e) { failure = e || new Error("encoder error"); } });
      encoder.configure(config);
      return step(0);
    }).then(function () {
      return encoder.flush();
    }).then(function () {
      if (failure) throw failure;
      if (typeof encoder.close === "function") encoder.close();
      muxer.finalize();
      var blob = new Blob([target.buffer], { type: "video/mp4" });
      progress(1);
      return { blob: blob, type: "video/mp4" };
    });
  }

  function chooseEncoder(env) {
    env = env || {};
    var muxer = env.Muxer || (env.Mp4Muxer && env.Mp4Muxer.Muxer);
    if (env.VideoEncoder && muxer) return "webcodecs";
    if (env.MediaRecorder && (!env.canvas || typeof env.canvas.captureStream === "function")) return "mediarecorder";
    return "png";
  }

  function shareLinks(url, text) {
    var u = encodeURIComponent(url || ""), tx = encodeURIComponent(text || "");
    return {
      whatsapp: "https://wa.me/?text=" + encodeURIComponent((text ? text + " " : "") + (url || "")),
      x: "https://twitter.com/intent/tweet?text=" + tx + "&url=" + u,
      facebook: "https://www.facebook.com/sharer/sharer.php?u=" + u,
      email: "mailto:?subject=" + encodeURIComponent("School Wrapped") + "&body=" + encodeURIComponent((text ? text + "\n\n" : "") + (url || ""))
    };
  }

  // Native share with the video file when the browser can; otherwise a fallback the page turns into buttons.
  function shareVideo(file, share, nav) {
    share = share || {};
    function fallback() {
      return { method: "fallback", download: file || null, copy: share.url || "", links: shareLinks(share.url, share.text) };
    }
    var can = false;
    try { can = !!(file && nav && typeof nav.share === "function" && typeof nav.canShare === "function" && nav.canShare({ files: [file] })); } catch (e) { can = false; }
    if (!can) return Promise.resolve(fallback());
    return Promise.resolve(nav.share({ files: [file], title: share.title, text: share.text, url: share.url })).then(function () {
      return { method: "native" };
    }, function (err) {
      return err && err.name === "AbortError" ? { method: "cancelled" } : fallback();
    });
  }

  var API = {
    adapt: adapt, buildCards: buildCards, planFrames: planFrames, drawCard: drawCard, encodeVideo: encodeVideo,
    chooseEncoder: chooseEncoder, shareLinks: shareLinks, shareVideo: shareVideo, wrapText: wrapText,
    suspectYears: suspectYears, yearOfPeriodEnd: yearOfPeriodEnd, fmtExact: fmtExact, fmtPupils: fmtPupils,
    PALETTE_KEYS: PALETTE_KEYS, STATUS: STATUS, CODECS: CODECS,
    LIBS: { mp4Muxer: MP4_MUXER_URL, qrcode: QRCODE_URL }
  };
  root.MoneyWrapped = API;
  if (typeof document === "undefined") return;

  // ======================================================================
  // DOM wiring
  // ======================================================================
  var CARD_MS = 5000, ANIM_MS = 2400;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function button(cls, text, label) {
    var b = el("button", cls, text);
    b.type = "button";
    if (label) b.setAttribute("aria-label", label);
    return b;
  }
  function readPalette() {
    var cs = getComputedStyle(document.documentElement), pal = {};
    PALETTE_KEYS.forEach(function (k) { pal[k] = cs.getPropertyValue("--" + k).trim(); });
    return pal;
  }
  // Never rejects: a failed request or a body cut off while reading both come back as {ok: false}.
  function getJSON(url) {
    if (typeof fetch !== "function") return Promise.resolve({ ok: false, why: "offline" });
    return fetch(url, { credentials: "same-origin" }).then(function (r) {
      if (!r.ok) return { ok: false, why: r.status === 404 ? "missing" : "error" };
      return r.text().then(function (t) {
        try { return { ok: true, data: JSON.parse(t) }; } catch (e) { return { ok: false, why: "not-json" }; }
      });
    }).catch(function () { return { ok: false, why: "offline" }; });
  }
  var loading = {};
  function loadScript(key, src, integrity) {
    if (loading[key]) return loading[key];
    loading[key] = new Promise(function (resolve, reject) {
      var sc = document.createElement("script");
      sc.src = src; sc.async = true;
      if (integrity) { sc.integrity = integrity; sc.crossOrigin = "anonymous"; }
      sc.onload = function () { resolve(); };
      sc.onerror = function () { delete loading[key]; reject(new Error("Could not load " + src)); };
      document.head.appendChild(sc);
    });
    return loading[key];
  }
  var qrCache = {};
  function qrFor(url) {
    if (qrCache[url]) return Promise.resolve(qrCache[url]);
    return loadScript("qr", QRCODE_URL, QRCODE_SRI).then(function () {
      var q = root.qrcode(0, "M");
      q.addData(url); q.make();
      qrCache[url] = { size: q.getModuleCount(), dark: function (r, c) { return q.isDark(r, c); } };
      return qrCache[url];
    }).catch(function () { return null; });
  }
  function download(blob, name) {
    var a = document.createElement("a"), href = URL.createObjectURL(blob);
    a.href = href; a.download = name; a.hidden = true;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(href); }, 30000);
  }

  function start(rootEl) {
    var params = new URLSearchParams(location.search);
    var urn = (rootEl.getAttribute("data-urn") || params.get("urn") || "").replace(/[^0-9]/g, "");
    var mode = params.get("mode") === "ptfa" ? "ptfa" : (rootEl.getAttribute("data-mode") === "ptfa" ? "ptfa" : "school");
    if (!urn) return;
    var schoolPath = rootEl.getAttribute("data-path") || null;
    var status = el("p", "wr-status muted small");
    status.setAttribute("role", "status");
    status.textContent = "Loading the story…";
    rootEl.appendChild(status);
    var ctxUrl = rootEl.getAttribute("data-context") || "/data/wrapped/context.json";
    var unavailable = "We couldn't load this school's figures just now. Please try again later.";
    getJSON("/data/s/" + urn + ".json").then(function (s) {
      var code = s.ok ? obj(obj(s.data).council).code : null;
      return Promise.all([
        Promise.resolve(s), getJSON("/data/sx/" + urn + ".json"),
        code != null ? getJSON("/data/a/council-" + encodeURIComponent(code) + ".json") : Promise.resolve({ ok: false, why: "missing" }),
        getJSON("/data/a/england.json"), getJSON(ctxUrl)
      ]);
    }).then(function (r) {
      var data;
      if (!r[0].ok || !Object.keys(obj(r[0].data)).length) {
        data = { error: r[0].why === "missing" ? "Figures for this school aren't published yet." : unavailable,
          name: rootEl.getAttribute("data-name") || null, path: schoolPath };
      } else {
        data = adapt(r[0].data, r[1].ok ? r[1].data : null, r[2].ok ? r[2].data : null, r[3].ok ? r[3].data : null, r[4].ok ? r[4].data : null);
        if (!data.realLabel) data.realLabel = rootEl.getAttribute("data-real-label") || null;
      }
      return { data: data, model: buildCards(data, mode) };
    }).catch(function () {
      // Anything unexpected while loading still ends as a card in words, not a stuck loading line.
      var data = { error: unavailable, name: rootEl.getAttribute("data-name") || null, path: schoolPath };
      return { data: data, model: buildCards(data, mode) };
    }).then(function (story) {
      status.textContent = "";
      player(rootEl, story.model, story.data, mode, status);
    });
  }

  function player(rootEl, model, data, mode, status) {
    var cards = model.cards, n = cards.length, idx = 0, paused = false, held = false, stopped = false, rafId = 0;
    var reduce = root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var pal = readPalette(), qr = null, videoFile = null, busy = false;
    var pick = rootEl.querySelector(".wr-pick");
    if (pick) pick.hidden = true;

    var wrap = el("section", "wr-player");
    wrap.setAttribute("aria-label", model.title);
    var top = el("p", "wr-top small");
    var home = el("a", null, "School Money"); home.href = "/";
    top.appendChild(home);
    if (data && data.path) {
      top.appendChild(document.createTextNode(" · "));
      var sp = el("a", null, "School page"); sp.href = data.path;
      if (data.name) sp.setAttribute("aria-label", data.name + ": school page");
      top.appendChild(sp);
    }
    if (mode === "school" && data && data.pta && data.pta.latest) {
      top.appendChild(document.createTextNode(" · "));
      var pl = el("a", null, "PTFA Wrapped"); pl.href = "?mode=ptfa" + (rootEl.getAttribute("data-urn") ? "" : "&urn=" + encodeURIComponent(data.urn));
      top.appendChild(pl);
    } else if (mode === "ptfa" && data && !data.error) {
      top.appendChild(document.createTextNode(" · "));
      var sl = el("a", null, "School Wrapped"); sl.href = rootEl.getAttribute("data-urn") ? "?" : "?urn=" + encodeURIComponent(data.urn);
      top.appendChild(sl);
    }
    wrap.appendChild(top);

    var stage = el("div", "wr-stage");
    stage.tabIndex = 0;
    stage.setAttribute("role", "group");
    stage.setAttribute("aria-roledescription", "story");
    stage.setAttribute("aria-label", model.title + ". Left and right arrows move between cards, Space pauses, Escape exits.");
    var bars = el("div", "wr-bars"), fills = [];
    bars.setAttribute("aria-hidden", "true");
    for (var i = 0; i < n; i++) { var b = el("span", "wr-bar"), f = el("i"); b.appendChild(f); bars.appendChild(b); fills.push(f); }
    var canvas = el("canvas");
    canvas.width = W; canvas.height = H;
    canvas.setAttribute("role", "img");
    var g = canvas.getContext("2d");
    var live = el("p", "visually-hidden");
    live.setAttribute("aria-live", "polite");
    stage.appendChild(canvas); stage.appendChild(bars);
    wrap.appendChild(stage); wrap.appendChild(live);

    var controls = el("div", "wr-controls");
    var prevB = button("wr-prev", "‹ Back", "Previous card"), pauseB = button("wr-pause", reduce ? "Play" : "Pause"), nextB = button("wr-next", "Next ›", "Next card");
    pauseB.setAttribute("aria-pressed", reduce ? "true" : "false");
    controls.appendChild(prevB); controls.appendChild(pauseB); controls.appendChild(nextB);
    wrap.appendChild(controls);

    var actions = el("div", "wr-actions");
    var makeB = button("primary", "Make video"), shareB = button(null, "Share"), dlB = button(null, "Download video"), copyB = button(null, "Copy link");
    dlB.hidden = true;
    actions.appendChild(makeB); actions.appendChild(shareB); actions.appendChild(dlB); actions.appendChild(copyB);
    wrap.appendChild(actions);
    var bar = el("div", "wr-progress"), barFill = el("i");
    bar.setAttribute("role", "progressbar"); bar.setAttribute("aria-label", "Making the video");
    bar.setAttribute("aria-valuemin", "0"); bar.setAttribute("aria-valuemax", "100"); bar.setAttribute("aria-valuenow", "0");
    bar.hidden = true; bar.appendChild(barFill);
    wrap.appendChild(bar);
    var sheet = el("div", "wr-sheet");
    sheet.hidden = true;
    wrap.appendChild(sheet);
    var replay = button("wr-replay primary", "Play the story");
    replay.hidden = true;
    rootEl.appendChild(replay);

    var text = el("details", "wr-text"), sum = el("summary", null, "Read the story as text"), list = el("ol");
    text.appendChild(sum);
    cards.forEach(function (c) {
      var li = el("li"); li.appendChild(el("h3", null, c.title));
      if (c.big && c.big.text) li.appendChild(el("p", "wr-big", c.big.text + (c.big.unit ? " " + c.big.unit : "")));
      c.lines.forEach(function (l) { li.appendChild(el("p", null, l)); });
      if (c.source) li.appendChild(el("p", "muted small", "Source: " + c.source));
      if (c.link) { var a = el("a", null, c.link); a.href = c.link; li.appendChild(a); }
      list.appendChild(li);
    });
    text.appendChild(list);
    wrap.appendChild(text);
    rootEl.appendChild(wrap);
    status.textContent = "";
    wrap.appendChild(status);

    function say(msg) { status.textContent = msg; }
    function now() { return root.performance && performance.now ? performance.now() : Date.now(); }
    // One clock for the current card: it runs only while nothing pauses it (button, held pointer or Space).
    var base = 0, since = now(), running = false, ended = false;
    function shouldRun() { return !paused && !held && !stopped && !reduce; }
    function elapsed() { return base + (running ? now() - since : 0); }
    function sync() {
      var r = shouldRun();
      if (r === running) return;
      if (r) since = now(); else base += now() - since;
      running = r;
    }
    function show(i) {
      idx = clamp(i, 0, n - 1);
      base = 0; since = now(); ended = false;
      var c = cards[idx];
      canvas.setAttribute("aria-label", c.alt);
      live.textContent = (idx + 1) + " of " + n + ". " + c.alt;
      if (c.qr && !qr) qrFor(c.qr.url).then(function (m) { qr = m; if (cards[idx] === c) draw(1); });
      draw(reduce || paused ? 1 : 0);
    }
    function draw(t) {
      drawCard(g, cards[idx], t, pal, { index: idx, count: n, reducedMotion: reduce, qr: cards[idx].qr ? qr : null });
      var own = reduce ? 1 : clamp(elapsed() / CARD_MS, 0, 1);
      fills.forEach(function (f, i) { f.style.transform = "scaleX(" + (i < idx ? 1 : (i > idx ? 0 : own)) + ")"; });
    }
    function setPaused(p) {
      paused = p; sync();
      pauseB.textContent = p ? "Play" : "Pause";
      pauseB.setAttribute("aria-pressed", p ? "true" : "false");
    }
    function loop() {
      rafId = 0;
      if (stopped) return;
      if (running) {
        var e = elapsed();
        draw(clamp(e / ANIM_MS, 0, 1));
        if (e >= CARD_MS) { if (idx < n - 1) show(idx + 1); else { setPaused(true); ended = true; } }
      }
      rafId = requestAnimationFrame(loop);
    }
    function go(delta) { show(idx + delta); }
    function hold(on) { held = on; sync(); }
    var downX = null, downT = 0;
    stage.addEventListener("pointerdown", function (e) { downX = e.clientX; downT = now(); hold(true); });
    stage.addEventListener("pointerup", function (e) {
      if (downX == null) return;
      var dx = e.clientX - downX, dt = now() - downT, rect = stage.getBoundingClientRect();
      downX = null; hold(false);
      if (Math.abs(dx) > 50) go(dx < 0 ? 1 : -1);
      else if (dt < 300) go(e.clientX - rect.left < rect.width / 3 ? -1 : 1);
    });
    stage.addEventListener("pointercancel", function () { downX = null; hold(false); });
    stage.addEventListener("pointerleave", function () { if (downX != null) { downX = null; hold(false); } });
    prevB.addEventListener("click", function () { go(-1); });
    nextB.addEventListener("click", function () { go(1); });
    pauseB.addEventListener("click", function () {
      if (ended) { setPaused(false); show(0); return; }
      setPaused(!paused);
    });
    var spaceDown = 0;
    function onKey(e) {
      if (!rootEl.contains(document.activeElement) && document.activeElement !== document.body) return;
      var tag = (e.target && e.target.tagName) || "";
      if (e.key === "Escape") {
        if (!sheet.hidden) { closeSheet(); e.preventDefault(); return; }
        if (!stopped) { exit(); e.preventDefault(); }
        return;
      }
      if (stopped || /^(BUTTON|A|INPUT|SELECT|TEXTAREA|SUMMARY)$/.test(tag)) return;
      if (e.key === "ArrowRight") { go(1); e.preventDefault(); }
      else if (e.key === "ArrowLeft") { go(-1); e.preventDefault(); }
      else if (e.key === " " || e.key === "Spacebar") {
        e.preventDefault();
        if (!e.repeat) { spaceDown = now(); hold(true); }
      }
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("keyup", function (e) {
      if ((e.key === " " || e.key === "Spacebar") && spaceDown) {
        var quick = now() - spaceDown < 300;
        spaceDown = 0; hold(false);
        if (quick) go(1);
      }
    });
    function exit() {
      stopped = true; sync();
      if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
      wrap.hidden = true; replay.hidden = false;
      replay.focus();
    }
    replay.addEventListener("click", function () {
      stopped = false; replay.hidden = true; wrap.hidden = false;
      show(idx); sync(); stage.focus();
      if (!rafId) rafId = requestAnimationFrame(loop);
    });

    var lastTrigger = null;
    function closeSheet() {
      sheet.hidden = true;
      while (sheet.firstChild) sheet.removeChild(sheet.firstChild);
      if (lastTrigger) lastTrigger.focus();
    }
    function openSheet(result, trigger) {
      lastTrigger = trigger;
      while (sheet.firstChild) sheet.removeChild(sheet.firstChild);
      sheet.appendChild(el("h2", null, "Share this story"));
      var ul = el("ul");
      [["whatsapp", "WhatsApp"], ["x", "X"], ["facebook", "Facebook"], ["email", "Email"]].forEach(function (p) {
        var li = el("li"), a = el("a", "button quiet", p[1]);
        a.href = result.links[p[0]];
        if (p[0] !== "email") { a.target = "_blank"; a.rel = "noopener"; }
        li.appendChild(a); ul.appendChild(li);
      });
      sheet.appendChild(ul);
      var row = el("div", "wr-actions"), copy2 = button(null, "Copy link"), close = button("wr-close", "Close");
      copy2.addEventListener("click", copyLink);
      close.addEventListener("click", closeSheet);
      if (result.download) {
        var dl2 = button(null, "Download video");
        dl2.addEventListener("click", function () { download(result.download, result.download.name || "school-wrapped.mp4"); });
        row.appendChild(dl2);
      }
      row.appendChild(copy2); row.appendChild(close);
      sheet.appendChild(row);
      sheet.appendChild(el("p", "muted small", model.share.url));
      sheet.hidden = false;
      close.focus();
    }
    function copyLink() {
      var url = model.share.url;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(function () { say("Link copied."); }, function () { say("Copy this link: " + url); });
      } else say("Copy this link: " + url);
    }
    copyB.addEventListener("click", copyLink);
    shareB.addEventListener("click", function () {
      if (videoFile) {
        shareVideo(videoFile, model.share, navigator).then(function (r) { if (r.method === "fallback") openSheet(r, shareB); });
      } else if (navigator.share) {
        navigator.share({ title: model.share.title, text: model.share.text, url: model.share.url }).catch(function (e) {
          if (!e || e.name !== "AbortError") openSheet({ links: shareLinks(model.share.url, model.share.text) }, shareB);
        });
      } else openSheet({ links: shareLinks(model.share.url, model.share.text) }, shareB);
    });
    dlB.addEventListener("click", function () { if (videoFile) download(videoFile, videoFile.name); });

    var vcanvas = el("canvas");
    vcanvas.width = W; vcanvas.height = H;
    var vg = vcanvas.getContext("2d");
    var fileBase = slugify(data && data.name ? data.name : "school") + (mode === "ptfa" ? "-ptfa-wrapped" : "-school-wrapped");
    function progress(p) {
      bar.hidden = false;
      var v = Math.round(clamp(p, 0, 1) * 100);
      bar.setAttribute("aria-valuenow", String(v));
      bar.setAttribute("aria-valuetext", v + "%");
      barFill.style.transform = "scaleX(" + v / 100 + ")";
    }
    function render(f) {
      drawCard(vg, cards[f.card], f.t, pal, { index: f.card, count: n, fade: f.fade, qr: cards[f.card].qr ? qr : null });
      return vcanvas;
    }
    function recordWebm() {
      return new Promise(function (resolve, reject) {
        var stream = vcanvas.captureStream(30), types = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"];
        var type = types.filter(function (t) { return !MediaRecorder.isTypeSupported || MediaRecorder.isTypeSupported(t); })[0];
        var rec = new MediaRecorder(stream, type ? { mimeType: type, videoBitsPerSecond: BITRATE } : undefined), chunks = [];
        var frames = planFrames(n, 30, 3), i = 0;
        rec.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
        rec.onstop = function () { progress(1); resolve({ blob: new Blob(chunks, { type: "video/webm" }), type: "video/webm" }); };
        rec.onerror = function (e) { reject(e.error || new Error("recording stopped")); };
        rec.start();
        (function tick() {
          if (i >= frames.length) { rec.stop(); return; }
          render(frames[i]); i++;
          progress(i / frames.length * 0.97);
          setTimeout(tick, 1000 / 30);
        })();
      });
    }
    function savePngs() {
      var i = 0;
      return new Promise(function (resolve) {
        (function nextCard() {
          if (i >= n) { progress(1); resolve(null); return; }
          drawCard(vg, cards[i], 1, pal, { index: i, count: n, qr: cards[i].qr ? qr : null });
          var k = i;
          vcanvas.toBlob(function (b) {
            if (b) download(b, fileBase + "-" + String(k + 1).replace(/^(\d)$/, "0$1") + ".png");
            i++; progress(i / n);
            setTimeout(nextCard, 350);
          }, "image/png");
        })();
      });
    }
    makeB.addEventListener("click", function () {
      if (busy) return;
      busy = true; makeB.disabled = true; progress(0); say("Making your video…");
      var outro = cards.filter(function (c) { return c.qr; })[0];
      var mux = root.VideoEncoder ? loadScript("mux", MP4_MUXER_URL, MP4_MUXER_SRI).then(function () { return root.Mp4Muxer || null; }, function () { return null; }) : Promise.resolve(null);
      Promise.all([mux, outro && !qr ? qrFor(outro.qr.url) : Promise.resolve(qr)]).then(function (r) {
        var M = r[0]; qr = r[1] || qr;
        var kind = chooseEncoder({ VideoEncoder: root.VideoEncoder, VideoFrame: root.VideoFrame, Muxer: M && M.Muxer, MediaRecorder: root.MediaRecorder, canvas: vcanvas });
        if (kind === "webcodecs") {
          return encodeVideo({ cards: cards, fps: 30, seconds: 3, render: render, VideoEncoder: root.VideoEncoder, VideoFrame: root.VideoFrame,
            Muxer: M.Muxer, ArrayBufferTarget: M.ArrayBufferTarget, onProgress: progress })
            .catch(function () { return root.MediaRecorder ? recordWebm() : savePngs(); });
        }
        if (kind === "mediarecorder") return recordWebm();
        say("This browser can't make a video, so each card is saved as an image instead.");
        return savePngs();
      }).then(function (result) {
        if (result && result.blob) {
          var ext = result.type === "video/mp4" ? ".mp4" : ".webm";
          try { videoFile = new File([result.blob], fileBase + ext, { type: result.type }); } catch (e) { videoFile = result.blob; videoFile.name = fileBase + ext; }
          dlB.hidden = false;
          say("Your video is ready. Share it or download it.");
          dlB.focus();
        } else if (result === null) say("Your cards are saved as images.");
      }).catch(function () {
        say("Sorry, this browser couldn't make the video. You can still share the link.");
      }).then(function () { busy = false; makeB.disabled = false; });
    });

    if (reduce) pauseB.hidden = true;
    if (!data || data.error) { makeB.hidden = true; shareB.hidden = true; }
    show(0);
    sync();
    if (!reduce) rafId = requestAnimationFrame(loop);
    if (root.matchMedia) {
      var mq = root.matchMedia("(prefers-color-scheme: dark)");
      var repaint = function () { pal = readPalette(); draw(reduce || paused ? 1 : clamp(elapsed() / ANIM_MS, 0, 1)); };
      if (mq.addEventListener) mq.addEventListener("change", repaint);
    }
  }

  function boot() {
    var rootEl = document.getElementById("wrapped-app");
    if (rootEl) start(rootEl);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})(typeof globalThis !== "undefined" ? globalThis : this);
