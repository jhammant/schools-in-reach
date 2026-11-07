/* School Money — map.js (unit C1, the /map/ explorer). Defer-loaded after app.js, Leaflet and protomaps-leaflet.
   Pure helpers are exported as globalThis.MoneyMap (loadable under node for tests); DOM wiring runs only in a
   browser. Data goes into the page through textContent/setAttribute only: no HTML built from data.

   Reads: /data/map/measures.json, /data/map/councils.geojson, /data/map/constituencies.geojson,
          /data/map/schools.json, /data/search.json, /data/s/<urn>.json, /data/a/<id>.json.
   Static copy (IFS reasons with page numbers, notes, defaults) comes from <script id="mx-context">.
   Every fetch tolerates a 404, a body that is not JSON or a missing key, and says so in words. */
(function (root) {
  "use strict";

  // ======================================================================
  // Pure helpers (no DOM)
  // ======================================================================
  var ORDER = ["in_deficit", "heading_for_deficit", "tight", "healthy", "large_reserves"];
  var LABELS = { in_deficit: "In deficit", heading_for_deficit: "Heading for deficit", tight: "Tight", healthy: "Healthy", large_reserves: "Large reserves" };
  var ICONS = { in_deficit: "▼", heading_for_deficit: "↘", tight: "●", healthy: "✓", large_reserves: "▲" };
  var STATUS_VARS = { in_deficit: "--critical", heading_for_deficit: "--serious", tight: "--warning", healthy: "--good", large_reserves: "--plenty" };
  var GEOS = ["council", "constituency"];
  var MEASURE_KEYS = ["pct_in_deficit", "deficit_pp", "reserve_median_pp", "gov_pp_median", "spend_pp_median", "dsg_pp",
    "pta_median_pp", "fsm_pct", "pupils"];
  var DEFAULTS = { m: "pct_in_deficit", y: null, g: "council", q: "" };
  var FBIT = "https://financial-benchmarking-and-insights-tool.education.gov.uk/school/";
  var NOT_PUBLISHED = "Not published for this year";
  var WHY_TITLE = "Why schools go into deficit";
  // Used only when the page's context block is missing (it carries the IFS text with page numbers).
  var WHY_FALLBACK = { title: WHY_TITLE, text: "Most of a school's money goes on staff, so when pay and other costs rise faster than funding, " +
    "or pupil numbers fall, the budget is squeezed quickly. A deficit usually comes from several pressures at once, not one bad decision.",
    pages: [62, 63] };
  var HELPS_FALLBACK = "What helps: a plan agreed with the council or trust to bring the budget back into balance over a few years, " +
    "forecasts that governors see often, and early talks about pupil numbers and special needs funding.";
  var CITE_FALLBACK = "IFS, Annual report on education spending in England: 2025–26 (January 2026)";

  function app() { return root.MoneyApp || null; }
  function isNum(v) { return typeof v === "number" && isFinite(v); }
  function own(o, k) { return o != null && Object.prototype.hasOwnProperty.call(o, k); }
  function obj(o) { return o && typeof o === "object" && !Array.isArray(o) ? o : {}; }

  // £4,115 style, to the pound (MoneyApp has no exported fmtExact).
  function fmtExact(v, signed) {
    if (!isNum(v)) return "—";
    var sign = v < 0 ? "-" : (signed && v > 0 ? "+" : "");
    return sign + "£" + Math.round(Math.abs(v)).toLocaleString("en-GB");
  }
  function fmtMoney(v, signed) {
    var A = app();
    if (A && typeof A.fmtMoney === "function") return A.fmtMoney(v, signed);
    if (!isNum(v)) return "—";
    var sign = v < 0 ? "-" : (signed && v > 0 ? "+" : ""), a = Math.abs(v);
    if (a >= 1e9) return sign + "£" + (a / 1e9).toFixed(2) + "bn";
    if (a >= 1e6) return sign + "£" + (a / 1e6).toFixed(1) + "m";
    if (a >= 1e3) return sign + "£" + Math.round(a / 1e3) + "k";
    return sign + "£" + Math.round(a).toLocaleString("en-GB");
  }
  function fmtNumber(v, dp) {
    return Number(v).toLocaleString("en-GB", { minimumFractionDigits: 0, maximumFractionDigits: dp == null ? 1 : dp });
  }
  function unitSuffix(unit) { return unit === "gbp_pp" ? " per pupil" : (unit === "pupils" ? " pupils" : ""); }
  function fmtBound(v, unit, signed) {
    if (unit === "pct") return v.toFixed(1) + "%";
    if (unit === "gbp_pp") return fmtExact(v, signed);
    return fmtNumber(v, 1);
  }
  // A measure value with its unit, or null when missing (callers then say it isn't published, never £0).
  function fmtValue(v, unit, signed) {
    if (!isNum(v)) return null;
    return fmtBound(v, unit, signed) + unitSuffix(unit);
  }
  // The precision build_measures keeps: £1 per pupil, 0.1 for percentages and pupils (FTE counts have tenths).
  function stepFor(unit) { return unit === "gbp_pp" ? 1 : 0.1; }
  function tidy(v, step) { return step < 1 ? Math.round(v * 10) / 10 : Math.round(v); }

  // 1, 2, 2.5 or 5 times a power of ten, nearest to v (and at least step).
  function nice(v, step) {
    if (!(v > 0)) return step;
    var p = Math.pow(10, Math.floor(Math.log(v) / Math.LN10)), best = p, gap = Infinity;
    [1, 2, 2.5, 5, 10].forEach(function (m) { var c = m * p, d = Math.abs(c - v); if (d < gap) { gap = d; best = c; } });
    return Math.max(step, tidy(best, step));
  }

  // Class breaks. Sequential: quantile thresholds with duplicates removed. Diverging: symmetric about 0,
  // a grey middle class for values near 0, then negative and positive arms.
  // Returns {scale, unit, step, thresholds, classes: [{lo, hi, side}], min, max}; lo/hi null = open-ended.
  function binsFor(values, opts) {
    opts = opts || {};
    var scale = opts.scale === "diverging" ? "diverging" : "sequential";
    var n = Math.max(1, Math.floor(opts.n || 5)), unit = opts.unit || "gbp_pp", step = stepFor(unit);
    var vals = (Array.isArray(values) ? values : []).filter(isNum).sort(function (a, b) { return a - b; });
    var out = { scale: scale, unit: unit, step: step, thresholds: [], classes: [], min: null, max: null };
    if (!vals.length) return out;
    out.min = vals[0];
    out.max = vals[vals.length - 1];
    if (scale === "sequential") {
      for (var i = 1; i < n; i++) {
        var q = tidy(vals[Math.floor(i * vals.length / n)], step);
        if (q > out.min && (!out.thresholds.length || q > out.thresholds[out.thresholds.length - 1])) out.thresholds.push(q);
      }
      var los = [out.min].concat(out.thresholds);
      out.classes = los.map(function (lo, k) {
        return { lo: lo, hi: k < los.length - 1 ? tidy(los[k + 1] - step, step) : out.max, side: "seq" };
      });
      return out;
    }
    var arms = Math.max(1, Math.floor((n - 1) / 2));
    var abs = vals.map(Math.abs).sort(function (a, b) { return a - b; });
    var top = abs[Math.floor(0.95 * (abs.length - 1))] || abs[abs.length - 1];
    var e = nice(top / (2 * arms + 1), step);
    for (var j = 0; j < arms; j++) out.thresholds.push(tidy(e * (1 + 2 * j), step));
    var T = out.thresholds, classes = [];
    for (var a = arms; a >= 1; a--) {
      classes.push({ lo: a === arms ? null : tidy(-T[a] + step, step), hi: -T[a - 1], side: "neg" });
    }
    classes.push({ lo: tidy(-T[0] + step, step), hi: tidy(T[0] - step, step), side: "mid" });
    for (var b = 1; b <= arms; b++) {
      classes.push({ lo: T[b - 1], hi: b === arms ? null : tidy(T[b] - step, step), side: "pos" });
    }
    out.classes = classes;
    return out;
  }

  // Class index for v, or null when v is missing (drawn hatched as "No data", never as the lowest class).
  function classify(v, bins) {
    if (!isNum(v) || !bins || !bins.classes || !bins.classes.length) return null;
    var T = bins.thresholds || [], k = 0, i;
    if (bins.scale === "diverging") {
      var arms = T.length, a = Math.abs(v);
      if (a < T[0]) return arms;
      for (i = 0; i < arms; i++) if (a >= T[i]) k = i + 1;
      return v < 0 ? arms - k : arms + k;
    }
    for (i = 0; i < T.length; i++) if (v >= T[i]) k = i + 1;
    return k;
  }

  function parseColour(c) {
    var s = String(c == null ? "" : c).trim(), m;
    if ((m = /^#([0-9a-f]{3})$/i.exec(s))) return [0, 1, 2].map(function (i) { return parseInt(m[1][i] + m[1][i], 16); });
    if ((m = /^#([0-9a-f]{6})$/i.exec(s))) return [0, 2, 4].map(function (i) { return parseInt(m[1].slice(i, i + 2), 16); });
    if ((m = /^rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)/i.exec(s))) return [+m[1], +m[2], +m[3]];
    return null;
  }
  function hex(rgb) {
    return "#" + rgb.map(function (v) { var h = Math.max(0, Math.min(255, Math.round(v))).toString(16); return h.length < 2 ? "0" + h : h; }).join("");
  }
  // a blended toward b by t (0 = a, 1 = b).
  function mix(a, b, t) {
    var x = parseColour(a), y = parseColour(b);
    if (!x || !y) return String(t >= 0.5 ? b : a);
    return hex([0, 1, 2].map(function (i) { return x[i] + (y[i] - x[i]) * t; }));
  }
  // Colours for n classes from design tokens (palette: {accent, critical, plenty, lineStrong, card}).
  // Sequential is one hue (--accent) at rising strength; diverging runs --critical, grey (--line-strong), --plenty.
  function ramp(scale, palette, n) {
    var p = palette || {}, base = p.card || "#ffffff";
    n = Math.max(1, Math.floor(n || 5));
    if (scale !== "diverging") {
      if (n === 1) return [mix(base, p.accent, 0.75)];
      var out = [];
      for (var i = 0; i < n; i++) out.push(mix(base, p.accent, 0.18 + 0.82 * i / (n - 1)));
      return out;
    }
    var arms = Math.max(1, Math.floor((n - 1) / 2)), neg = [], pos = [];
    for (var a = arms; a >= 1; a--) neg.push(mix(base, p.critical, 0.3 + 0.7 * a / arms));
    for (var b = 1; b <= arms; b++) pos.push(mix(base, p.plenty, 0.3 + 0.7 * b / arms));
    return neg.concat([p.lineStrong || "#999999"], pos);
  }

  function classLabel(c, unit) {
    var s = unitSuffix(unit);
    if (c.lo == null) return fmtBound(c.hi, unit) + " or less" + s;
    if (c.hi == null) return fmtBound(c.lo, unit) + " or more" + s;
    if (c.lo === c.hi) return fmtBound(c.lo, unit) + s;
    return fmtBound(c.lo, unit) + " to " + fmtBound(c.hi, unit) + s;
  }
  // Legend rows for bins, the class England falls in and its marker text ("England: 12.4%").
  function legendModel(bins, measure, englandValue) {
    var m = obj(measure), unit = m.unit || (bins && bins.unit) || "gbp_pp";
    var items = ((bins && bins.classes) || []).map(function (c, i) { return { label: classLabel(c, unit), cls: i }; });
    var ev = fmtValue(englandValue, unit, m.signed);
    return {
      title: m.label || "",
      items: items,
      missing: { label: "No data", cls: null },
      england: ev ? { cls: classify(englandValue, bins), text: "England: " + ev } : null,
      empty: items.length ? null : "Figures for this year aren't published yet."
    };
  }

  // ---------------------------------------------------------------- URL state (?m=&y=&g=&q=)
  function queryParams(search) {
    var out = {}, s = String(search == null ? "" : search).replace(/^\?/, "");
    if (!s) return out;
    s.split("&").forEach(function (pair) {
      if (!pair) return;
      var i = pair.indexOf("="), k = i < 0 ? pair : pair.slice(0, i), v = i < 0 ? "" : pair.slice(i + 1);
      try { k = decodeURIComponent(k.replace(/\+/g, " ")); v = decodeURIComponent(v.replace(/\+/g, " ")); } catch (e) { return; }
      if (!own(out, k)) out[k] = v;
    });
    return out;
  }
  function stateOptions(opts) {
    opts = opts || {};
    var years = Array.isArray(opts.years) ? opts.years : [];
    var measures = Array.isArray(opts.measures) && opts.measures.length ? opts.measures : MEASURE_KEYS;
    var d = obj(opts.defaults), y = d.y && (!years.length || years.indexOf(d.y) >= 0) ? d.y : (years.length ? years[years.length - 1] : null);
    return {
      years: years, measures: measures, meta: obj(opts.meta),
      defaults: { m: measures.indexOf(d.m) >= 0 ? d.m : (measures.indexOf(DEFAULTS.m) >= 0 ? DEFAULTS.m : measures[0]),
        y: y, g: GEOS.indexOf(d.g) >= 0 ? d.g : DEFAULTS.g, q: "" }
    };
  }
  function measureFits(o, m, g) {
    var levels = obj(o.meta[m]).levels;
    return !Array.isArray(levels) || levels.indexOf(g) >= 0;
  }
  // Invalid values fall back to the defaults; a measure the geography lacks (DSG for constituencies) does too.
  function parseState(search, opts) {
    var o = stateOptions(opts), p = queryParams(search), d = o.defaults;
    var g = GEOS.indexOf(p.g) >= 0 ? p.g : d.g;
    var m = o.measures.indexOf(p.m) >= 0 ? p.m : d.m;
    if (!measureFits(o, m, g)) m = d.m;
    var y = d.y;
    if (p.y && /^\d{4}-\d{2}$/.test(p.y) && (o.years.length ? o.years.indexOf(p.y) >= 0 : true)) y = p.y;
    return { m: m, y: y, g: g, q: cleanQuery(p.q) };
  }
  // The q value as stored in state and the URL: control characters and runs of spaces collapsed, at most 80 characters.
  function cleanQuery(q) {
    return String(q == null ? "" : q).replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim().slice(0, 80);
  }
  // Defaults are omitted; returns "" or "?m=...&y=...&g=...&q=...".
  function serialiseState(state, opts) {
    var o = stateOptions(opts), d = o.defaults, s = obj(state), parts = [];
    if (s.m && s.m !== d.m) parts.push("m=" + encodeURIComponent(s.m));
    if (s.y && s.y !== d.y) parts.push("y=" + encodeURIComponent(s.y));
    if (s.g && s.g !== d.g) parts.push("g=" + encodeURIComponent(s.g));
    if (s.q) parts.push("q=" + encodeURIComponent(s.q));
    return parts.length ? "?" + parts.join("&") : "";
  }

  // ---------------------------------------------------------------- search
  function norm(s) {
    return String(s == null ? "" : s).toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  }
  function normName(s) {
    return norm(String(s == null ? "" : s).replace(/&/g, " and ")).replace(/[^a-z0-9]+/g, " ").trim();
  }
  var TYPE_ORDER = { school: 0, council: 1, constituency: 2, trust: 3 };
  // A copy of MoneyApp.rankSearch for when app.js is not loaded.
  function localRank(rows, q, limit) {
    limit = limit || 8;
    var needle = norm(q).trim().replace(/\s+/g, " ");
    if (!needle || !Array.isArray(rows)) return [];
    var words = needle.split(" "), hits = [];
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      if (!r || !r.name) continue;
      var name = norm(r.name), sub = norm(r.sub), score = 0;
      if (name.indexOf(needle) === 0) score = 3;
      else {
        var tokens = name.split(/[^a-z0-9]+/);
        if (words.every(function (w) { return tokens.some(function (t) { return t.indexOf(w) === 0; }); })) score = 2;
        else if ((name + " " + sub).indexOf(needle) !== -1) score = 1;
      }
      if (score) hits.push({ row: r, score: score, i: i, name: name });
    }
    hits.sort(function (a, b) {
      return b.score - a.score || (TYPE_ORDER[a.row.t] - TYPE_ORDER[b.row.t]) || a.name.length - b.name.length || a.i - b.i;
    });
    return hits.slice(0, limit).map(function (h) { return h.row; });
  }
  // School, council and constituency rows of /data/search.json that match q (trusts aren't on the map).
  function searchHits(rows, q, limit) {
    var pool = (Array.isArray(rows) ? rows : []).filter(function (r) { return r && (r.t === "school" || r.t === "council" || r.t === "constituency"); });
    var A = app();
    var rank = A && typeof A.rankSearch === "function" ? A.rankSearch : localRank;
    return rank(pool, q, limit || 8);
  }
  function featuresOf(boundaries, geo) {
    var b = boundaries;
    if (b && !Array.isArray(b) && !Array.isArray(b.features) && b[geo]) b = b[geo];
    if (b && Array.isArray(b.features)) b = b.features;
    return Array.isArray(b) ? b : [];
  }
  // {kind: "school", urn} or {kind: "area", geo, id, featureIndex}: a boundary matched by id, then by name.
  function pickTarget(row, boundaries) {
    if (!row || row.id == null) return null;
    if (row.t === "school") return { kind: "school", urn: String(row.id) };
    if (row.t !== "council" && row.t !== "constituency") return null;
    var geo = row.t, want = String(row.id), wantId = want.indexOf(geo + "-") === 0 ? want : geo + "-" + want;
    var feats = featuresOf(boundaries, geo), i, p;
    for (i = 0; i < feats.length; i++) {
      p = obj(feats[i] && feats[i].properties);
      if (p.id === wantId || (p.code != null && String(p.code) === want)) return { kind: "area", geo: geo, id: p.id || wantId, featureIndex: i };
    }
    var n = normName(row.name);
    for (i = 0; n && i < feats.length; i++) {
      p = obj(feats[i] && feats[i].properties);
      if (normName(p.name) === n) return { kind: "area", geo: geo, id: p.id || wantId, featureIndex: i };
    }
    return { kind: "area", geo: geo, id: wantId, featureIndex: -1 };
  }

  // ---------------------------------------------------------------- cards
  function pagesText(pages) {
    var p = (Array.isArray(pages) ? pages : []).filter(isNum);
    if (!p.length) return "";
    if (p.length === 1) return "p." + p[0];
    if (p.length === 2 && p[1] === p[0] + 1) return "p." + p[0] + "–" + p[1];
    return "pp." + p.join(", ");
  }
  function framingLine(f, cite, label) {
    var pg = pagesText(f.pages);
    return { label: label || f.title || WHY_TITLE, text: f.text + " (" + cite + (pg ? ", " + pg : "") + ")", kind: "why" };
  }
  // The reasons and what helps, added wherever a card names a deficit.
  function explainLines(ctx, extra) {
    var c = obj(ctx), cite = c.cite || CITE_FALLBACK, why = c.why && c.why.text ? c.why : WHY_FALLBACK, out = [];
    out.push(framingLine(why, cite, WHY_TITLE));
    (extra || []).forEach(function (f) { if (f && f.text) out.push(framingLine(f, cite)); });
    out.push({ label: "What helps", text: String(c.helps || HELPS_FALLBACK).replace(/^What helps:\s*/, ""), kind: "helps" });
    return out;
  }
  function mentionsDeficit(lines) {
    return lines.some(function (l) { return /deficit/i.test(l.label + " " + l.text); });
  }

  // One adapter for a measures.json entry plus its optional /data/a/<id>.json document.
  function adaptArea(entry, areaDoc, year) {
    var e = obj(entry), a = obj(areaDoc), by = obj(obj(a.by_year)[year]), S = obj(by.all || by);
    var dsg = obj(obj(a.dsg)[year]);
    return {
      id: e.id || a.id || null, name: e.name || a.name || "This area", p: e.p || a.path || null, m: obj(e.m),
      schools: isNum(S.schools) ? S.schools : null, inDeficit: isNum(S.in_deficit) ? S.in_deficit : null,
      deficitTotal: isNum(S.deficit_total) ? S.deficit_total : null,
      dsgBalance: isNum(dsg.balance) ? dsg.balance : null,
      pupils: isNum(obj(a.pupils_by_year)[year]) ? a.pupils_by_year[year] : null
    };
  }
  function seriesOf(m, key) {
    var s = obj(obj(m)[key]);
    return Object.keys(s).sort().filter(function (y) { return isNum(s[y]); }).map(function (y) { return { y: y, v: s[y] }; });
  }
  // Card for an area: entry is a measures.json entry with its id; measure is its meta (with key);
  // england is measures.json's england block (or a number for this measure and year).
  function areaCardModel(entry, measure, year, england, areaDoc, ctx) {
    var A = adaptArea(entry, areaDoc, year), M = obj(measure), key = M.key || DEFAULTS.m, unit = M.unit || "gbp_pp";
    var c = obj(ctx), v = obj(A.m[key])[year];
    var ev = isNum(england) ? england : obj(obj(england)[key])[year];
    var label = (M.label || key) + (year ? ", " + year : "");
    var text = fmtValue(v, unit, M.signed);
    var cash = null;
    if (key === "deficit_pp" && A.deficitTotal != null) cash = fmtMoney(A.deficitTotal, true);
    if (key === "dsg_pp" && A.dsgBalance != null) cash = fmtMoney(A.dsgBalance, true);
    text = (text || NOT_PUBLISHED) + (text && cash ? ", total " + cash : "") + (isNum(ev) ? " (England " + fmtValue(ev, unit, M.signed) + ")" : "");
    var lines = [{ label: label, text: text }];
    if (A.schools != null && A.inDeficit != null) lines.push({ label: "Schools in deficit", text: A.inDeficit + " of " + A.schools + (year ? " in " + year : "") });
    var pupils = A.pupils != null ? A.pupils : obj(A.m.pupils)[year];
    if (key !== "pupils" && isNum(pupils)) lines.push({ label: "Pupils" + (year ? ", " + year : ""), text: fmtNumber(pupils, 1) });
    lines.push({ label: "Source", text: (year ? year + ", " : "") + (M.source || "DfE returns") });
    if (unit === "gbp_pp") lines.push({ label: "Note", text: c.cash_note || "£ figures are cash for each year, not adjusted for inflation." });
    if (key === "pta_median_pp" && c.pta_note) lines.push({ label: "About parents' associations", text: c.pta_note });
    if (key === "dsg_pp" && c.dsg_note) lines.push({ label: "High-needs budgets", text: c.dsg_note });
    if (mentionsDeficit(lines) || key in { deficit_pp: 1, reserve_median_pp: 1, dsg_pp: 1 }) {
      lines = lines.concat(explainLines(c, key === "dsg_pp" ? [c.send] : []));
    }
    var links = [];
    if (A.id) links.push({ href: "/deck/?area=" + encodeURIComponent(A.id), text: "Make slides for " + A.name });
    return {
      kind: "area", title: A.name, lines: lines, spark: seriesOf(A.m, key),
      sparkUnit: unit, sparkSigned: !!M.signed, sparkLabel: M.label || key,
      open: A.p ? { href: A.p, text: "Open the " + A.name + " page" } : null,
      links: links,
      pin: A.id ? { type: "area", id: String(A.id), name: A.name, p: A.p || "" } : null
    };
  }

  function schoolPath(urn, name) {
    var A = app(), slug = A && typeof A.slugify === "function" ? A.slugify(name) : normName(name).replace(/ /g, "-") || "school";
    return "/school/" + urn + "-" + slug + "/";
  }
  // One adapter for /data/s/<urn>.json (fields per the shared contract). fallback ({urn, name}) is the identity the
  // caller already knows; it fills in whichever of those the document lacks.
  function adaptSchool(s, fallback) {
    var d = obj(s), f = obj(fallback), key = ORDER.indexOf(d.status) >= 0 ? d.status : null;
    var urn = d.urn != null ? String(d.urn) : (f.urn != null ? String(f.urn) : null), name = d.name || f.name || "";
    var pupils = isNum(d.pupils) ? d.pupils : null;
    function pp(total, given) { return isNum(given) ? given : (isNum(total) && pupils ? Math.round(total / pupils) : null); }
    return {
      urn: urn, name: name || (urn ? "School " + urn : "This school"),
      path: d.path || (urn ? schoolPath(urn, name) : null),
      status: key, label: key ? LABELS[key] : null, reason: typeof d.reason === "string" ? d.reason : null,
      year: typeof d.year === "string" ? d.year : null,
      source: d.source || (d.academy ? "DfE AAR return" : "DfE CFR return"),
      reserve: isNum(d.reserve) ? d.reserve : null, reservePp: pp(d.reserve, d.reserve_pp),
      income: isNum(d.income) ? d.income : null, incomePp: pp(d.income, d.income_pp),
      pupils: pupils
    };
  }
  function moneyLine(label, year, pp, total, signed) {
    var l = label + (year ? ", " + year : "");
    if (!isNum(pp)) return { label: l, text: NOT_PUBLISHED };
    return { label: l, text: fmtExact(pp, signed) + " per pupil" + (isNum(total) ? " (total " + fmtMoney(total, signed) + ")" : "") };
  }
  // Card for a school from /data/s/<urn>.json. fallback ({urn, name}) is used when the document didn't load,
  // and for whichever identity fields a loaded document is missing.
  function schoolCardModel(s, ctx, fallback) {
    var f = obj(fallback);
    if (!s || typeof s !== "object") {
      var urn = f.urn != null ? String(f.urn) : null, name = f.name || "This school", path = urn ? schoolPath(urn, f.name || "") : null;
      return {
        kind: "school", title: name, status: null,
        lines: [{ label: "Figures", text: "This school's figures couldn't be loaded just now. Its page has them." }],
        spark: [], open: path ? { href: path, text: "Open the school page" } : null,
        links: urn ? [{ href: FBIT + urn, text: "DfE benchmarking tool (FBIT)" }] : [],
        pin: urn ? { type: "school", id: urn, name: name, p: path } : null
      };
    }
    var S = adaptSchool(s, f), c = obj(ctx), lines = [];
    lines.push({ label: "Status" + (S.year ? ", " + S.year : ""), text: S.status ? ICONS[S.status] + " " + S.label : "No published status for this school" });
    if (S.reason) lines.push({ label: "Why", text: S.reason });
    lines.push(moneyLine("Reserve per pupil", S.year, S.reservePp, S.reserve, true));
    lines.push(moneyLine("Income per pupil", S.year, S.incomePp, S.income, false));
    if (S.pupils != null) lines.push({ label: "Pupils" + (S.year ? ", " + S.year : ""), text: fmtNumber(S.pupils, 1) });
    lines.push({ label: "Source", text: (S.year ? S.year + ", " : "") + S.source });
    if (S.status === "in_deficit" || S.status === "heading_for_deficit" || mentionsDeficit(lines)) lines = lines.concat(explainLines(c, []));
    var links = [];
    if (S.urn) {
      links.push({ href: "/wrapped/?urn=" + encodeURIComponent(S.urn), text: "School Wrapped" });
      links.push({ href: FBIT + S.urn, text: "DfE benchmarking tool (FBIT)" });
    }
    return {
      kind: "school", title: S.name,
      status: S.status ? { key: S.status, icon: ICONS[S.status], label: S.label } : null,
      lines: lines, spark: [],
      open: S.path ? { href: S.path, text: "Open the school page" } : null,
      links: links,
      pin: S.urn ? { type: "school", id: S.urn, name: S.name, p: S.path || "" } : null
    };
  }

  // The table caption: "Share of schools in deficit, 2025-26, by council. England: 12.4%. Source: ...".
  function captionText(measure, year, englandValue, geo) {
    var M = obj(measure), ev = fmtValue(englandValue, M.unit || "gbp_pp", M.signed);
    return (M.label || "") + ", " + (year || "no year yet") + ", by " + (geo === "constituency" ? "constituency" : "council") +
      ". England: " + (ev || "not published") + ". Source: " + (M.source || "DfE returns") + ".";
  }

  // Rows of /data/map/schools.json as objects (one adapter for its key/rows layout).
  function schoolRows(doc) {
    var d = obj(doc), key = obj(d.key), fields = Array.isArray(key.fields) ? key.fields : ["urn", "lat", "lon", "status", "phase", "governance", "name"];
    var at = {};
    fields.forEach(function (f, i) { at[f] = i; });
    var st = Array.isArray(key.status) ? key.status : ORDER, ph = Array.isArray(key.phase) ? key.phase : [], gv = Array.isArray(key.governance) ? key.governance : [];
    return (Array.isArray(d.rows) ? d.rows : []).map(function (r) {
      if (!Array.isArray(r)) return null;
      var lat = r[at.lat], lon = r[at.lon], s = r[at.status];
      if (!isNum(lat) || !isNum(lon)) return null;
      return { urn: String(r[at.urn]), lat: lat, lon: lon, status: isNum(s) && s >= 0 && st[s] && ORDER.indexOf(st[s]) >= 0 ? st[s] : null,
        phase: ph[r[at.phase]] || "other", governance: gv[r[at.governance]] || "council-run", name: String(r[at.name] || "") };
    }).filter(Boolean);
  }
  function dotVisible(row, filters) {
    var f = obj(filters);
    if (f.phase && f.phase.indexOf(row.phase) < 0) return false;
    if (f.gov && f.gov.indexOf(row.governance) < 0) return false;
    if (f.status && f.status.indexOf(row.status || "none") < 0) return false;
    return true;
  }

  var API = {
    ORDER: ORDER, LABELS: LABELS, ICONS: ICONS, MEASURE_KEYS: MEASURE_KEYS,
    fmtExact: fmtExact, fmtValue: fmtValue, binsFor: binsFor, classify: classify, ramp: ramp, mix: mix,
    legendModel: legendModel, parseState: parseState, serialiseState: serialiseState, searchHits: searchHits,
    pickTarget: pickTarget, normName: normName, areaCardModel: areaCardModel, schoolCardModel: schoolCardModel,
    adaptArea: adaptArea, adaptSchool: adaptSchool, captionText: captionText, schoolRows: schoolRows, dotVisible: dotVisible
  };
  root.MoneyMap = API;
  if (typeof document === "undefined") return;

  // ======================================================================
  // DOM wiring
  // ======================================================================
  var host = document.getElementById("money-map");
  if (!host) return;
  var L = root.L;
  var ATTRIBUTION = '<a href="https://protomaps.com">Protomaps</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
  var ENGLAND = [[49.9, -6.4], [55.85, 1.8]];
  var DOT_ZOOM = 9;

  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $$(sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function media(q) { return root.matchMedia ? root.matchMedia(q) : { matches: false }; }
  function reduced() { return media("(prefers-reduced-motion: reduce)").matches; }
  function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function isDark() { return getComputedStyle(document.documentElement).colorScheme === "dark" || cssVar("color-scheme") === "dark"; }
  var paletteCache = null;
  function palette() {
    if (!paletteCache) {
      paletteCache = { accent: cssVar("--accent"), critical: cssVar("--critical"), plenty: cssVar("--plenty"), lineStrong: cssVar("--line-strong"),
        card: cssVar("--card"), line: cssVar("--line"), ink: cssVar("--ink"), ink3: cssVar("--ink-3") };
      ORDER.forEach(function (k) { paletteCache[k] = cssVar(STATUS_VARS[k]); });
    }
    return paletteCache;
  }
  var jsonCache = {};
  function fetchJSON(url) {
    if (!url || typeof fetch !== "function") return Promise.resolve(null);
    if (!jsonCache[url]) {
      jsonCache[url] = fetch(url).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; })
        .then(function (d) { if (d == null) delete jsonCache[url]; return d; });
    }
    return jsonCache[url];
  }
  function readContext() {
    var node = document.getElementById("mx-context");
    try { return obj(JSON.parse(node ? node.textContent : "{}")); } catch (e) { return {}; }
  }

  var ctx = readContext();
  var meta = obj(ctx.measures);
  var years = Array.isArray(ctx.years) ? ctx.years : (function () { try { return JSON.parse(host.getAttribute("data-years") || "[]"); } catch (e) { return []; } })();
  var opts = {
    measures: Object.keys(meta).length ? Object.keys(meta) : MEASURE_KEYS, years: years, meta: meta,
    defaults: { m: host.getAttribute("data-default-measure"), y: host.getAttribute("data-default-year"), g: "council" }
  };
  var dataUrls = obj(ctx.data);
  var state = parseState(root.location ? root.location.search : "", opts);
  var measuresDoc = null, measuresFailed = false, bins = null, colours = [];
  var map = null, baseLayer = null, geoLayer = null, geoLayerFor = null, layersById = {}, geoData = {}, geoPromises = {};
  var dotRenderer = null, dotLayer = null, schools = null, schoolIndex = {}, schoolsPromise = null, schoolsFailed = false;
  var selectedId = null, lastTrigger = null, cardFor = null;

  var els = {
    measure: $("#mx-measure"), year: $("#mx-year"), out: $("#mx-year-out"), q: $("#mx-q"), list: $("#mx-q-list"),
    legend: $("#mx-legend"), card: $("#mx-card"), tableH: $("#mx-table-h"), filters: $("#mx-controls")
  };
  function metaOf(key) { return Object.assign({ key: key }, obj(meta[key])); }
  function valueOf(entry, key, year) { return obj(obj(obj(entry).m)[key])[year]; }

  // ---------------------------------------------------------------- map
  function addBase() {
    if (!map || !root.protomapsL || !host.getAttribute("data-tiles")) return;
    if (baseLayer) map.removeLayer(baseLayer);
    baseLayer = root.protomapsL.leafletLayer({ url: host.getAttribute("data-tiles"), flavor: isDark() ? "dark" : "light", lang: "en",
      maxDataZoom: 15, attribution: ATTRIBUTION });
    baseLayer.addTo(map);
  }
  function initMap() {
    host.textContent = "";
    if (!L || typeof L.map !== "function") {
      host.classList.add("mx-off");
      host.appendChild(el("p", "mx-note", "The map couldn't load just now. The table below lists every council, with links to their pages."));
      return;
    }
    map = L.map(host, { zoomControl: true, zoomSnap: 0.5, minZoom: 6, maxZoom: 18, maxBounds: [[49.5, -9], [61, 2.2]] });
    map.fitBounds(ENGLAND);
    addBase();
    dotRenderer = L.canvas({ padding: 0.5 });
    dotLayer = L.layerGroup().addTo(map);
    map.on("moveend", drawDots);
  }
  function ensureHatch() {
    var svg = map && map.getPanes().overlayPane.querySelector("svg");
    if (!svg) return;
    var old = svg.querySelector("#mx-hatch");
    if (old) old.parentNode.removeChild(old);
    var NS = "http://www.w3.org/2000/svg", p = palette();
    var defs = svg.querySelector("defs") || svg.insertBefore(document.createElementNS(NS, "defs"), svg.firstChild);
    var pat = document.createElementNS(NS, "pattern");
    pat.setAttribute("id", "mx-hatch");
    pat.setAttribute("width", "6");
    pat.setAttribute("height", "6");
    pat.setAttribute("patternUnits", "userSpaceOnUse");
    pat.setAttribute("patternTransform", "rotate(45)");
    var bg = document.createElementNS(NS, "rect");
    bg.setAttribute("width", "6");
    bg.setAttribute("height", "6");
    bg.setAttribute("fill", p.card || "#ffffff");
    var line = document.createElementNS(NS, "line");
    line.setAttribute("x1", "0"); line.setAttribute("y1", "0"); line.setAttribute("x2", "0"); line.setAttribute("y2", "6");
    line.setAttribute("stroke", p.ink3 || "#888888");
    line.setAttribute("stroke-width", "2");
    pat.appendChild(bg);
    pat.appendChild(line);
    defs.appendChild(pat);
  }
  function styleFor(feature) {
    var id = obj(feature && feature.properties).id, entry = obj(obj(measuresDoc)[geoLayerFor])[id];
    var cls = classify(valueOf(entry, state.m, state.y), bins), p = palette(), on = id === selectedId;
    return { color: on ? p.ink : p.card, weight: on ? 3 : 0.7, opacity: 1, fillColor: cls == null ? "url(#mx-hatch)" : colours[cls],
      fillOpacity: cls == null ? 1 : 0.82 };
  }
  // g is the geography the layer was drawn for: it can differ from state.g while a new geography downloads.
  // A boundary with no measures entry still gets its own name and a no-data line.
  function areaTip(g, id, name) {
    var entry = obj(obj(obj(measuresDoc)[g])[id]), m = metaOf(state.m), box = el("div", "mx-tip");
    var missing = measuresFailed ? "Figures couldn't be loaded just now." : (measuresDoc ? NOT_PUBLISHED : "Loading figures…");
    box.appendChild(el("strong", null, entry.name || name || ""));
    box.appendChild(el("span", null, fmtValue(valueOf(entry, state.m, state.y), m.unit, m.signed) || missing));
    return box;
  }
  function drawGeo(g, data) {
    if (!map) return;
    if (!data) {
      legendNote((g === "council" ? "Council" : "Constituency") + " boundaries couldn't be loaded, so the map can't show them. The table below lists every " + g + ".");
      if (geoLayer) { map.removeLayer(geoLayer); geoLayer = null; geoLayerFor = null; }
      return;
    }
    if (geoLayerFor !== g) {
      if (geoLayer) map.removeLayer(geoLayer);
      layersById = {};
      geoLayerFor = g;
      geoLayer = L.geoJSON(data, {
        style: styleFor,
        onEachFeature: function (feature, layer) {
          var props = obj(feature.properties), id = props.id;
          layersById[id] = layer;
          layer.bindTooltip(function () { return areaTip(g, id, props.name); }, { sticky: true });
          layer.on("mouseover", function () { layer.setStyle({ weight: 2.5, color: palette().ink }); });
          layer.on("mouseout", function () { geoLayer.resetStyle(layer); });
          layer.on("click", function () { openArea(id, map.getContainer()); });
        }
      }).addTo(map);
      if (dotLayer) dotLayer.eachLayer(function (d) { if (d.bringToFront) d.bringToFront(); });
    } else {
      geoLayer.setStyle(styleFor);
    }
    ensureHatch();
  }
  function loadGeo(g) {
    var url = dataUrls[g];
    if (!url) return Promise.resolve(null);
    if (!geoPromises[g]) {
      geoPromises[g] = fetchJSON(url).then(function (d) {
        d = d && Array.isArray(d.features) ? d : null;
        if (d) geoData[g] = d; else delete geoPromises[g];
        return d;
      });
    }
    return geoPromises[g];
  }

  // ---------------------------------------------------------------- school dots
  function filters() {
    function checked(name) { return $$('input[name="' + name + '"]', els.filters).filter(function (i) { return i.checked; }).map(function (i) { return i.value; }); }
    return { phase: checked("phase"), gov: checked("gov"), status: checked("status") };
  }
  function loadSchools() {
    if (!schoolsPromise) {
      schoolsPromise = fetchJSON(dataUrls.schools).then(function (d) {
        var rows = d ? schoolRows(d) : [];
        if (!d) { schoolsPromise = null; schoolsFailed = true; return null; }
        schoolsFailed = false;
        schools = rows;
        rows.forEach(function (r) { schoolIndex[r.urn] = r; });
        return rows;
      });
    }
    return schoolsPromise;
  }
  function schoolTip(row) {
    var box = el("div", "mx-tip");
    box.appendChild(el("strong", null, row.name));
    box.appendChild(el("span", null, row.status ? ICONS[row.status] + " " + LABELS[row.status] : "No published status"));
    return box;
  }
  function drawDots() {
    if (!map || !dotLayer) return;
    renderDotKey();
    if (map.getZoom() < DOT_ZOOM) { dotLayer.clearLayers(); return; }
    loadSchools().then(function (rows) {
      renderDotKey();
      dotLayer.clearLayers();
      if (!rows || map.getZoom() < DOT_ZOOM) return;
      var view = map.getBounds().pad(0.15), f = filters(), p = palette(), r = map.getZoom() >= 12 ? 6.5 : 4.5;
      rows.forEach(function (row) {
        if (!dotVisible(row, f) || !view.contains([row.lat, row.lon])) return;
        var none = !row.status;
        L.circleMarker([row.lat, row.lon], { renderer: dotRenderer, radius: r, weight: none ? 1.5 : 1, color: none ? p.ink3 : p.card,
          fillColor: none ? p.card : p[row.status], fillOpacity: none ? 0.6 : 0.95 })
          .bindTooltip(function () { return schoolTip(row); })
          .on("click", function () { openSchool(row.urn, row, map.getContainer()); })
          .addTo(dotLayer);
      });
    });
  }

  // ---------------------------------------------------------------- legend
  function legendNote(text) {
    var old = $(".mx-legend-note", els.legend);
    if (old) old.textContent = text;
    else if (els.legend) els.legend.insertBefore(el("p", "mx-legend-note mx-note", text), els.legend.firstChild);
  }
  function swatch(colour, cls) {
    var s = el("span", "mx-sw" + (cls ? " " + cls : ""));
    s.setAttribute("aria-hidden", "true");
    if (colour) s.style.background = colour;
    return s;
  }
  function renderDotKey() {
    var box = $(".mx-dotkey", els.legend);
    if (!box) return;
    var zoomed = map && map.getZoom() >= DOT_ZOOM;
    var head = $(".mx-dothead", box);
    head.textContent = schoolsFailed ? "School dots couldn't be loaded just now." :
      (zoomed ? "Schools, by budget status" : "Schools, by budget status (zoom in to town level to see them)");
  }
  function renderLegend() {
    if (!els.legend) return;
    els.legend.textContent = "";
    if (measuresFailed) {
      els.legend.appendChild(el("p", "mx-legend-note mx-note", "Map figures couldn't be loaded just now. The table below lists every council with its own figures."));
      return;
    }
    if (!measuresDoc) { els.legend.appendChild(el("p", "small muted", "Loading the map key…")); return; }
    var m = metaOf(state.m), ev = obj(obj(measuresDoc.england)[state.m])[state.y], model = legendModel(bins, m, ev);
    els.legend.appendChild(el("p", "mx-legend-title", m.label + ", " + (state.y || "no year yet")));
    if (model.empty) els.legend.appendChild(el("p", "small muted", model.empty));
    var ul = el("ul", "mx-key");
    model.items.forEach(function (it) {
      var li = el("li");
      li.appendChild(swatch(colours[it.cls]));
      li.appendChild(el("span", null, it.label));
      if (model.england && model.england.cls === it.cls) li.appendChild(el("span", "mx-eng", "◀ " + model.england.text));
      ul.appendChild(li);
    });
    var none = el("li");
    none.appendChild(swatch(null, "mx-sw-none"));
    none.appendChild(el("span", null, model.missing.label));
    ul.appendChild(none);
    els.legend.appendChild(ul);
    if (model.england && model.england.cls == null) els.legend.appendChild(el("p", "small", model.england.text));
    var notes = ["Source: " + (state.y ? state.y + ", " : "") + (m.source || "DfE returns") + "."];
    if (m.unit === "gbp_pp") notes.push(ctx.cash_note || "");
    if (state.m === "pta_median_pp" && ctx.pta_note) notes.push(ctx.pta_note);
    if (state.m === "dsg_pp" && ctx.dsg_note) notes.push(ctx.dsg_note);
    els.legend.appendChild(el("p", "small muted", notes.join(" ").trim()));
    var dots = el("div", "mx-dotkey");
    dots.appendChild(el("p", "mx-dothead small"));
    var dl = el("ul", "mx-key mx-key-dots");
    ORDER.concat(["none"]).forEach(function (k) {
      var li = el("li");
      li.appendChild(swatch(k === "none" ? null : palette()[k], "mx-dot" + (k === "none" ? " mx-dot-none" : "")));
      if (k !== "none") { var i = el("span", "mx-icon", ICONS[k]); i.setAttribute("aria-hidden", "true"); li.appendChild(i); }
      li.appendChild(el("span", null, k === "none" ? "No published status" : LABELS[k]));
      dl.appendChild(li);
    });
    dots.appendChild(dl);
    els.legend.appendChild(dots);
    renderDotKey();
  }

  // ---------------------------------------------------------------- table (the keyboard and no-map path)
  function ensureTable() {
    var t = $("#mx-table");
    if (t) return t;
    var box = $(".mx-tablebox");
    if (!box) return null;
    var empty = $("#mx-table-empty");
    if (empty) empty.parentNode.removeChild(empty);
    var scroller = el("div", "mx-scroll");
    t = el("table");
    t.id = "mx-table";
    t.setAttribute("data-sortable", "");
    t.appendChild(el("caption"));
    var head = el("thead"), tr = el("tr");
    ["Council", ""].forEach(function (h) { var th = el("th", null, h); th.setAttribute("scope", "col"); tr.appendChild(th); });
    head.appendChild(tr);
    t.appendChild(head);
    t.appendChild(el("tbody"));
    scroller.appendChild(t);
    box.appendChild(scroller);
    return t;
  }
  function renderTable() {
    if (!measuresDoc) return;
    var t = ensureTable();
    if (!t) return;
    var g = state.g, m = metaOf(state.m), entries = obj(measuresDoc[g]);
    var ev = obj(obj(measuresDoc.england)[state.m])[state.y];
    t.setAttribute("data-level", g);
    if (els.tableH) els.tableH.textContent = g === "council" ? "Every council" : "Every constituency";
    var cap = t.querySelector("caption") || t.insertBefore(el("caption"), t.firstChild);
    cap.textContent = captionText(m, state.y, ev, g);
    var ths = $$("thead th", t);
    if (ths[0]) ths[0].textContent = g === "council" ? "Council" : "Constituency";
    if (ths[1]) ths[1].textContent = m.label + ", " + (state.y || "no year yet");
    ths.forEach(function (th) { th.removeAttribute("aria-sort"); });
    var body = t.tBodies[0] || t.appendChild(el("tbody"));
    var frag = document.createDocumentFragment();
    Object.keys(entries).sort(function (a, b) { return String(entries[a].name).localeCompare(String(entries[b].name)); }).forEach(function (id) {
      var e = entries[id], v = valueOf(e, state.m, state.y), tr = el("tr");
      tr.setAttribute("data-id", id);
      var th = el("th");
      th.setAttribute("scope", "row");
      if (e.p) { var a = el("a", null, e.name); a.href = e.p; th.appendChild(a); } else th.appendChild(document.createTextNode(e.name));
      if (map && dataUrls[g]) {
        var b = el("button", "mx-show", "Show on map");
        b.type = "button";
        b.setAttribute("data-show", id);
        b.setAttribute("aria-label", "Show " + e.name + " on the map");
        th.appendChild(b);
      }
      tr.appendChild(th);
      var td = el("td", isNum(v) ? null : "muted", fmtValue(v, m.unit, m.signed) || "Not published");
      if (isNum(v)) td.setAttribute("data-sort", String(v));
      tr.appendChild(td);
      frag.appendChild(tr);
    });
    body.textContent = "";
    body.appendChild(frag);
  }

  // ---------------------------------------------------------------- card (dialog; a bottom sheet at 600px or less)
  function sparkline(model) {
    var pts = (model.spark || []).filter(function (p) { return p && isNum(p.v); });
    if (pts.length < 2) return null;
    var NS = "http://www.w3.org/2000/svg", W = 240, H = 56, P = 6;
    var vals = pts.map(function (p) { return p.v; }), lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    if (lo === hi) { lo -= 1; hi += 1; }
    var svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("class", "chart mx-spark");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", (model.sparkLabel || "Trend") + ": " + pts.map(function (p) {
      return p.y + " " + fmtValue(p.v, model.sparkUnit, model.sparkSigned);
    }).join(", "));
    var path = document.createElementNS(NS, "path");
    path.setAttribute("class", "line s1");
    path.setAttribute("d", "M" + pts.map(function (p, i) {
      return (P + i * (W - 2 * P) / (pts.length - 1)).toFixed(1) + "," + (P + (hi - p.v) / (hi - lo) * (H - 2 * P)).toFixed(1);
    }).join("L"));
    svg.appendChild(path);
    return svg;
  }
  function pinned(pin) {
    try {
      var list = JSON.parse(localStorage.getItem("moneyPinned") || "[]");
      return Array.isArray(list) && list.some(function (p) { return p && p.type === pin.type && String(p.id) === String(pin.id); });
    } catch (e) { return false; }
  }
  function pinButton(pin) {
    var b = el("button", "pin");
    b.type = "button";
    b.setAttribute("data-pin", JSON.stringify(pin));
    b.setAttribute("aria-pressed", pinned(pin) ? "true" : "false");
    var i = el("span", null, "📌");
    i.setAttribute("aria-hidden", "true");
    b.appendChild(i);
    b.appendChild(document.createTextNode(" Pin"));
    return b;
  }
  function renderCard(model) {
    var body = $(".mx-card-body", els.card);
    body.textContent = "";
    var h = el("h2", "mx-card-title", model.title);
    h.id = "mx-card-title";
    h.tabIndex = -1;
    body.appendChild(h);
    if (model.status) {
      var badge = el("span", "badge small s-" + model.status.key), icon = el("span", null, model.status.icon);
      icon.setAttribute("aria-hidden", "true");
      badge.appendChild(icon);
      badge.appendChild(document.createTextNode(" " + model.status.label));
      body.appendChild(badge);
    }
    var dl = el("dl", "mx-lines"), why = [];
    model.lines.forEach(function (l) {
      if (l.kind) { why.push(l); return; }
      dl.appendChild(el("dt", null, l.label));
      dl.appendChild(el("dd", null, l.text));
    });
    body.appendChild(dl);
    var spark = sparkline(model);
    if (spark) {
      var pts = model.spark.filter(function (p) { return p && isNum(p.v); }), a = pts[0], z = pts[pts.length - 1];
      body.appendChild(spark);
      body.appendChild(el("p", "mx-spark-cap small muted", "Trend: " + a.y + " " + fmtValue(a.v, model.sparkUnit, model.sparkSigned) +
        ", " + z.y + " " + fmtValue(z.v, model.sparkUnit, model.sparkSigned)));
    }
    if (why.length) {
      var det = el("details", "mx-why-card");
      det.appendChild(el("summary", null, why[0].label + " and what helps"));
      why.forEach(function (l) {
        var p = el("p");
        p.appendChild(el("strong", null, l.label + ": "));
        p.appendChild(document.createTextNode(l.text));
        det.appendChild(p);
      });
      if (ctx.helps_link) { var more = el("a", null, "Questions to ask"); more.href = ctx.helps_link; det.appendChild(more); }
      body.appendChild(det);
    }
    var actions = el("div", "mx-actions");
    if (model.open) { var a = el("a", "mx-open", model.open.text); a.href = model.open.href; actions.appendChild(a); }
    (model.links || []).forEach(function (l) { var x = el("a", "mx-link", l.text); x.href = l.href; if (/^https?:/.test(l.href)) x.rel = "noopener"; actions.appendChild(x); });
    if (model.pin) actions.appendChild(pinButton(model.pin));
    body.appendChild(actions);
  }
  function openCard(model, key, trigger) {
    if (els.card.hidden) lastTrigger = trigger || document.activeElement;
    cardFor = key;
    renderCard(model);
    els.card.hidden = false;
    var h = $("#mx-card-title", els.card);
    if (h) h.focus({ preventScroll: true });
  }
  function refreshCard(model, key) {
    if (els.card.hidden || cardFor !== key) return;
    var had = els.card.contains(document.activeElement);
    renderCard(model);
    if (had) { var h = $("#mx-card-title", els.card); if (h) h.focus({ preventScroll: true }); }
  }
  function closeCard() {
    if (els.card.hidden) return;
    els.card.hidden = true;
    cardFor = null;
    select(null);
    var t = lastTrigger;
    lastTrigger = null;
    if (t && t.focus && document.contains(t)) t.focus();
  }
  function select(id) {
    var prev = selectedId;
    selectedId = id;
    [prev, id].forEach(function (k) { var layer = k && layersById[k]; if (layer && geoLayer) { geoLayer.resetStyle(layer); if (k === id && layer.bringToFront) layer.bringToFront(); } });
  }
  function areaEntry(id) {
    var g = id && id.indexOf("constituency-") === 0 ? "constituency" : "council";
    return Object.assign({ id: id }, obj(obj(measuresDoc)[g])[id]);
  }
  var areaDocs = {};
  // The card for an area at the current measure and year, so render() can bring an open card up to date.
  function areaModel(id) {
    var entry = areaEntry(id);
    if (!measuresDoc) {
      var text = measuresFailed ? "Figures for this area couldn't be loaded just now." : "Loading this area's figures…";
      return { kind: "area", title: entry.name || "This area", lines: [{ label: "Figures", text: text }],
        spark: [], open: entry.p ? { href: entry.p, text: "Open its page" } : null, links: [], pin: null };
    }
    return areaCardModel(entry, metaOf(state.m), state.y, measuresDoc.england, areaDocs[id] || null, ctx);
  }
  function refreshAreaCard() {
    if (cardFor && cardFor.indexOf("area:") === 0) refreshCard(areaModel(cardFor.slice(5)), cardFor);
  }
  function openArea(id, trigger) {
    if (!id) return;
    select(id);
    var key = "area:" + id;
    openCard(areaModel(id), key, trigger);
    if (areaDocs[id]) return;
    fetchJSON("/data/a/" + encodeURIComponent(id) + ".json").then(function (doc) {
      if (!doc) return;
      areaDocs[id] = doc;
      refreshCard(areaModel(id), key);
    });
  }
  function openSchool(urn, row, trigger) {
    var key = "school:" + urn;
    select(null);
    openCard({ kind: "school", title: (row && row.name) || "School " + urn, lines: [{ label: "Figures", text: "Loading this school's figures…" }],
      spark: [], open: null, links: [], pin: null }, key, trigger);
    fetchJSON("/data/s/" + encodeURIComponent(urn) + ".json").then(function (doc) {
      refreshCard(schoolCardModel(doc && typeof doc === "object" ? doc : null, ctx, { urn: urn, name: row && row.name }), key);
    });
  }
  function focusArea(id, trigger) {
    var g = id.indexOf("constituency-") === 0 ? "constituency" : "council";
    if (state.g !== g) { setGeo(g); render(); }
    var show = function () {
      var layer = layersById[id];
      if (map && layer && layer.getBounds) map.fitBounds(layer.getBounds(), { maxZoom: 11, animate: !reduced() });
      openArea(id, trigger);
    };
    if (map) loadGeo(g).then(function (d) { drawGeo(g, d); show(); }); else show();
  }

  // ---------------------------------------------------------------- search combobox
  var searchIndex = null;
  function loadIndex() {
    if (!searchIndex) searchIndex = fetchJSON("/data/search.json").then(function (d) { if (!Array.isArray(d)) searchIndex = null; return Array.isArray(d) ? d : []; });
    return searchIndex;
  }
  // Typed or chosen search text goes into the URL too, so a shared or reloaded link restores what is in the box.
  function setQuery(q) {
    q = cleanQuery(q);
    if (q === state.q) return;
    state.q = q;
    updateURL();
  }
  function choose(row) {
    if (!row) return;
    setQuery(row.name);
    if (row.t === "school") {
      loadSchools().then(function () {
        var r = schoolIndex[String(row.id)];
        if (map && r) { if (reduced()) map.setView([r.lat, r.lon], 14); else map.flyTo([r.lat, r.lon], 14); }
        openSchool(String(row.id), r || { name: row.name }, els.q);
      });
      return;
    }
    var g = row.t;
    var go = function (d) {
      var t = pickTarget(row, d ? d.features : []);
      if (t) focusArea(t.id, els.q);
    };
    if (map && dataUrls[g]) loadGeo(g).then(go); else go(null);
  }
  (function search() {
    var input = els.q, list = els.list;
    if (!input || !list) return;
    var options = [], rows = [], active = -1, timer = null, last = "";
    function hide() { list.hidden = true; list.textContent = ""; options = []; active = -1; input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); }
    function setActive(i) {
      active = i;
      options.forEach(function (o, k) { o.setAttribute("aria-selected", k === i ? "true" : "false"); });
      if (i >= 0) { input.setAttribute("aria-activedescendant", options[i].id); options[i].scrollIntoView({ block: "nearest" }); }
      else input.removeAttribute("aria-activedescendant");
    }
    function render(hits, note) {
      list.textContent = "";
      options = [];
      rows = hits;
      if (!hits.length) { if (note) list.appendChild(el("li", "empty", note)); else { hide(); return; } }
      hits.forEach(function (r, i) {
        var li = el("li");
        li.id = "mx-q-opt-" + i;
        li.setAttribute("role", "option");
        li.setAttribute("aria-selected", "false");
        li.appendChild(el("span", "kind", r.t || ""));
        li.appendChild(el("span", "name", r.name || ""));
        if (r.sub) li.appendChild(el("span", "sub", r.sub));
        li.addEventListener("mousedown", function (e) { e.preventDefault(); });
        li.addEventListener("click", function () { hide(); input.value = r.name || ""; choose(r); });
        list.appendChild(li);
        options.push(li);
      });
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
      setActive(-1);
    }
    function run() {
      var q = input.value.trim();
      last = q;
      setQuery(q);
      if (q.length < 2) { hide(); return; }
      loadIndex().then(function (all) {
        if (last !== q) return;
        render(searchHits(all, q, 8), all.length ? "No matching school or area" : "Search isn't available just now.");
      });
    }
    input.addEventListener("focus", function () { loadIndex(); });
    input.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(run, 80); });
    input.addEventListener("keydown", function (e) {
      if (list.hidden && e.key === "ArrowDown" && input.value.trim()) { run(); return; }
      if (list.hidden) return;
      if (e.key === "ArrowDown") { e.preventDefault(); setActive(options.length ? (active + 1) % options.length : -1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); setActive(options.length ? (active - 1 + options.length) % options.length : -1); }
      else if (e.key === "Enter") { e.preventDefault(); var i = active >= 0 ? active : (options.length ? 0 : -1); if (i >= 0) options[i].click(); }
      else if (e.key === "Escape") { e.stopPropagation(); hide(); }
    });
    input.addEventListener("blur", function () { setTimeout(hide, 120); });
    if (state.q) {
      input.value = state.q;
      loadIndex().then(function (all) { var hit = searchHits(all, state.q, 1)[0]; if (hit) choose(hit); });
    }
  })();

  // ---------------------------------------------------------------- controls and state
  function updateURL() {
    if (!root.history || !root.history.replaceState || !root.location) return;
    root.history.replaceState(null, "", root.location.pathname + serialiseState(state, opts) + root.location.hash);
  }
  function syncControls() {
    if (els.measure) {
      els.measure.value = state.m;
      Array.prototype.forEach.call(els.measure.options, function (o) {
        var lv = obj(meta[o.value]).levels;
        o.disabled = Array.isArray(lv) && lv.indexOf(state.g) < 0;
      });
    }
    var i = years.indexOf(state.y);
    if (els.year && i >= 0) { els.year.value = String(i); els.year.setAttribute("aria-valuetext", state.y); }
    if (els.out) els.out.textContent = state.y || "No year yet";
    $$('input[name="g"]', els.filters).forEach(function (r) { r.checked = r.value === state.g; });
  }
  // Every geography change goes through here, so a measure the geography lacks (DSG for constituencies)
  // falls back to the default whether the change came from the radios or from search.
  function setGeo(g) {
    state.g = g === "constituency" ? "constituency" : "council";
    if (!measureFits(stateOptions(opts), state.m, state.g)) state.m = stateOptions(opts).defaults.m;
  }
  function render() {
    syncControls();
    updateURL();
    if (measuresDoc) {
      var m = metaOf(state.m), entries = obj(measuresDoc[state.g]);
      bins = binsFor(Object.keys(entries).map(function (id) { return valueOf(entries[id], state.m, state.y); }), { scale: m.scale, n: 5, unit: m.unit });
      colours = ramp(m.scale, palette(), bins.classes.length);
      renderTable();
    }
    renderLegend();
    refreshAreaCard();
    if (map && measuresDoc) {
      var g = state.g;
      loadGeo(g).then(function (d) { if (state.g === g) drawGeo(g, d); });
    }
  }
  if (els.filters) {
    els.filters.addEventListener("change", function (e) {
      var t = e.target;
      if (t === els.measure) state.m = t.value;
      else if (t.name === "g") {
        setGeo(t.value);
        closeCard();
      } else if (t.name === "phase" || t.name === "gov" || t.name === "status") { drawDots(); return; }
      else return;
      render();
    });
  }
  if (els.year) {
    els.year.addEventListener("input", function () {
      var y = years[parseInt(els.year.value, 10)];
      if (y && y !== state.y) { state.y = y; render(); }
    });
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-show]");
    if (b) { e.preventDefault(); host.scrollIntoView({ block: "nearest", behavior: reduced() ? "auto" : "smooth" }); focusArea(b.getAttribute("data-show"), b); }
  });
  if (els.card) {
    $(".mx-close", els.card).addEventListener("click", closeCard);
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !els.card.hidden) closeCard(); });
  }
  var scheme = media("(prefers-color-scheme: dark)");
  if (scheme.addEventListener) scheme.addEventListener("change", function () { paletteCache = null; addBase(); render(); drawDots(); });

  initMap();
  renderLegend();
  fetchJSON(dataUrls.measures || "/data/map/measures.json").then(function (d) {
    if (!d || typeof d !== "object" || !d.council) { measuresFailed = true; renderLegend(); refreshAreaCard(); return; }
    measuresDoc = d;
    render();
    drawDots();
  });
})(typeof globalThis !== "undefined" ? globalThis : this);
