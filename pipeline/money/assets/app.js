/* School Money — app.js. Defer-loaded; every page works without it.
   Pure helpers are exported as globalThis.MoneyApp (loadable under node for tests); DOM wiring
   runs only in a browser. All data goes through textContent: no HTML built from strings of data.

   Reads: /assets/glossary.json, /data/search.json, /data/s/<urn>.json, /data/sx/<urn>.json (a school's
          SERIES, for data-drill="/data/sx/<urn>.json#m:<metric>"), /data/a/<id>.json,
          /data/postcodes/<district>.json (a 404 = no suggestions; deploy/money/check_site.py requires them).
          A full postcode goes to api.postcodes.io only when Search is pressed (/search/), never while typing.
   Search: forgiving (searchMatches): typos, apostrophes, St/Saint, & / and, a URN or council code, "schools in
          Hackney"; a failed index request is retried on the next search.
   Tables: table[data-sortable] sorts by column (header buttons, plus a Sort by select for phones); a preceding
          .table-filters[data-filters] filters rows by their [data-tags] (group:value slugs); rows of pinned
          schools move to the top on load.
   Menu: button.menu-toggle (site.MENU_BUTTON) opens and closes the nav on a phone.
   Stores: localStorage moneyAudience ("parent"|... or null once cleared), moneyPinned ([{type,id,name,p}]).
   Imports: Schools in Reach's localStorage "shortlist" and "plan" (arrays of URNs). */
(function (root) {
  "use strict";

  // ======================================================================
  // Pure helpers (no DOM)
  // ======================================================================
  function fmtMoney(v, signed) {
    if (v == null || typeof v !== "number" || !isFinite(v)) return "—";
    var sign = v < 0 ? "-" : (signed && v > 0 ? "+" : ""), a = Math.abs(v);
    if (a >= 1e9) return sign + "£" + (a / 1e9).toFixed(2) + "bn";
    if (a >= 1e6) return sign + "£" + (a / 1e6).toFixed(1) + "m";
    if (a >= 1e3) return sign + "£" + Math.round(a / 1e3) + "k";
    return sign + "£" + Math.round(a).toLocaleString("en-GB");
  }
  function fmtExact(v, signed) {
    if (v == null || typeof v !== "number" || !isFinite(v)) return "—";
    var sign = v < 0 ? "-" : (signed && v > 0 ? "+" : "");
    return sign + "£" + Math.round(Math.abs(v)).toLocaleString("en-GB");
  }
  // Units: "money" (the default), "pct" (a share, one decimal) or "n" (a count). Taken from an explicit
  // data-unit, then a glossary key ending in _pct, then a % sign in the figure's own text.
  function unitOf(key, explicit, text) {
    if (explicit === "pct" || explicit === "n" || explicit === "money") return explicit;
    if (/_pct$/.test(key || "")) return "pct";
    var t = String(text == null ? "" : text);
    if (t.indexOf("%") !== -1 && t.indexOf("£") === -1) return "pct";
    return "money";
  }
  function fmtUnit(v, unit, signed, exact) {
    if (unit === "pct" || unit === "n") {
      if (v == null || typeof v !== "number" || !isFinite(v)) return "—";
      var sign = v < 0 ? "-" : (signed && v > 0 ? "+" : ""), a = Math.abs(v);
      if (unit === "n") return sign + Math.round(a).toLocaleString("en-GB");
      return sign + (a >= 100 ? String(Math.round(a)) : String(+a.toFixed(1))) + "%";
    }
    return exact ? fmtExact(v, signed) : fmtMoney(v, signed);
  }
  function perPupil(v, pupils) {
    if (v == null || typeof v !== "number" || !isFinite(v)) return null;
    if (typeof pupils !== "number" || !isFinite(pupils) || pupils <= 0) return null;
    return Math.round(v / pupils);
  }
  // UK postcode: outward district (A9, A99, AA9, AA99, A9A, AA9A), optional inward (9AA).
  var POSTCODE = /^([A-Z]{1,2}\d[A-Z\d]?)(?: ?(\d[A-Z]{2}))?$/;
  function parsePostcode(q) {
    var s = String(q == null ? "" : q).trim().toUpperCase().replace(/\s+/g, " ");
    var m = POSTCODE.exec(s);
    if (!m) return null;
    return { district: m[1], inward: m[2] || null, full: m[2] ? m[1] + " " + m[2] : null };
  }
  var TYPE_ORDER = { school: 0, council: 1, constituency: 2, trust: 3 };
  function norm(s) {
    return String(s == null ? "" : s).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  }
  // Search text, forgiving: case, accents, apostrophes and punctuation are ignored, "&" reads as "and", "C of E" as
  // "CofE", and "St" / "St." and "Saint" match each other. Each row is folded once (cached per row object), so a
  // keystroke over the 27,000-entry index compares prepared strings only.
  var ALIASES = { st: "saint", saint: "st" };
  function fold(s) {
    return norm(s).replace(/['’‘`]/g, "").replace(/&/g, " and ").replace(/[^a-z0-9]+/g, " ").trim().replace(/\bc of e\b/g, "cofe");
  }
  function withAliases(list) {
    var out = list.slice();
    list.forEach(function (t) { if (ALIASES[t]) out.push(ALIASES[t]); });
    return out;
  }
  function canonical(list) { return list.map(function (t) { return t === "st" ? "saint" : t; }).join(" "); }
  var folded = typeof WeakMap === "function" ? new WeakMap() : null;
  function prepRow(r) {
    var p = folded && folded.get(r);
    if (p) return p;
    var name = fold(r.name), sub = fold(r.sub), nt = name ? name.split(" ") : [], st = sub ? sub.split(" ") : [];
    p = { name: name, canon: canonical(nt), full: sub ? name + " " + sub : name, nt: withAliases(nt), st: withAliases(st) };
    if (folded) folded.set(r, p);
    return p;
  }
  // Optimal string alignment distance (insertions, deletions, substitutions and swapped neighbours), or max + 1 as soon
  // as it must be more than max.
  function editDistance(a, b, max) {
    if (a === b) return 0;
    var n = a.length, m = b.length, i, j;
    if (Math.abs(n - m) > max) return max + 1;
    var before = null, prev = [], cur;
    for (j = 0; j <= m; j++) prev[j] = j;
    for (i = 1; i <= n; i++) {
      cur = [i];
      var low = i;
      for (j = 1; j <= m; j++) {
        var v = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a.charCodeAt(i - 1) === b.charCodeAt(j - 1) ? 0 : 1));
        if (before && j > 1 && a.charCodeAt(i - 1) === b.charCodeAt(j - 2) && a.charCodeAt(i - 2) === b.charCodeAt(j - 1)) v = Math.min(v, before[j - 2] + 1);
        cur[j] = v;
        if (v < low) low = v;
      }
      if (low > max) return max + 1;
      before = prev;
      prev = cur;
    }
    return prev[m] > max ? max + 1 : prev[m];
  }
  // Typos allowed in a word: none in three letters or fewer, one in four to six, two from seven.
  function typos(w) { return w.length >= 7 ? 2 : w.length >= 4 ? 1 : 0; }
  // Words that say "an area" rather than name one: "schools in Hackney", "Hackney council", "London Borough of Hackney".
  var AREA_WORDS = { schools: 1, school: 1, in: 1, near: 1, around: 1, council: 1, borough: 1, county: 1, of: 1, the: 1, area: 1,
                     local: 1, authority: 1, london: 1, constituency: 1, primary: 1, secondary: 1 };
  var tokenLists = typeof WeakMap === "function" ? new WeakMap() : null;
  // Every distinct name and place word in pool (the rows of the given types), kept per rows array and types.
  function tokenList(rows, key, pool) {
    var byKey = tokenLists && tokenLists.get(rows);
    if (byKey && byKey[key]) return byKey[key];
    var seen = Object.create(null), list = [];
    pool.forEach(function (r) {
      var p = prepRow(r);
      p.nt.concat(p.st).forEach(function (t) { if (t && !seen[t]) { seen[t] = 1; list.push(t); } });
    });
    if (tokenLists) { byKey = byKey || {}; byKey[key] = list; tokenLists.set(rows, byKey); }
    return list;
  }
  // {token: typos} for the index words within a query word's allowance; the last word may still be being typed, so
  // it also matches the start of a longer word. At most 60 per word, closest first.
  function closeWords(w, list, last) {
    var k = typos(w), found = [];
    if (!k) return null;
    for (var i = 0; i < list.length; i++) {
      var t = list[i], d = editDistance(w, t, k);
      if (last && t.length > w.length && d > 0) d = Math.min(d, editDistance(w, t.slice(0, w.length), k));
      if (d <= k) found.push([t, d]);
    }
    found.sort(function (a, b) { return a[1] - b[1]; });
    var out = Object.create(null);
    found.slice(0, 60).forEach(function (f) { out[f[0]] = f[1]; });
    return out;
  }
  function typeRank(r) { return TYPE_ORDER[r.t] == null ? 9 : TYPE_ORDER[r.t]; }
  // Does some word in toks start with w?
  function starts(w, toks) {
    for (var i = 0; i < toks.length; i++) if (toks[i].indexOf(w) === 0) return true;
    return false;
  }
  function allStart(ws, toks) {
    for (var i = 0; i < ws.length; i++) if (!starts(ws[i], toks)) return false;
    return true;
  }
  // Search rows (the /data/search.json shape) for q: {rows, fuzzy, urn}. Best first:
  //   a URN or council code typed as digits (urn: true); the name exactly; the name's start; every word starting a word
  //   of the name; an area typed with "schools in" / "council" around it; every word starting a word of the name or
  //   its place, at least one in the name; the text anywhere in name or place.
  // Only when nothing matches like that: names within a typo or two of every word (fuzzy: true, closest first).
  // Ties: school, council, constituency, trust; then the shorter name; then index order. opts.types keeps those types.
  function searchMatches(rows, q, limit, opts) {
    limit = limit || 8;
    var types = opts && Array.isArray(opts.types) ? opts.types : null;
    var needle = fold(q), out = { rows: [], fuzzy: false, urn: false };
    if (!needle || !Array.isArray(rows)) return out;
    var words = needle.split(" "), canon = canonical(words), digits = /^\d{3,8}$/.test(needle) ? needle : null;
    var core = words.filter(function (w) { return !AREA_WORDS[w]; }), areaWords = core.length && core.length < words.length ? core : null;
    var areaCanon = areaWords ? canonical(areaWords) : null;
    var hits = [], pool = [];
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      if (!r || !r.name || (types && types.indexOf(r.t) === -1)) continue;
      pool.push(r);
      var p = prepRow(r), score = 0;
      if (digits && String(r.id) === digits && (r.t === "school" || r.t === "council")) score = 9;
      else if (p.name === needle || p.canon === canon) score = 6;
      else if (p.name.indexOf(needle) === 0 || p.canon.indexOf(canon) === 0) score = 5;
      else if (allStart(words, p.nt)) score = 4;
      else if (areaWords && (r.t === "council" || r.t === "constituency") && allStart(areaWords, p.nt)) score = areaCanon === p.canon ? 5.5 : 3.5;
      else if (placed(words, p)) score = 2;
      else if (p.full.indexOf(needle) !== -1) score = 1;
      if (score) hits.push({ row: r, score: score, i: i, len: p.name.length });
    }
    if (hits.some(function (h) { return h.score === 9; })) out.urn = true;
    if (!hits.length && !digits) {
      // Fuzzy: each word to the index words within its typo allowance, then rows where every word lands on the name or
      // place and at least one on the name. The cost is the typos used; an exact word costs nothing. As above, a council
      // or constituency needs only the words that aren't area words ("Hakney council" is Hackney's).
      var list = tokenList(rows, types ? types.join() : "", pool), near = words.map(function (w, n) { return closeWords(w, list, n === words.length - 1); });
      var all = words.map(function (w, n) { return n; }), coreAt = areaWords ? all.filter(function (n) { return !AREA_WORDS[words[n]]; }) : all;
      var cost = function (w, n, toks) {
        var best = Infinity;
        for (var j = 0; j < toks.length; j++) {
          var t = toks[j];
          if (t.indexOf(w) === 0) return 0;
          if (near[n] && near[n][t] != null && near[n][t] < best) best = near[n][t];
        }
        return best;
      };
      if (near.some(Boolean)) {
        pool.forEach(function (r, k) {
          var p = prepRow(r), total = 0, inName = false, at = r.t === "council" || r.t === "constituency" ? coreAt : all;
          for (var x = 0; x < at.length; x++) {
            var n = at[x], c = cost(words[n], n, p.nt);
            if (c !== Infinity) inName = true; else c = cost(words[n], n, p.st);
            if (c === Infinity) return;
            total += c;
          }
          if (inName && total > 0) hits.push({ row: r, score: -total, i: k, len: p.name.length });
        });
        out.fuzzy = hits.length > 0;
      }
    }
    hits.sort(function (a, b) { return b.score - a.score || typeRank(a.row) - typeRank(b.row) || a.len - b.len || a.i - b.i; });
    out.rows = hits.slice(0, limit).map(function (h) { return h.row; });
    return out;
  }
  // Every word starts a word of the name or the place, and at least one starts a word of the name.
  function placed(words, p) {
    var inName = false;
    for (var i = 0; i < words.length; i++) {
      if (starts(words[i], p.nt)) inName = true;
      else if (!starts(words[i], p.st)) return false;
    }
    return inName;
  }
  // The best matches as a list (searchMatches without the flags); map.js uses it too.
  function rankSearch(rows, q, limit, opts) { return searchMatches(rows, q, limit, opts).rows; }
  var pinLimits = { school: 6, area: 4 };
  function samePin(a, b) { return a && b && a.type === b.type && String(a.id) === String(b.id); }
  function cleanPin(item) {
    return { type: item.type === "area" ? "area" : "school", id: String(item.id), name: String(item.name || ""), p: String(item.p || "") };
  }
  // Returns {list, action: "added"|"removed"|"full", limit}. Never mutates the input list.
  function togglePin(list, item) {
    list = Array.isArray(list) ? list : [];
    if (!item || item.id == null) return { list: list, action: "full", limit: 0 };
    var without = list.filter(function (p) { return !samePin(p, item); });
    if (without.length !== list.length) return { list: without, action: "removed" };
    var type = item.type === "area" ? "area" : "school", limit = pinLimits[type];
    var count = list.filter(function (p) { return p.type === type; }).length;
    if (count >= limit) return { list: list, action: "full", limit: limit };
    return { list: list.concat([cleanPin(item)]), action: "added" };
  }
  // urns: strings or numbers; lookup: function(urn) -> {name, p} | map {urn: {name, p}}. Unknown URNs
  // (no money page) are not imported. Returns {list, added, skipped, unknown}.
  function importShortlist(list, urns, lookup) {
    var out = { list: Array.isArray(list) ? list.slice() : [], added: 0, skipped: 0, unknown: 0 };
    var seen = {};
    (Array.isArray(urns) ? urns : []).forEach(function (u) {
      var key = String(u == null ? "" : u).trim();
      if (!/^\d+$/.test(key) || seen[key]) return;
      seen[key] = true;
      var info = typeof lookup === "function" ? lookup(key) : (lookup ? lookup[key] : null);
      if (!info || !info.name) { out.unknown++; return; }
      var item = { type: "school", id: key, name: info.name, p: info.p || ("/school/" + key + "/") };
      if (out.list.some(function (p) { return samePin(p, item); })) { out.skipped++; return; }
      var r = togglePin(out.list, item);
      if (r.action === "added") { out.list = r.list; out.added++; } else out.skipped++;
    });
    return out;
  }
  function slugify(s) {
    return norm(String(s || "").replace(/&/g, " and ")).replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80).replace(/-+$/, "") || "school";
  }
  function milesBetween(a, b) {
    var r = Math.PI / 180, p1 = a.lat * r, p2 = b.lat * r;
    var h = Math.pow(Math.sin((p2 - p1) / 2), 2) + Math.cos(p1) * Math.cos(p2) * Math.pow(Math.sin((b.lon - a.lon) * r / 2), 2);
    return 3958.8 * 2 * Math.asin(Math.sqrt(Math.min(1, h)));
  }
  // The district file's schools, nearest first from `from` ({lat, lon}; else the district centre), as search rows
  // whose sub says how far away each one is.
  function nearestRows(doc, from, limit) {
    if (!doc || !Array.isArray(doc.schools)) return [];
    var origin = from && isFinite(from.lat) && isFinite(from.lon) ? from : (isFinite(doc.lat) ? { lat: doc.lat, lon: doc.lon } : null);
    return doc.schools.map(function (r) {
      var mi = origin && isFinite(r.lat) && isFinite(r.lon) ? milesBetween(origin, r) : r.mi;
      var away = isFinite(mi) ? (mi < 0.1 ? "under 0.1 miles" : mi.toFixed(1) + " miles") : "";
      return { t: "school", id: r.id, name: r.name, status: r.status || null, p: r.p, mi: mi,
        sub: [away, r.sub].filter(Boolean).join(" · ") };
    }).sort(function (x, y) { return (isFinite(x.mi) ? x.mi : 1e9) - (isFinite(y.mi) ? y.mi : 1e9); }).slice(0, limit || 10);
  }
  // A full postcode's position from postcodes.io (the lookup Schools in Reach already uses); null when it can't say.
  function postcodePoint(full) {
    if (!full || typeof fetch !== "function") return Promise.resolve(null);
    return fetch("https://api.postcodes.io/postcodes/" + encodeURIComponent(full)).then(function (r) {
      return r.ok ? r.json() : null;
    }).then(function (j) {
      var x = j && j.result;
      return x && isFinite(x.latitude) && isFinite(x.longitude) ? { lat: x.latitude, lon: x.longitude } : null;
    }).catch(function () { return null; });
  }
  // Schools near a parsed postcode: {rows, exact} (exact = sorted from the full postcode, not the district centre).
  // districtOnly (the suggestions while typing) never sends the postcode off the site; pressing Search does.
  function schoolsNear(pc, limit, districtOnly) {
    return Promise.all([postcodeLookup(pc.district), districtOnly ? null : postcodePoint(pc.full)]).then(function (r) {
      return { rows: nearestRows(r[0], r[1], limit), exact: !!r[1] };
    });
  }
  function postcodeLookup(district) {
    var d = String(district || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
    if (!d || typeof fetch !== "function") return Promise.resolve(null);
    return fetch("/data/postcodes/" + encodeURIComponent(d) + ".json").then(function (r) {
      if (!r.ok) return null;
      return r.json();
    }).catch(function () { return null; });
  }

  // A SERIES file (/data/sx/<urn>.json) as the drill payload {title, year, rows, series, src} for one metric.
  // Totals break down into their own lines for the chosen year, and each line drills into its own series.
  var SX_REF = /^(\/data\/sx\/[0-9]+\.json)#m:([a-z0-9_]+)$/;
  var STAFF = ["teaching_staff", "supply_staff", "education_support_staff", "admin_clerical_staff", "premises_staff", "catering_staff", "other_staff_costs"];
  var BREAKDOWN = {
    total_income: ["grant_funding_government", "sen_funding", "pupil_premium", "other_dfe_grants", "self_generated_income",
                   "donations_revenue", "donations_capital", "facilities_income", "catering_income"],
    total_expenditure: STAFF.concat(["premises", "energy", "occupation", "catering", "educational_supplies", "supplies_services", "bought_in_services"]),
    total_staff: STAFF
  };
  function isNum(v) { return typeof v === "number" && isFinite(v); }
  function seriesDrill(sx, metric, opts) {
    opts = opts || {};
    var all = sx && sx.m && typeof sx.m === "object" ? sx.m : null;
    var m = all && all[metric];
    if (!m || typeof m !== "object") return null;
    var years = (Array.isArray(sx.years) ? sx.years : []).filter(function (y) { return m[y] && isNum(m[y].v); });
    if (!years.length) return null;
    var label = typeof opts.label === "function" ? opts.label : function (k) { return String(k).replace(/_/g, " "); };
    var suspect = (sx.flags && sx.flags.suspect) || {};
    function flagged(y, k) { return Array.isArray(suspect[y]) && suspect[y].indexOf(k) !== -1; }
    var year = opts.year && years.indexOf(opts.year) !== -1 ? opts.year : years[years.length - 1];
    var rows = (BREAKDOWN[metric] || []).map(function (k) {
      var c = all[k] && all[k][year];
      if (!c || !isNum(c.v)) return null;
      var r = { key: k, label: label(k), v: c.v, pp: isNum(c.pp) ? c.pp : null };
      if (opts.file) r.drill = opts.file + "#m:" + k;
      if (flagged(year, k)) r.suspect = true;
      return r;
    }).filter(Boolean);
    return {
      title: opts.title || label(metric), year: year, rows: rows,
      series: years.map(function (y) {
        var p = { y: y, v: m[y].v, pp: isNum(m[y].pp) ? m[y].pp : null };
        if (flagged(y, metric)) p.suspect = true;
        return p;
      }),
      src: opts.src || null
    };
  }
  // Table filters: tags are "group:value" slugs separated by spaces. A row shows when, for every group with
  // an active filter, it carries one of that group's active values.
  function parseTags(text) {
    var out = {};
    String(text == null ? "" : text).split(/\s+/).forEach(function (t) {
      var i = t.indexOf(":");
      if (i < 1 || i === t.length - 1) return;
      var g = t.slice(0, i);
      (out[g] = out[g] || []).push(t.slice(i + 1));
    });
    return out;
  }
  function rowShown(tags, active) {
    return Object.keys(active || {}).every(function (g) {
      var want = active[g] || [];
      if (!want.length) return true;
      var mine = (tags && tags[g]) || [];
      return want.some(function (v) { return mine.indexOf(v) !== -1; });
    });
  }
  // Rows of pinned schools first (in their existing order), then the rest; returns a new array.
  function pinnedFirst(rows, urnOf, pinned) {
    var top = [], rest = [];
    (rows || []).forEach(function (r) { (pinned[String(urnOf(r))] ? top : rest).push(r); });
    return top.concat(rest);
  }

  // Readers ("Show me what matters to a ..."): the panel of one-tap links under the header, and the tags on a
  // school page's sections. A link is [text, target]; a target is a site path, "#id" on this page, "video" or
  // "video:ptfa" (the school's 30-second videos), "deck:<view>" (the school's presentation), "deck" (the area's)
  // or "map".
  var READERS = ["parent", "governor", "ptfa", "leader", "pupil"];
  var READER_TITLES = { parent: "For parents", governor: "For governors", ptfa: "For PTFA committees",
                        leader: "For school leaders", pupil: "For pupils" };
  var SCHOOL_LINKS = {
    parent: [["What the status means", "#status"], ["Questions to ask the school", "#questions"], ["Share the 30-second video", "video"],
             ["What the PTFA raises", "#ptfa"], ["How the money is split", "#split"]],
    governor: [["Governors' presentation", "deck:governors"], ["Spending vs similar schools", "#spending"], ["Nearby schools compared", "#nearby"],
               ["Questions for the head", "#questions"], ["Budget health check", "/tools/budget-check/"], ["Reserves by year", "#reserve"]],
    ptfa: [["PTFA presentation", "deck:ptfa"], ["The PTFA's 30-second video", "video:ptfa"], ["How the PTFA compares", "#ptfa"],
           ["PTA planner", "/tools/pta-planner/"], ["Fundraising guide", "/guides/ptfa/"]],
    leader: [["School review presentation", "deck:review"], ["Spending vs similar schools", "#spending"], ["Nearby schools compared", "#nearby"],
             ["Budget and PTA tools", "/tools/"], ["Compare with other schools", "/compare/"], ["Funding vs spending", "#funding"]],
    pupil: [["Watch the 30-second video", "video"], ["How my school's money is split", "#split"], ["Where school money goes", "/guides/pupils/"],
            ["Where the money comes from", "#income"]]
  };
  var AREA_LINKS = {
    parent: [["Your school in the table", "#schools"], ["See it on the map", "map"], ["Present this area", "deck"]],
    governor: [["Present this area", "deck"], ["Every school in the table", "#schools"], ["See it on the map", "map"]],
    ptfa: [["Every school in the table", "#schools"], ["Present this area", "deck"], ["See it on the map", "map"]],
    leader: [["Present this area", "deck"], ["Every school in the table", "#schools"], ["See it on the map", "map"]],
    pupil: [["See it on the map", "map"], ["Your school in the table", "#schools"]]
  };
  // Anywhere on the site; they also top up a school's or an area's own links to five. Labels stay short enough for
  // two lines on a 360px phone.
  var GENERAL_LINKS = {
    parent: [["Guide for parents", "/guides/parents/"], ["30-second school videos", "/video/"], ["What PTFAs raise", "/ptfa/"],
             ["Schools on the map", "/map/"], ["Find a school", "/"]],
    governor: [["Guide for governors", "/guides/governors/"], ["Budget health check", "/tools/budget-check/"], ["Compare schools", "/compare/"],
               ["Schools in deficit", "/debts/"], ["Schools on the map", "/map/"]],
    ptfa: [["Fundraising guide", "/guides/ptfa/"], ["PTA planner", "/tools/pta-planner/"], ["What PTFAs raise", "/ptfa/"],
           ["30-second PTFA videos", "/video/"], ["Find a school", "/"]],
    leader: [["Guide for school leaders", "/guides/school-leaders/"], ["Budget and PTA tools", "/tools/"], ["Compare schools", "/compare/"],
             ["Schools in deficit", "/debts/"], ["Schools on the map", "/map/"]],
    pupil: [["Where school money goes", "/guides/pupils/"], ["Schools on the map", "/map/"], ["30-second school videos", "/video/"],
            ["Find a school", "/"]]
  };
  var SCHOOL_PATH = /^\/school\/(\d{1,8})-[a-z0-9-]+\/$/;
  // What a page is from its path: a school's page (with its urn), a council, constituency or trust page (any page of
  // its table), or "other".
  function pageOf(pathname) {
    var p = String(pathname == null ? "/" : pathname), m = SCHOOL_PATH.exec(p);
    if (m) return { kind: "school", path: p, urn: m[1] };
    m = /^\/(council|constituency|trust)\/[a-z0-9-]+\/(?:\d+\/)?$/.exec(p);
    return { kind: m ? m[1] : "other", path: p };
  }
  // The panel's links for a reader on a page, best first, at most five ([] for an unknown reader). page is pageOf's
  // result plus sections (the ids on the page) and, on a council or constituency page, areaId from its pin. An in-page
  // link needs its id in sections; a school's videos and presentations need its #status (a school without a return has
  // neither); an area presentation needs the area's id (trusts have none); nothing links to the page itself.
  function audienceLinks(reader, page) {
    if (READERS.indexOf(reader) === -1) return [];
    var p = page || {}, ids = p.sections || [], out = [], seen = {};
    var school = p.kind === "school" && SCHOOL_PATH.test(String(p.path)) && /^\d{1,8}$/.test(String(p.urn)) && ids.indexOf("status") !== -1;
    var area = p.kind === "council" || p.kind === "constituency" || p.kind === "trust";
    function href(target) {
      if (target.charAt(0) === "/") return target;
      if (target.charAt(0) === "#") return ids.indexOf(target.slice(1)) !== -1 ? target : null;
      if (target === "video" || target === "video:ptfa") return school ? p.path + "video/" + (target === "video:ptfa" ? "?mode=ptfa" : "") : null;
      if (target.indexOf("deck:") === 0) return school ? "/deck/?urn=" + p.urn + "&view=" + target.slice(5) : null;
      if (target === "deck") return area && p.kind !== "trust" && p.areaId ? "/deck/?area=" + encodeURIComponent(p.areaId) : null;
      if (target === "map") return p.kind === "constituency" ? "/map/?g=constituency" : "/map/";
      return null;
    }
    var own = school ? SCHOOL_LINKS[reader] : area ? AREA_LINKS[reader] : [];
    own.concat(GENERAL_LINKS[reader]).forEach(function (l) {
      var h = out.length < 5 ? href(l[1]) : null;
      if (!h || seen[h] || h.split(/[?#]/)[0] === p.path) return;
      seen[h] = true;
      out.push({ text: l[0], href: h });
    });
    return out;
  }

  var API = {
    fmtMoney: fmtMoney, perPupil: perPupil, parsePostcode: parsePostcode, rankSearch: rankSearch,
    milesBetween: milesBetween, nearestRows: nearestRows, schoolsNear: schoolsNear,
    searchMatches: searchMatches, fold: fold, editDistance: editDistance,
    pinLimits: pinLimits, togglePin: togglePin, importShortlist: importShortlist, postcodeLookup: postcodeLookup,
    slugify: slugify, unitOf: unitOf, fmtUnit: fmtUnit, seriesDrill: seriesDrill, parseTags: parseTags,
    rowShown: rowShown, pinnedFirst: pinnedFirst, SX_REF: SX_REF,
    READERS: READERS, READER_TITLES: READER_TITLES, pageOf: pageOf, audienceLinks: audienceLinks
  };
  root.MoneyApp = API;
  if (typeof document === "undefined") return;

  // ======================================================================
  // DOM wiring
  // ======================================================================
  var LABELS = { in_deficit: "In deficit", heading_for_deficit: "Heading for deficit", tight: "Tight", healthy: "Healthy", large_reserves: "Large reserves",
                 reserve_held_by_trust: "Reserve held by the trust" };
  var ICONS = { in_deficit: "▼", heading_for_deficit: "↘", tight: "●", healthy: "✓", large_reserves: "▲", reserve_held_by_trust: "◇" };
  var KEY_AUD = "moneyAudience", KEY_PIN = "moneyPinned";

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $$(sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }
  function storeGet(key, fallback) {
    try { var raw = localStorage.getItem(key); return raw == null ? fallback : JSON.parse(raw); } catch (e) { return fallback; }
  }
  function storeSet(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* private mode or full */ }
  }
  var jsonCache = {};
  // Resolves to parsed JSON, or null on any failure (404, bad JSON, offline). Never throws.
  function fetchJSON(url) {
    if (jsonCache[url]) return jsonCache[url];
    jsonCache[url] = fetch(url).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; })
      .then(function (d) { if (d == null) delete jsonCache[url]; return d; });
    return jsonCache[url];
  }
  function num(attr) {
    if (attr == null || attr === "") return null;
    var n = parseFloat(attr);
    return isFinite(n) ? n : null;
  }
  function badge(status, size) {
    var b = el("span", "badge " + (size || "small") + " s-" + status);
    var i = el("span", null, ICONS[status] || "");
    i.setAttribute("aria-hidden", "true");
    b.appendChild(i);
    b.appendChild(document.createTextNode(" " + (LABELS[status] || status)));
    return b;
  }
  function place(box, x, y, below) {
    box.hidden = false;
    var r = box.getBoundingClientRect();
    var left = Math.min(Math.max(8, x - r.width / 2), window.innerWidth - r.width - 8);
    var top = below || y - r.height - 12 < 8 ? y + 16 : y - r.height - 12;
    if (top + r.height > window.innerHeight - 8) top = Math.max(8, window.innerHeight - r.height - 8);
    box.style.left = left + "px";
    box.style.top = top + "px";
  }
  function focusables(container) {
    return $$('a[href],button:not([disabled]),input:not([disabled]),select,textarea,[tabindex]:not([tabindex="-1"])', container)
      .filter(function (e) { return e.offsetParent !== null || e === document.activeElement; });
  }

  // ---------------------------------------------------------------- phone menu (site.MENU_BUTTON)
  // At 600px and below app.css hides the nav until the Menu button opens it (without JavaScript the button is hidden and
  // the nav shows). Escape closes it and, when focus was in the menu, puts focus back on the button.
  (function menu() {
    var button = $("button.menu-toggle"), nav = button && document.getElementById(button.getAttribute("aria-controls") || "");
    if (!button || !nav) return;
    var more = $("details.nav-more", nav);
    function open() { return button.getAttribute("aria-expanded") === "true"; }
    button.addEventListener("click", function () { button.setAttribute("aria-expanded", open() ? "false" : "true"); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && more && more.hasAttribute("open")) {
        more.removeAttribute("open");
        if (more.contains(document.activeElement)) $("summary", more).focus();
        return;
      }
      if (e.key !== "Escape" || !open()) return;
      var inside = document.activeElement === button || nav.contains(document.activeElement);
      button.setAttribute("aria-expanded", "false");
      if (inside) button.focus();
    });
  })();

  // ---------------------------------------------------------------- audience
  // The chosen reader sets html[data-reader] (the strip's space and section tags; the head script restores it
  // before first paint) and html[data-audience] (which [data-for]
  // copy shows: the reader, else "parent"). The picker lives on home; other pages show one dismissible strip.
  (function audience() {
    var html = document.documentElement, slot = document.getElementById("for-you"), picker = $("fieldset.audience"), live = null;
    var page = pageOf(typeof location !== "undefined" ? location.pathname : "/");
    var table = page.kind !== "school" && page.kind !== "other" ? $("main table[data-sortable]") : null;
    if (table && !table.id && !document.getElementById("schools")) table.id = "schools";  // the panel's "in the table" link
    var pin = $("main button.pin[data-pin]"), d = null;
    try { d = pin && JSON.parse(pin.getAttribute("data-pin")); } catch (e) { d = null; }
    if (d && page.kind === "school" && d.type === "school" && String(d.id) === page.urn) page.name = String(d.name || "");
    if (d && (page.kind === "council" || page.kind === "constituency") && d.type === "area") {
      page.areaId = String(d.id || "");
      page.name = String(d.name || "");
    }
    page.sections = $$("main [id]").map(function (n) { return n.id; });
    if (picker) {
      live = el("span", "visually-hidden");
      live.setAttribute("role", "status");
      picker.appendChild(live);
    }
    function render(reader) {
      if (!slot) return 0;
      slot.textContent = "";
      var links = reader ? audienceLinks(reader, page) : [];
      if (!links.length) return 0;
      var box = el("nav", "fy"), head = el("p", "fy-head"), title = el("strong", "fy-title", READER_TITLES[reader]), list = el("ul");
      box.setAttribute("aria-labelledby", "fy-title");
      title.id = "fy-title";
      head.appendChild(title);
      head.appendChild(el("span", "fy-sub", page.name ? "Quick links for " + page.name : "Quick links"));
      links.forEach(function (l) {
        var li = el("li"), a = el("a", null, l.text);
        a.setAttribute("href", l.href);
        li.appendChild(a);
        list.appendChild(li);
      });
      box.appendChild(head);
      box.appendChild(list);
      var close = el("button", "aud-clear fy-close", "Close");
      close.type = "button";
      close.setAttribute("aria-label", "Close quick links and clear audience choice");
      box.appendChild(close);
      slot.appendChild(box);
      return links.length;
    }
    function apply(reader) {
      html.setAttribute("data-audience", reader || "parent");
      if (reader) html.setAttribute("data-reader", reader); else html.removeAttribute("data-reader");
      $$("button[data-audience]").forEach(function (b) {
        b.setAttribute("aria-pressed", b.getAttribute("data-audience") === reader ? "true" : "false");
      });
      return render(reader);
    }
    var saved = storeGet(KEY_AUD, null);
    apply(READERS.indexOf(saved) === -1 ? null : saved);
    document.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("button[data-audience], button.aud-clear");
      if (!b) return;
      var a = b.getAttribute("data-audience");
      if (a !== null && READERS.indexOf(a) === -1) return;
      // A chip chooses its reader; pressing the chosen chip again, or Clear, clears the choice.
      var next = a !== null && b.getAttribute("aria-pressed") !== "true" ? a : null;
      storeSet(KEY_AUD, next);
      var shown = apply(next);
      if (live) live.textContent = !next ? "Choice cleared"
        : READER_TITLES[next] + (shown ? ": " + shown + " quick links below" : " chosen");
      // The close control disappears. Return focus to a useful, visible control on this page.
      if (!next && b.classList.contains("aud-clear")) {
        var first = picker ? $("button[data-audience]", picker) : document.getElementById("q");
        if (first) first.focus();
      }
    });
  })();

  // ---------------------------------------------------------------- glossary
  var glossary = null, glossaryPromise = null;
  function loadGlossary() {
    if (glossary) return Promise.resolve(glossary);
    if (!glossaryPromise) glossaryPromise = fetchJSON("/assets/glossary.json").then(function (g) { glossary = g || {}; return glossary; });
    return glossaryPromise;
  }
  function term(key) { return (glossary && glossary[key]) || null; }
  function figureData(mf) {
    var key = mf.getAttribute("data-mf") || "";
    var g = term(key) || {};
    var unit = unitOf(key, mf.getAttribute("data-unit"), mf.textContent), money = unit === "money";
    return {
      key: key,
      unit: unit,
      label: mf.getAttribute("data-label") || g.label || key.replace(/_/g, " "),
      v: num(mf.getAttribute("data-v")),
      pp: money ? num(mf.getAttribute("data-pp")) : null,
      year: mf.getAttribute("data-year") || "",
      src: mf.getAttribute("data-src") || "",
      similar: money ? num(mf.getAttribute("data-cmp-similar")) : null,
      england: money ? num(mf.getAttribute("data-cmp-england")) : null,
      drill: mf.getAttribute("data-drill") || "",
      signed: mf.hasAttribute("data-signed"),
      plain: g.plain || "", how: g.how || "", source: g.source || ""
    };
  }
  function compareText(pp, other, who) {
    if (pp == null || other == null || other === 0) return null;
    var diff = (pp - other) / Math.abs(other) * 100;
    if (Math.abs(diff) < 1) return "about the same as " + who;
    return Math.abs(diff).toFixed(0) + "% " + (diff > 0 ? "more than " : "less than ") + who + " (" + fmtExact(other) + " per pupil)";
  }

  // ---------------------------------------------------------------- tooltips ([data-tip] and .mf)
  var tip = el("div", "tooltip");
  tip.id = "money-tip";
  tip.setAttribute("role", "tooltip");
  tip.hidden = true;
  document.body.appendChild(tip);
  var tipFor = null;
  function renderTip(target) {
    tip.textContent = "";
    if (target.hasAttribute("data-tip")) { tip.textContent = target.getAttribute("data-tip"); return; }
    var d = figureData(target);
    tip.appendChild(el("b", null, d.label + (d.year ? " · " + d.year : "")));
    if (d.plain) tip.appendChild(el("div", "plain", d.plain));
    var row;
    if (d.v != null) {
      row = el("div", "row");
      row.appendChild(el("span", null, d.unit === "pct" ? "Share" : d.unit === "n" ? "Count" : "Total"));
      row.appendChild(el("span", "num", fmtUnit(d.v, d.unit, d.signed, true)));
      tip.appendChild(row);
    }
    if (d.pp != null) {
      row = el("div", "row");
      row.appendChild(el("span", null, "Per pupil"));
      row.appendChild(el("span", "num", fmtExact(d.pp, d.signed)));
      tip.appendChild(row);
    }
    var s = compareText(d.pp, d.similar, "similar schools"), e = compareText(d.pp, d.england, "England");
    if (s) tip.appendChild(el("div", "cmp", "Similar schools: " + s));
    if (e) tip.appendChild(el("div", "cmp", "England: " + e));
    if (d.source) tip.appendChild(el("div", "src", "Source: " + d.source));
    tip.appendChild(el("div", "src", "Click for the breakdown"));
  }
  function showTip(target, x, y) {
    tipFor = target;
    renderTip(target);
    place(tip, x, y);
    target.setAttribute("aria-describedby", tip.id);
    if (!glossary && target.classList.contains("mf")) loadGlossary().then(function () { if (tipFor === target && !tip.hidden) { renderTip(target); place(tip, x, y); } });
  }
  function hideTip() {
    if (tipFor) tipFor.removeAttribute("aria-describedby");
    tipFor = null;
    tip.hidden = true;
  }
  document.addEventListener("pointermove", function (e) {
    if (e.pointerType === "touch") return;
    var t = e.target.closest && e.target.closest("[data-tip],.mf");
    if (!t) { if (tipFor) hideTip(); return; }
    if (t !== tipFor) showTip(t, e.clientX, e.clientY); else place(tip, e.clientX, e.clientY);
  });
  document.addEventListener("focusin", function (e) {
    var t = e.target.closest && e.target.closest("[data-tip],.mf");
    if (!t) return;
    var r = t.getBoundingClientRect();
    showTip(t, r.left + r.width / 2, r.top);
  });
  document.addEventListener("focusout", hideTip);
  document.addEventListener("scroll", hideTip, true);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && tipFor) hideTip(); });

  // ---------------------------------------------------------------- money figures: enhance + drill-down
  function enhanceFigures(ctx) {
    $$(".mf", ctx).forEach(function (mf) {
      if (mf.classList.contains("js")) return;
      mf.classList.add("js");
      mf.setAttribute("tabindex", "0");
      mf.setAttribute("role", "button");
      mf.setAttribute("aria-haspopup", "dialog");
      if (num(mf.getAttribute("data-v")) < 0) mf.classList.add("neg");
    });
  }
  enhanceFigures(document);

  var drill = null, backdrop = null, drillOpener = null, drillStack = [];
  function buildDrill() {
    if (drill) return;
    backdrop = el("div", "drill-backdrop");
    backdrop.hidden = true;
    backdrop.addEventListener("click", closeDrill);
    drill = el("aside", "drill");
    drill.setAttribute("role", "dialog");
    drill.setAttribute("aria-modal", "true");
    drill.setAttribute("aria-labelledby", "drill-title");
    drill.hidden = true;
    drill.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { e.preventDefault(); closeDrill(); return; }
      if (e.key !== "Tab") return;
      var f = focusables(drill);
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    });
    document.body.appendChild(backdrop);
    document.body.appendChild(drill);
  }
  function closeDrill() {
    if (!drill || drill.hidden) return;
    drillSeq++;
    drill.hidden = true;
    backdrop.hidden = true;
    drillStack = [];
    document.body.style.overflow = "";
    if (drillOpener && drillOpener.focus) drillOpener.focus();
    drillOpener = null;
  }
  function sparkline(series, fmt) {
    fmt = fmt || fmtMoney;
    var pts = (series || []).filter(function (s) { return s && typeof s.v === "number" && isFinite(s.v); });
    if (pts.length < 2) return null;
    var NS = "http://www.w3.org/2000/svg", W = 320, H = 72, L = 4, R = 4, T = 10, B = 16;
    var vals = pts.map(function (p) { return p.v; });
    var lo = Math.min(0, Math.min.apply(null, vals)), hi = Math.max(0, Math.max.apply(null, vals));
    if (hi === lo) hi = lo + 1;
    function x(i) { return L + i * (W - L - R) / (pts.length - 1); }
    function y(v) { return T + (hi - v) / (hi - lo) * (H - T - B); }
    var svg = document.createElementNS(NS, "svg");
    svg.setAttribute("class", "spark");
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", pts.map(function (p) { return p.y + ": " + fmt(p.v); }).join(", "));
    if (lo < 0) {
      var z = document.createElementNS(NS, "line");
      z.setAttribute("class", "zero");
      z.setAttribute("x1", L); z.setAttribute("x2", W - R); z.setAttribute("y1", y(0)); z.setAttribute("y2", y(0));
      svg.appendChild(z);
    }
    var path = document.createElementNS(NS, "path");
    path.setAttribute("d", "M" + pts.map(function (p, i) { return x(i).toFixed(1) + "," + y(p.v).toFixed(1); }).join("L"));
    svg.appendChild(path);
    var dot = document.createElementNS(NS, "circle");
    dot.setAttribute("cx", x(pts.length - 1)); dot.setAttribute("cy", y(pts[pts.length - 1].v)); dot.setAttribute("r", "3.5");
    svg.appendChild(dot);
    [[0, "start"], [pts.length - 1, "end"]].forEach(function (a) {
      var t = document.createElementNS(NS, "text");
      t.setAttribute("x", x(a[0])); t.setAttribute("y", H - 3); t.setAttribute("text-anchor", a[1]);
      t.textContent = pts[a[0]].y;
      svg.appendChild(t);
    });
    return svg;
  }
  // A money figure built in the browser, following the same data-* contract as site.money_figure() so the
  // tooltip and drill-down work on it. opts: {unit, signed, similar, england, ppFirst (per-pupil as the
  // headline, total in small print: used where the row is already "per pupil")}.
  function figureSpan(key, v, pp, year, label, src, opts) {
    opts = opts || {};
    var unit = unitOf(key, opts.unit, "");
    if (typeof v !== "number" || !isFinite(v)) v = null;
    if (typeof pp !== "number" || !isFinite(pp) || unit !== "money") pp = null;
    var ppFirst = !!opts.ppFirst && pp != null;
    var s = el("span", "mf", ppFirst ? fmtExact(pp, opts.signed) : fmtUnit(v, unit, opts.signed, false));
    s.setAttribute("data-mf", key || "cfr_line");
    s.setAttribute("data-v", v == null ? "" : String(v));
    if (pp != null) s.setAttribute("data-pp", String(pp));
    s.setAttribute("data-year", year || "");
    if (unit !== "money") s.setAttribute("data-unit", unit);
    if (label) s.setAttribute("data-label", label);
    if (src) s.setAttribute("data-src", src);
    if (opts.signed) s.setAttribute("data-signed", "1");
    if (typeof opts.drill === "string" && opts.drill) s.setAttribute("data-drill", opts.drill);
    if (typeof opts.similar === "number") s.setAttribute("data-cmp-similar", String(Math.round(opts.similar)));
    if (typeof opts.england === "number") s.setAttribute("data-cmp-england", String(Math.round(opts.england)));
    var small = null;
    if (ppFirst) { if (v != null) small = fmtMoney(v, opts.signed) + " total"; }
    else if (pp != null) small = fmtExact(pp, opts.signed) + " per pupil";
    if (small) { s.appendChild(document.createTextNode(" ")); s.appendChild(el("small", null, small)); }
    return s;
  }
  // Empties the panel and puts back its header (title + close button); returns the close button.
  function drillShell(title) {
    drill.textContent = "";
    var head = el("header");
    var h2 = el("h2", null, title);
    h2.id = "drill-title";
    head.appendChild(h2);
    var close = el("button", "close", "×");
    close.type = "button";
    close.setAttribute("aria-label", "Close");
    close.addEventListener("click", closeDrill);
    head.appendChild(close);
    drill.appendChild(head);
    return close;
  }
  function renderDrill(d, data) {
    var close = drillShell((data && data.title) || d.label);
    if (drillStack.length > 1) {
      var back = el("button", "button quiet", "‹ Back");
      back.type = "button";
      back.addEventListener("click", function () { drillStack.pop(); var prev = drillStack[drillStack.length - 1]; renderDrill(prev.d, prev.data); });
      drill.appendChild(back);
    }
    var year = (data && data.year) || d.year;
    if (year) drill.appendChild(el("p", "year", year));
    var headline;
    if (d.v == null && d.pp != null) headline = el("p", "headline", fmtExact(d.pp, d.signed) + " per pupil");
    else {
      headline = el("p", "headline", fmtUnit(d.v, d.unit, d.signed, true));
      if (d.pp != null) headline.appendChild(el("small", null, fmtExact(d.pp, d.signed) + " per pupil"));
    }
    drill.appendChild(headline);
    var s = compareText(d.pp, d.similar, "similar schools"), e = compareText(d.pp, d.england, "England");
    if (s || e) {
      drill.appendChild(el("h3", null, "Compared with"));
      var cmp = el("div", "cmp");
      if (s) { cmp.appendChild(el("span", null, "Similar schools")); cmp.appendChild(el("span", null, s)); }
      if (e) { cmp.appendChild(el("span", null, "England")); cmp.appendChild(el("span", null, e)); }
      drill.appendChild(cmp);
    }
    var spark = data && sparkline(data.series, function (v) { return fmtUnit(v, d.unit, false, false); });
    if (spark) { drill.appendChild(el("h3", null, "Over time")); drill.appendChild(spark); }
    if (data && Array.isArray(data.rows) && data.rows.length) {
      drill.appendChild(el("h3", null, "Breakdown"));
      var table = el("table");
      var body = table.createTBody();
      data.rows.forEach(function (r) {
        if (!r) return;
        var tr = body.insertRow();
        var th = el("th", null, r.label || (term(r.key) || {}).label || r.key || "");
        th.scope = "row";
        tr.appendChild(th);
        if (r.suspect) { tr.className = "suspect"; th.appendChild(el("small", null, " (figure under review)")); }
        var td = tr.insertCell();
        td.appendChild(figureSpan(r.key, r.v, r.pp, year, r.label, data.src, { unit: r.unit, signed: !!r.signed, drill: r.drill }));
      });
      drill.appendChild(table);
      enhanceFigures(table);
    }
    if (d.plain) { drill.appendChild(el("h3", null, "What this means")); drill.appendChild(el("p", null, d.plain)); }
    if (d.how || d.source) {
      drill.appendChild(el("h3", null, "How it's worked out"));
      if (d.how) drill.appendChild(el("p", null, d.how));
      if (d.source) drill.appendChild(el("p", "muted small", "Source: " + d.source));
    }
    var src = d.src || (data && data.src);
    if (src) {
      var a = el("a", "check", "Check at source ↗");
      a.href = src;
      a.rel = "noopener";
      drill.appendChild(a);
    }
    close.focus();
  }
  // Each open bumps drillSeq; closing does too. A reply only renders if it belongs to the current open.
  var drillSeq = 0;
  function openDrill(mf) {
    buildDrill();
    hideTip();
    var inPanel = drill.contains(mf);
    if (!inPanel) { drillOpener = mf; drillStack = []; }
    var seq = ++drillSeq;
    drill.hidden = false;
    backdrop.hidden = false;
    document.body.style.overflow = "hidden";
    // The dialog shell goes up at once, so focus moves inside it and Escape / the close button work while
    // the glossary and breakdown are still loading.
    var close = drillShell(figureData(mf).label);
    var busy = el("p", "muted", "Loading…");
    busy.setAttribute("role", "status");
    drill.appendChild(busy);
    close.focus();
    loadGlossary().then(function () {
      if (seq !== drillSeq) return;
      var d = figureData(mf);
      var ref = d.drill;
      var loader, sx = SX_REF.exec(ref);
      if (ref && ref.charAt(0) === "#") {
        var script = document.getElementById(ref.slice(1));
        var inline = null;
        try { inline = script ? JSON.parse(script.textContent) : null; } catch (err) { inline = null; }
        loader = Promise.resolve(inline);
      } else if (sx) {
        loader = fetchJSON(sx[1]).then(function (doc) {
          return seriesDrill(doc, sx[2], { year: d.year, src: d.src, title: d.label, file: sx[1],
            label: function (k) { return (term(k) || {}).label || String(k).replace(/_/g, " "); } });
        });
      } else if (ref) loader = fetchJSON(ref);
      else loader = Promise.resolve(null);
      loader.then(function (data) {
        if (seq !== drillSeq || drill.hidden) return;
        drillStack.push({ d: d, data: data });
        renderDrill(d, data);
      });
    });
  }
  document.addEventListener("click", function (e) {
    var mf = e.target.closest && e.target.closest(".mf");
    if (!mf || e.target.closest("a")) return;
    e.preventDefault();
    openDrill(mf);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" && e.key !== " ") return;
    var mf = e.target.closest && e.target.closest(".mf");
    if (!mf) return;
    e.preventDefault();
    openDrill(mf);
  });

  // ---------------------------------------------------------------- search index
  // Resolves to the index rows, or null when it could not be loaded; a failure is forgotten, so the next search
  // tries again rather than search staying off for the rest of the visit. fetchJSON keeps any parsed answer, so an
  // unusable one (an empty list, an error object) is dropped from its cache as well.
  var indexPromise = null;
  function loadIndex() {
    if (!indexPromise) indexPromise = fetchJSON("/data/search.json").then(function (d) {
      if (Array.isArray(d) && d.length) return d;
      indexPromise = null;
      delete jsonCache["/data/search.json"];
      return null;
    });
    return indexPromise;
  }
  var UNAVAILABLE = "Search is unavailable just now. Try again in a moment, or browse:";
  var BROWSE = [{ t: "browse", name: "Councils and regions", p: "/areas/" }, { t: "browse", name: "Schools on the map", p: "/map/" },
                { t: "browse", name: "Academy trusts", p: "/trust/" }];
  function didYouMean(row) { return "No exact matches. Did you mean " + row.name + "?"; }
  function schoolLookup(rows) {
    var map = {};
    rows.forEach(function (r) { if (r && r.t === "school") map[String(r.id)] = { name: r.name, p: r.p }; });
    return function (urn) { return map[String(urn)] || null; };
  }

  // ---------------------------------------------------------------- pins
  var pins = (storeGet(KEY_PIN, []) || []).filter(function (p) { return p && p.id != null; }).map(cleanPin);
  var pinbar = null, pinMsg = null;
  function buildPinbar() {
    if (pinbar) return;
    pinbar = el("div", "pinbar");
    pinbar.setAttribute("role", "region");
    pinbar.setAttribute("aria-label", "Pinned for comparison");
    pinbar.hidden = true;
    document.body.appendChild(pinbar);
  }
  function refreshPins() {
    storeSet(KEY_PIN, pins);
    var n = pins.length;
    $$("[data-pin-count]").forEach(function (c) {
      c.textContent = String(n);
      if (n) c.removeAttribute("data-zero"); else c.setAttribute("data-zero", "");
    });
    $$("[data-pin]").forEach(function (b) {
      var item = parsePin(b);
      b.setAttribute("aria-pressed", item && pins.some(function (p) { return samePin(p, item); }) ? "true" : "false");
    });
    buildPinbar();
    var msg = pinMsg;
    pinbar.textContent = "";
    pinbar.hidden = !n && !msg;
    document.body.classList.toggle("has-pinbar", !pinbar.hidden);
    if (n) {
      pinbar.appendChild(el("span", "count", "📌 " + n + " pinned"));
      pinbar.appendChild(el("span", "names", pins.map(function (p) { return p.name; }).join(" · ")));
      var schools = pins.filter(function (p) { return p.type === "school"; }), areas = pins.filter(function (p) { return p.type === "area"; });
      if (schools.length) {
        var a = el("a", "go", "Compare" + (areas.length ? " schools" : ""));
        a.href = "/compare/?urns=" + schools.map(function (p) { return encodeURIComponent(p.id); }).join(",");
        pinbar.appendChild(a);
      }
      if (areas.length) {
        var b = el("a", "go", "Compare" + (schools.length ? " areas" : ""));
        b.href = "/compare/?areas=" + areas.map(function (p) { return encodeURIComponent(p.id); }).join(",");
        pinbar.appendChild(b);
      }
      var clear = el("button", null, "Clear");
      clear.type = "button";
      clear.addEventListener("click", function () { pins = []; pinMsg = null; refreshPins(); });
      pinbar.appendChild(clear);
    }
    if (msg) {
      var m = el("span", "msg", msg);
      m.setAttribute("aria-live", "polite");
      pinbar.appendChild(m);
    }
    refreshImports();
  }
  // One-tap import of Schools in Reach's saved "shortlist" and "plan". The controls sit in their own
  // in-flow region ([data-pin-import] slot, else the end of <main>), so they are reachable before the first
  // pin; the pin bar only appears once something is pinned. "Not now" (or an import) hides the region until
  // the saved lists change.
  var KEY_IMPORT_SEEN = "moneyImportSeen", importBox = null;
  function importLists() {
    return [["shortlist", storeGet("shortlist", null)], ["plan", storeGet("plan", null)]]
      .filter(function (pair) { return Array.isArray(pair[1]) && pair[1].length; });
  }
  function importSignature(lists) {
    return lists.map(function (pair) { return pair[0] + ":" + pair[1].map(String).sort().join(","); }).join("|");
  }
  function refreshImports() {
    var lists = importLists();
    var signature = importSignature(lists);
    var show = lists.length && storeGet(KEY_IMPORT_SEEN, null) !== signature;
    if (!importBox) {
      if (!show) return;
      importBox = el("div", "pin-import");
      importBox.setAttribute("role", "region");
      importBox.setAttribute("aria-label", "Schools saved on Schools in Reach");
      var slot = $("[data-pin-import]") || document.getElementById("main") || document.body;
      slot.appendChild(importBox);
    }
    importBox.textContent = "";
    importBox.hidden = !show;
    if (!show) return;
    importBox.appendChild(el("span", "lead", "Pin the schools you saved on Schools in Reach to compare their money here."));
    lists.forEach(function (pair) {
      var btn = el("button", "button", "Import Schools in Reach " + pair[0] + " (" + pair[1].length + ")");
      btn.type = "button";
      btn.addEventListener("click", function () {
        loadIndex().then(function (rows) {
          // Without the index there are no names to pin by; say so and leave the offer up to try again.
          if (!rows) { pinMsg = "The list of schools didn't load, so nothing was added. Try again in a moment."; refreshPins(); return; }
          var r = importShortlist(pins, pair[1], schoolLookup(rows));
          pins = r.list;
          pinMsg = r.added ? "Added " + r.added + " from your " + pair[0] + "." : "Nothing new to add from your " + pair[0] + ".";
          if (r.skipped) pinMsg += " " + r.skipped + " left out: up to " + pinLimits.school + " schools can be pinned.";
          if (r.unknown) pinMsg += " " + r.unknown + " without a money page.";
          storeSet(KEY_IMPORT_SEEN, signature);
          refreshPins();
        });
      });
      importBox.appendChild(btn);
    });
    var later = el("button", "button quiet", "Not now");
    later.type = "button";
    later.addEventListener("click", function () { storeSet(KEY_IMPORT_SEEN, signature); refreshImports(); });
    importBox.appendChild(later);
  }
  function parsePin(b) {
    try { var item = JSON.parse(b.getAttribute("data-pin")); return item && item.id != null ? item : null; } catch (e) { return null; }
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-pin]");
    if (!b) return;
    var item = parsePin(b);
    if (!item) return;
    var r = togglePin(pins, item);
    pins = r.list;
    pinMsg = r.action === "full" ? "You can pin up to " + r.limit + " " + (item.type === "area" ? "areas" : "schools") + ". Unpin one to add another." : null;
    refreshPins();
  });
  refreshPins();

  // ---------------------------------------------------------------- search boxes (#q in the header, #find on the home page)
  function attachSearch(input) {
    if (!input) return;
    var list = document.getElementById(input.id + "-list");
    if (!list) {
      list = el("ul", "listbox");
      list.id = input.id + "-list";
      list.setAttribute("role", "listbox");
      list.hidden = true;
      input.parentNode.appendChild(list);
    }
    input.setAttribute("aria-controls", list.id);
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    if (!input.hasAttribute("aria-expanded")) input.setAttribute("aria-expanded", "false");
    // The count, a "Did you mean" or the unavailable note, said once by screen readers (the note in the list is visual).
    var status = el("span", "visually-hidden");
    status.setAttribute("role", "status");
    input.parentNode.appendChild(status);
    var go = input.getAttribute("data-go") || "";
    var options = [], active = -1, timer = null, lastQuery = "", urnHit = null;
    function hide() { list.hidden = true; list.textContent = ""; options = []; active = -1; input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); }
    function setActive(i) {
      active = i;
      options.forEach(function (o, k) { o.setAttribute("aria-selected", k === i ? "true" : "false"); });
      if (i >= 0) { input.setAttribute("aria-activedescendant", options[i].id); options[i].scrollIntoView({ block: "nearest" }); }
      else input.removeAttribute("aria-activedescendant");
    }
    // rows as options; note shows when there are none; lead goes above them (a "Did you mean" or the unavailable note).
    function render(rows, note, lead) {
      list.textContent = "";
      options = [];
      status.textContent = lead || (rows.length ? rows.length + (rows.length === 1 ? " suggestion" : " suggestions") : note || "");
      if (!rows.length) {
        if (note) list.appendChild(el("li", "empty", note));
        else { hide(); return; }
      }
      if (lead && rows.length) {
        var head = el("li", "note", lead);
        head.setAttribute("aria-hidden", "true");
        list.appendChild(head);
      }
      rows.forEach(function (r, i) {
        var li = el("li");
        li.id = input.id + "-opt-" + i;
        li.setAttribute("role", "option");
        li.setAttribute("aria-selected", "false");
        li.appendChild(el("span", "kind", r.t || ""));
        li.appendChild(el("span", "name", r.name || ""));
        if (r.status && LABELS[r.status]) li.appendChild(badge(r.status));
        if (r.sub) li.appendChild(el("span", "sub", r.sub));
        li.addEventListener("mousedown", function (e) { e.preventDefault(); });
        // data-go="video/" (the Videos page) sends a school pick to that page under the school's path.
        li.addEventListener("click", function () { if (r.p) location.href = r.p + (go && (r.t || "school") === "school" ? go : ""); });
        list.appendChild(li);
        options.push(li);
      });
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
      setActive(-1);
    }
    function run() {
      var q = input.value.trim();
      lastQuery = q;
      urnHit = null;
      if (q.length < 2) { hide(); return; }
      var pc = parsePostcode(q);
      if (pc && /\d/.test(q)) {
        schoolsNear(pc, 8, true).then(function (near) {
          if (lastQuery !== q) return;
          render(near.rows, "No schools found near " + (pc.full || pc.district));
        });
        return;
      }
      loadIndex().then(function (rows) {
        if (lastQuery !== q) return;
        if (!rows) { render(BROWSE, null, UNAVAILABLE); return; }
        var m = searchMatches(rows, q, 8);
        urnHit = m.urn ? m.rows[0] : null;
        render(m.rows, "No matches", m.fuzzy && m.rows.length ? didYouMean(m.rows[0]) : null);
      });
    }
    input.addEventListener("focus", function () { loadIndex(); });
    input.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(run, 80); });
    input.addEventListener("keydown", function (e) {
      if (list.hidden && (e.key === "ArrowDown") && input.value.trim()) { run(); return; }
      if (list.hidden) return;
      if (e.key === "ArrowDown") { e.preventDefault(); setActive(options.length ? (active + 1) % options.length : -1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); setActive(!options.length ? -1 : active <= 0 ? options.length - 1 : active - 1); }
      else if (e.key === "Enter" && active >= 0) { e.preventDefault(); options[active].click(); }
      // A URN typed in full goes straight to its school.
      else if (e.key === "Enter" && urnHit && urnHit.p && lastQuery === input.value.trim()) { e.preventDefault(); location.href = urnHit.p + (go && urnHit.t === "school" ? go : ""); }
      else if (e.key === "Escape") { hide(); }
    });
    input.addEventListener("blur", function () { setTimeout(hide, 120); });
  }
  attachSearch(document.getElementById("q"));
  attachSearch(document.getElementById("find"));

  // ---------------------------------------------------------------- /search/?q=: results in the page
  (function searchPage() {
    if (!/^\/search\/?$/.test(location.pathname)) return;
    var q = (new URLSearchParams(location.search).get("q") || "").trim();
    var header = document.getElementById("q");
    if (header && q) header.value = q;
    if (q.length < 2) return;
    var main = document.querySelector("main") || document.body;
    var h1 = main.querySelector("h1");
    var box = el("section", "search-results");
    box.setAttribute("aria-live", "polite");
    box.appendChild(el("p", "muted", "Searching…"));
    if (h1 && h1.nextSibling) h1.parentNode.insertBefore(box, h1.nextSibling); else main.insertBefore(box, main.firstChild);
    function show(rows, emptyNote, heading, jump) {
      box.textContent = "";
      box.appendChild(el("h2", null, rows.length ? (heading || "Results for “" + q + "”") : emptyNote));
      if (!rows.length) {
        box.appendChild(el("p", "muted", "Try part of the school's name, its town or council, its URN, or a postcode."));
        return;
      }
      var ul = el("ul", "results");
      rows.forEach(function (r) {
        var li = el("li"), a = el("a", null, r.name || "");
        a.href = r.p || "#";
        li.appendChild(el("span", "kind", r.t || ""));
        li.appendChild(a);
        if (r.status && LABELS[r.status]) li.appendChild(badge(r.status));
        if (r.sub) li.appendChild(el("span", "sub", r.sub));
        ul.appendChild(li);
      });
      box.appendChild(ul);
      if (jump && rows.length === 1 && rows[0].p) location.replace(rows[0].p);
    }
    var pc = parsePostcode(q);
    if (pc && /\d/.test(q)) {
      schoolsNear(pc, 30).then(function (near) {
        show(near.rows, "No schools found near " + (pc.full || pc.district), "Schools nearest " + (pc.full || pc.district));
        if (near.rows.length && !near.exact && pc.full) {
          box.insertBefore(el("p", "muted small", "Sorted from the middle of " + pc.district + "; the exact postcode couldn't be looked up."), box.children[1] || null);
        }
      });
      return;
    }
    function unavailable() {
      box.textContent = "";
      box.appendChild(el("h2", null, "Search is unavailable just now"));
      box.appendChild(el("p", null, "The list of schools didn't load. Try again in a moment, or browse:"));
      var ul = el("ul", "browse");
      BROWSE.forEach(function (b) { var li = el("li"), a = el("a", null, b.name); a.href = b.p; li.appendChild(a); ul.appendChild(li); });
      box.appendChild(ul);
      var again = el("button", "button", "Try again");
      again.type = "button";
      again.addEventListener("click", function () { box.textContent = ""; box.appendChild(el("p", "muted", "Searching…")); find(); });
      box.appendChild(again);
    }
    function find() {
      loadIndex().then(function (rows) {
        if (!rows) { unavailable(); return; }
        var m = searchMatches(rows, q, 50);
        if (m.urn) { show(m.rows.slice(0, 1), "", null, true); return; }  // a URN goes straight to its school
        if (!m.fuzzy) { show(m.rows, "No matches for “" + q + "”", null, true); return; }
        // Close matches only: say so, offer the best as "Did you mean", and never jump to it.
        show(m.rows, "", "Close matches for “" + q + "”");
        var dym = el("p", "dym", "No exact matches. Did you mean "), a = el("a", null, m.rows[0].name);
        a.href = m.rows[0].p || "#";
        dym.appendChild(a);
        dym.appendChild(document.createTextNode("?"));
        box.insertBefore(dym, box.children[1] || null);
      });
    }
    find();
  })();

  // ---------------------------------------------------------------- preview cards ([data-preview])
  (function previews() {
    var card = null, cardFor = null, timer = null;
    function build() {
      if (card) return;
      card = el("div", "preview");
      card.id = "money-preview";
      card.setAttribute("role", "tooltip");
      card.hidden = true;
      document.body.appendChild(card);
    }
    function latestYear(by) {
      var ys = Object.keys(by || {}).sort();
      return ys.length ? ys[ys.length - 1] : null;
    }
    function fill(ref, d) {
      card.textContent = "";
      if (!d) { card.appendChild(el("span", "muted", "No money data yet.")); return; }
      card.appendChild(el("span", "pname", d.name || ref));
      var dl = el("dl");
      function row(k, v) { dl.appendChild(el("dt", null, k)); dl.appendChild(el("dd", null, v)); }
      if (ref.indexOf("school:") === 0) {
        if (d.status && LABELS[d.status]) card.appendChild(badge(d.status));
        if (d.year) row("Year", d.year);
        row("Income per pupil", fmtExact(d.income_pp));
        row("Reserve per pupil", fmtExact(d.reserve_pp, true));
      } else {
        var y = latestYear(d.by_year), S = y && d.by_year[y] && d.by_year[y].all;
        if (y) row("Year", y);
        if (S) {
          row("Schools", S.schools == null ? "—" : String(S.schools));
          row("In deficit", S.in_deficit_pct == null ? "—" : S.in_deficit_pct.toFixed(0) + "%");
          row("Income per pupil (median)", fmtExact(S.income_pp_median));
          row("Reserve per pupil (median)", fmtExact(S.reserve_median_pp, true));
        }
      }
      card.appendChild(dl);
    }
    function show(target) {
      var ref = target.getAttribute("data-preview") || "";
      var m = /^(school|area):(.+)$/.exec(ref);
      if (!m) return;
      build();
      cardFor = target;
      var url = m[1] === "school" ? "/data/s/" + encodeURIComponent(m[2]) + ".json" : "/data/a/" + encodeURIComponent(m[2]) + ".json";
      fetchJSON(url).then(function (d) {
        if (cardFor !== target) return;
        fill(ref, d);
        var r = target.getBoundingClientRect();
        place(card, r.left + r.width / 2, r.bottom, true);
        target.setAttribute("aria-describedby", card.id);
      });
    }
    function hide() {
      clearTimeout(timer);
      if (cardFor) cardFor.removeAttribute("aria-describedby");
      cardFor = null;
      if (card) card.hidden = true;
    }
    // Mouse: hover shows after a short delay, leaving hides. Keyboard: focus shows, blur hides.
    // Touch: the first tap shows the card (and, on a link, does not follow it); a second tap follows the
    // link or, on anything else, hides the card. Tapping elsewhere hides it.
    var touched = null, touchedAt = 0;
    function isTouch(e, t) { return e.pointerType === "touch" || (touched === t && Date.now() - touchedAt < 1000); }
    document.addEventListener("pointerover", function (e) {
      if (e.pointerType === "touch") return;
      var t = e.target.closest && e.target.closest("[data-preview]");
      if (!t || t === cardFor) return;
      clearTimeout(timer);
      timer = setTimeout(function () { show(t); }, 150);
    });
    document.addEventListener("pointerout", function (e) {
      if (e.pointerType === "touch") return;
      var t = e.target.closest && e.target.closest("[data-preview]");
      if (t && !(e.relatedTarget && t.contains(e.relatedTarget))) hide();
    });
    document.addEventListener("pointerdown", function (e) {
      if (e.pointerType !== "touch") return;
      var t = e.target.closest && e.target.closest("[data-preview]");
      touched = t || null;
      touchedAt = Date.now();
      if (!t && cardFor && !(card && card.contains(e.target))) hide();
    });
    document.addEventListener("focusin", function (e) {
      var t = e.target.closest && e.target.closest("[data-preview]");
      if (t) show(t);
    });
    document.addEventListener("focusout", hide);
    document.addEventListener("click", function (e) {
      var t = e.target.closest && e.target.closest("[data-preview]");
      if (!t) return;
      var link = t.tagName === "A" || !!t.closest("a");
      if (link && !isTouch(e, t)) return;
      var open = cardFor === t && card && !card.hidden;
      if (open) { if (!link) hide(); return; }
      e.preventDefault();
      show(t);
    });
  })();

  // ---------------------------------------------------------------- sortable tables
  function cellValue(td) {
    if (!td) return "";
    var raw = td.querySelector("[data-sort]") || (td.hasAttribute("data-sort") ? td : null);
    if (raw) { var n = parseFloat(raw.getAttribute("data-sort")); if (isFinite(n)) return n; }
    var mf = td.querySelector(".mf");
    if (mf) { var v = num(mf.getAttribute("data-v")); if (v != null) return v; }
    return td.textContent.trim().toLowerCase();
  }
  function compareCells(x, y, asc) {
    var xn = typeof x === "number", yn = typeof y === "number";
    if (xn && yn) return asc ? x - y : y - x;
    if (xn !== yn) return xn ? -1 : 1;
    var c = String(x).localeCompare(String(y));
    return asc ? c : -c;
  }
  // Each header's text goes into a native button (sorting toggles ascending / descending; aria-sort stays on the th),
  // with a plain .th-label copy beside it. Above the table, .sort-controls offers the same as a labelled "Sort by"
  // select and a direction button: app.css shows them, and swaps the header buttons for the plain labels, where a
  // responsive table's header row is clipped on a phone, so no invisible control is left in the tab order. A page
  // script that rewrites a header (the map's measure column) gets its button back from the observer.
  var sortSeq = 0;
  $$("table[data-sortable]").forEach(function (t) {
    var head = t.tHead || $("thead", t), heads = $$("thead th", t), body = t.tBodies && t.tBodies[0];
    if (!heads.length || !body || !t.parentNode) return;
    var original = null, state = { col: -1, asc: true }, n = ++sortSeq, names = [], opts = [];
    var controls = el("div", "sort-controls" + (t.classList.contains("responsive") ? " for-responsive" : ""));
    var label = el("label", null, "Sort by"), select = el("select"), dir = el("button", "sort-dir", "Ascending"), said = el("span", "visually-hidden");
    select.id = "sort-" + n;
    label.setAttribute("for", select.id);
    dir.type = "button";
    said.setAttribute("role", "status");
    var none = el("option", null, "Table order");
    none.value = "";
    select.appendChild(none);
    function sortTo(col, asc) {
      if (!original) original = Array.prototype.slice.call(body.rows);
      state = { col: col, asc: asc };
      heads.forEach(function (o, k) { if (k === col) o.setAttribute("aria-sort", asc ? "ascending" : "descending"); else o.removeAttribute("aria-sort"); });
      var rows = col < 0 ? original.filter(function (r) { return r.parentNode === body; }) : Array.prototype.slice.call(body.rows).sort(function (a, b) {
        return compareCells(cellValue(a.cells[col]), cellValue(b.cells[col]), asc);
      });
      rows.forEach(function (r) { body.appendChild(r); });
      select.value = col < 0 ? "" : String(col);
      dir.textContent = asc ? "Ascending" : "Descending";
      said.textContent = col < 0 ? "In table order" : "Sorted by " + names[col] + ", " + (asc ? "ascending" : "descending");
    }
    // Puts th's own content in a button (once); returns false for an empty header.
    function wrap(th, col) {
      if ($("button.sort", th)) return true;
      var text = th.textContent.trim().replace(/\s+/g, " ");
      if (!text) return false;
      names[col] = text;
      var button = el("button", "sort");
      button.type = "button";
      while (th.childNodes.length) button.appendChild(th.childNodes[0]);
      th.appendChild(button);
      th.appendChild(el("span", "th-label", text));
      if (!opts[col]) {
        opts[col] = el("option");
        opts[col].value = String(col);
        select.appendChild(opts[col]);
      }
      opts[col].textContent = text;
      return true;
    }
    heads.forEach(function (th, col) {
      wrap(th, col);
      // On the th (the button's click bubbles here), so the whole cell sorts and a header a page script has rewritten
      // still sorts before the observer gives it its button back.
      th.addEventListener("click", function () { if (names[col]) sortTo(col, !(state.col === col && state.asc)); });
    });
    if (head && typeof MutationObserver === "function") {
      new MutationObserver(function () { heads.forEach(wrap); }).observe(head, { childList: true, subtree: true, characterData: true });
    }
    select.addEventListener("change", function () { sortTo(select.value === "" ? -1 : +select.value, state.asc); });
    dir.addEventListener("click", function () {
      if (state.col >= 0) { sortTo(state.col, !state.asc); return; }
      state.asc = !state.asc;
      dir.textContent = state.asc ? "Ascending" : "Descending";
    });
    controls.appendChild(label);
    controls.appendChild(select);
    controls.appendChild(dir);
    controls.appendChild(said);
    t.parentNode.insertBefore(controls, t);
  });

  // ---------------------------------------------------------------- table filters and pinned rows
  function bodyRows(t) {
    var body = t.tBodies && t.tBodies[0];
    return body ? Array.prototype.slice.call(body.rows) : [];
  }
  function rowUrn(r) {
    var a = r.querySelector("[data-preview]");
    var ref = a ? a.getAttribute("data-preview") || "" : "";
    return ref.indexOf("school:") === 0 ? ref.slice(7) : "";
  }
  // Each filter block applies to the first sortable table after it in the page.
  var filterTargets = [], pendingFilters = [];
  $$("[data-filters], table[data-sortable]").forEach(function (n) {
    if (n.hasAttribute("data-filters")) pendingFilters.push(n);
    else { pendingFilters.forEach(function (f) { filterTargets.push([f, n]); }); pendingFilters = []; }
  });
  filterTargets.forEach(function (pair) {
    var box = pair[0], t = pair[1];
    var count = el("span", "filter-count muted small");
    count.setAttribute("aria-live", "polite");
    box.appendChild(count);
    function apply() {
      var active = {};
      $$("button[data-filter]", box).forEach(function (b) {
        var tag = parseTags(b.getAttribute("data-filter"));
        if (b.getAttribute("aria-pressed") !== "true") return;
        Object.keys(tag).forEach(function (g) { active[g] = (active[g] || []).concat(tag[g]); });
      });
      var rows = bodyRows(t), shown = 0;
      rows.forEach(function (r) {
        var holder = r.querySelector("[data-tags]");
        var ok = rowShown(parseTags(holder ? holder.getAttribute("data-tags") : ""), active);
        r.hidden = !ok;
        if (ok) shown++;
      });
      count.textContent = Object.keys(active).length ? "Showing " + shown + " of " + rows.length : "";
    }
    $$("button[data-filter]", box).forEach(function (b) {
      if (!b.hasAttribute("aria-pressed")) b.setAttribute("aria-pressed", "false");
      b.addEventListener("click", function () {
        b.setAttribute("aria-pressed", b.getAttribute("aria-pressed") === "true" ? "false" : "true");
        apply();
      });
    });
  });
  (function pinnedRows() {
    var pinned = {};
    pins.forEach(function (p) { if (p.type === "school") pinned[String(p.id)] = true; });
    if (!Object.keys(pinned).length) return;
    $$("table[data-sortable]").forEach(function (t) {
      var body = t.tBodies && t.tBodies[0];
      if (!body) return;
      pinnedFirst(bodyRows(t), rowUrn, pinned).forEach(function (r) {
        if (pinned[rowUrn(r)]) r.classList.add("pinned");
        body.appendChild(r);
      });
    });
  })();

  // ---------------------------------------------------------------- compare page (#compare-app)
  (function compare() {
    var app = document.getElementById("compare-app");
    if (!app) return;
    var MAX = pinLimits.school, MAX_AREAS = pinLimits.area;
    var CATS = [["total_income", "Income per pupil"], ["total_expenditure", "Spending per pupil"], ["teaching_staff", "Teachers per pupil"],
      ["education_support_staff", "Support staff per pupil"], ["supply_staff", "Supply staff per pupil"], ["admin_clerical_staff", "Office staff per pupil"],
      ["premises", "Buildings per pupil"], ["energy", "Energy per pupil"], ["educational_supplies", "Learning resources per pupil"]];
    var AREA_ROWS = [["schools", "Schools", "n"], ["in_deficit", "Schools in deficit", "n"], ["in_deficit_pct", "Share in deficit", "pct"],
      ["deficit_total", "Total deficits", "money"], ["deficit_pp", "Deficits per pupil", "money"], ["reserve_median_pp", "Reserve per pupil (median)", "money"],
      ["income_pp_median", "Income per pupil (median)", "money"], ["spend_pp_median", "Spending per pupil (median)", "money"],
      ["grant_pp_median", "Grants per pupil (median)", "money"], ["pta_pp_median", "PTA income per pupil (median)", "money"],
      ["pta_schools", "Schools with a registered PTA", "n"], ["donations_pp_median", "Donations per pupil (median)", "money"]];
    var SERIES = ["var(--c1)", "var(--c2)", "var(--c3)", "var(--c4)", "var(--serious)", "var(--good)"];
    var input = document.getElementById("cmp-find"), results = document.getElementById("cmp-results");
    var chosenList = document.getElementById("cmp-chosen"), out = document.getElementById("cmp-out") || app;
    var chosen = [], areas = [], searchSeq = 0;
    // Results are a plain list of "Compare <school>" buttons with the count in a polite status region (older markup
    // gave the list role="listbox", which buttons can't sit in; build_money now leaves it off and adds #cmp-status).
    var cmpStatus = document.getElementById("cmp-status");
    if (results) {
      if (results.getAttribute("role") === "listbox") results.removeAttribute("role");
      if (!results.hasAttribute("aria-label")) results.setAttribute("aria-label", "Matching schools");
      if (!cmpStatus) {
        cmpStatus = el("p", "visually-hidden");
        cmpStatus.id = "cmp-status";
        cmpStatus.setAttribute("role", "status");
        cmpStatus.setAttribute("aria-live", "polite");
        results.parentNode.insertBefore(cmpStatus, results.nextSibling);
      }
    }
    // Enter in the finder searches (it never submits the page away from the chosen schools).
    var form = input && input.closest ? input.closest("form") : null;
    if (form) form.addEventListener("submit", function (e) { e.preventDefault(); search(input.value); });

    function loadSchool(urn) {
      return fetchJSON("/data/s/" + encodeURIComponent(urn) + ".json").then(function (d) {
        if (!d || typeof d !== "object" || !Array.isArray(d.years)) return { urn: urn, name: "School " + urn, missing: true };
        d.pp = d.pp || {}; d.similar = d.similar || {};
        return d;
      });
    }
    function loadArea(id) {
      return fetchJSON("/data/a/" + encodeURIComponent(id) + ".json").then(function (d) {
        if (!d || typeof d !== "object" || !d.by_year) return { id: id, name: "Area " + id, missing: true };
        return d;
      });
    }
    function syncUrl() {
      var url = new URL(location.href);
      if (chosen.length) url.searchParams.set("urns", chosen.join(",")); else url.searchParams.delete("urns");
      if (areas.length) url.searchParams.set("areas", areas.join(",")); else url.searchParams.delete("areas");
      url.searchParams.delete("q");
      history.replaceState(null, "", url);
    }
    function say(text) { if (cmpStatus) cmpStatus.textContent = text; }
    function search(q) {
      if (!results) return;
      var seq = ++searchSeq;
      results.textContent = "";
      if (!q.trim()) { say(""); return; }
      loadIndex().then(function (rows) {
        if (seq !== searchSeq) return;
        results.textContent = "";
        if (!rows) { results.appendChild(el("li", "muted", "Search is unavailable just now. Try again in a moment.")); say("Search is unavailable just now."); return; }
        var m = searchMatches(rows, q, 12, { types: ["school"] }), hits = m.rows;
        if (!hits.length) { results.appendChild(el("li", "muted", "No schools match.")); say("No schools match."); return; }
        say((m.fuzzy ? "No exact matches. " + hits.length + " close " : hits.length + " ") + (hits.length === 1 ? "school matches" : "schools match")
          + (chosen.length >= MAX ? ". Up to " + MAX + " schools can be compared: remove one to add another." : "."));
        hits.forEach(function (h) {
          var li = el("li");
          var left = el("div");
          left.appendChild(el("strong", null, h.name));
          left.appendChild(el("div", "where", h.sub || ""));
          var right = el("div");
          if (h.status && LABELS[h.status]) right.appendChild(badge(h.status));
          // The button's name is "Compare <school>" (the school's name is visually hidden: it is already beside it).
          var added = chosen.indexOf(String(h.id)) !== -1, add = el("button", null, added ? "Added" : "Compare");
          add.appendChild(el("span", "visually-hidden", " " + h.name));
          add.type = "button";
          add.disabled = added || chosen.length >= MAX;
          add.addEventListener("click", function () { addSchool(String(h.id)); });
          right.appendChild(document.createTextNode(" "));
          right.appendChild(add);
          li.appendChild(left);
          li.appendChild(right);
          results.appendChild(li);
        });
      });
    }
    function addSchool(urn) {
      if (chosen.indexOf(urn) !== -1 || chosen.length >= MAX) return;
      chosen.push(urn);
      syncUrl();
      render();
      if (input && input.value) search(input.value);
    }
    function removeSchool(urn) {
      chosen = chosen.filter(function (u) { return u !== urn; });
      syncUrl();
      render();
    }
    function removeArea(id) {
      areas = areas.filter(function (a) { return a !== id; });
      syncUrl();
      render();
    }
    function chip(name, href, colour, onRemove) {
      var li = el("li");
      if (colour) { var key = el("span", "key dot"); key.style.background = colour; li.appendChild(key); }
      if (href) { var a = el("a", null, name); a.href = href; li.appendChild(a); } else li.appendChild(el("span", "muted", name));
      var x = el("button", null, "×");
      x.type = "button";
      x.setAttribute("aria-label", "Remove " + name);
      x.addEventListener("click", onRemove);
      li.appendChild(x);
      return li;
    }
    function render() {
      Promise.all([Promise.all(chosen.map(loadSchool)), Promise.all(areas.map(loadArea))]).then(function (both) {
        var loaded = both[0], loadedAreas = both[1];
        var schools = loaded.filter(function (s) { return !s.missing; });
        var good = loadedAreas.filter(function (a) { return !a.missing; });
        if (chosenList) {
          chosenList.textContent = "";
          loaded.forEach(function (s) {
            chosenList.appendChild(chip(s.missing ? "No finance data for school " + s.urn : s.name, s.missing ? null : s.path,
              s.missing ? null : SERIES[schools.indexOf(s) % SERIES.length], function () { removeSchool(String(s.urn)); }));
          });
          loadedAreas.forEach(function (a) {
            chosenList.appendChild(chip(a.missing ? "No data for area " + a.id : a.name, a.missing ? null : a.path, null, function () { removeArea(String(a.id)); }));
          });
        }
        out.textContent = "";
        if (!schools.length && !good.length) {
          out.appendChild(el("p", "muted", loaded.length || loadedAreas.length ? "None of the chosen items has data to compare."
            : "Search above to add up to " + MAX + " schools, or pin schools and areas as you browse."));
          return;
        }
        if (schools.length) {
          out.appendChild(el("h2", null, "Schools side by side"));
          out.appendChild(schoolTable(schools));
          // Whose similar schools these are, and how they are chosen (each method once).
          var methods = [];
          schools.forEach(function (s) { var m = s.similar_meta && s.similar_meta.method; if (m && methods.indexOf(String(m)) === -1) methods.push(String(m)); });
          if (methods.length) out.appendChild(el("p", "muted small", "Similar schools are School Money's own comparison groups, not the DfE's. " + methods.join(" ")));
          if (schools.some(function (s) { return s.years.length > 1; })) {
            out.appendChild(el("h2", null, "Reserve as a share of income, by year"));
            out.appendChild(chart(schools));
          }
        }
        if (good.length) {
          out.appendChild(el("h2", null, "Areas side by side"));
          out.appendChild(areaTable(good));
        }
        enhanceFigures(out);
      });
    }
    function mkTable(cols) {
      var wrap = el("div", "cmp-table");
      var t = el("table", "responsive");
      var head = t.createTHead().insertRow();
      head.appendChild(el("th", null, ""));
      cols.forEach(function (c) { var th = el("th", null, c); th.scope = "col"; head.appendChild(th); });
      var body = t.createTBody();
      wrap.appendChild(t);
      return { wrap: wrap, row: function (label, fn) {
        var r = body.insertRow();
        var th = el("th", null, label);
        th.scope = "row";
        r.appendChild(th);
        cols.forEach(function (c, i) {
          var td = r.insertCell();
          td.setAttribute("data-label", c);
          var v = fn(i);
          if (v instanceof Node) td.appendChild(v); else td.textContent = v;
        });
      } };
    }
    function schoolTable(schools) {
      var t = mkTable(schools.map(function (s) { return s.name; }));
      function at(i) { return schools[i]; }
      t.row("Status", function (i) { var s = at(i); return LABELS[s.status] ? badge(s.status) : "—"; });
      t.row("Why", function (i) { return at(i).reason || "—"; });
      t.row("Council", function (i) { var c = at(i).council; return c ? (typeof c === "string" ? c : c.name || "—") : "—"; });
      t.row("Latest year", function (i) { var s = at(i); return (s.year || "—") + (s.academy ? " (academy)" : ""); });
      t.row("Pupils", function (i) { var p = at(i).pupils; return p == null ? "—" : Math.round(p).toLocaleString("en-GB"); });
      // The reserve on the basis the school's status uses: for an academy in a trust that pools reserves, its share of
      // the trust's reserve is included and the row says so (reserve_basis; without it, today's wording).
      t.row("Reserve", function (i) {
        var s = at(i), trust = s.reserve_basis === "incl_trust_share";
        var span = figureSpan(trust ? "revenue_reserve_incl_trust_share" : "revenue_reserve", s.reserve, s.reserve_pp, s.year,
          trust ? "Reserve, including its share of the trust's reserve" : null, s.check);
        if (!trust) return span;
        var box = el("span");
        box.appendChild(span);
        box.appendChild(el("small", "basis", " including its share of the trust's reserve"));
        return box;
      });
      t.row("Reserve as % of income", function (i) { var s = at(i); return s.share == null ? "—" : (s.share * 100).toFixed(1) + "%"; });
      t.row("Last year's balance", function (i) { var s = at(i); return figureSpan("in_year_balance", s.balance, s.balance_pp, s.year, null, s.check, { signed: true }); });
      t.row("Years spending more than income", function (i) { var s = at(i); return s.streak ? String(s.streak) : "—"; });
      t.row("Pupils since first year", function (i) { var s = at(i); return s.pupils_change == null ? "—" : (s.pupils_change > 0 ? "+" : "") + Math.round(s.pupils_change * 100) + "%"; });
      // Per-pupil categories are money figures too (tooltip, drill-down). The shared school JSON carries
      // totals only for income and spending; other categories keep data-v empty rather than guess.
      var TOTALS = { total_income: "income", total_expenditure: "spend" };
      // School Money's own similar schools (similar_meta: the year and how many schools had a return that year); the
      // medians below are for that year, which is each school's own latest year.
      if (schools.some(function (s) { return s.similar_meta; })) {
        t.row("Compared with", function (i) { return similarWords(at(i)); });
      }
      CATS.forEach(function (c) {
        t.row(c[1], function (i) {
          var s = at(i), pp = s.pp[c[0]];
          if (typeof pp !== "number") return "—";
          var total = TOTALS[c[0]] ? s[TOTALS[c[0]]] : null, m = s.similar[c[0]];
          var span = figureSpan(c[0], total, pp, s.year, null, s.check, { ppFirst: true, similar: typeof m === "number" ? m : null });
          if (typeof m === "number") { span.appendChild(document.createTextNode(" ")); span.appendChild(el("small", null, similarWords(s) + " " + fmtExact(m))); }
          return span;
        });
      });
      t.row("Check at source", function (i) { var s = at(i); if (!s.check) return "—"; var a = el("a", null, "DfE benchmarking"); a.href = s.check; a.rel = "noopener"; return a; });
      return t.wrap;
    }
    // "similar schools (17 schools, 2025-26)" from similar_meta, else "similar schools".
    function similarWords(s) {
      var meta = s && s.similar_meta;
      if (!meta || typeof meta !== "object" || !meta.year) return "similar schools";
      var n = typeof meta.peers === "number" && isFinite(meta.peers) ? Math.round(meta.peers) : null;
      return "similar schools (" + (n == null ? "" : n.toLocaleString("en-GB") + (n === 1 ? " school, " : " schools, ")) + meta.year + ")";
    }
    function areaTable(list) {
      var years = {};
      list.forEach(function (a) { Object.keys(a.by_year || {}).forEach(function (y) { years[y] = true; }); });
      var ys = Object.keys(years).sort(), year = ys[ys.length - 1];
      var t = mkTable(list.map(function (a) { return a.name; }));
      t.row("Year", function () { return year || "—"; });
      AREA_ROWS.forEach(function (r) {
        t.row(r[1], function (i) {
          var S = list[i].by_year && list[i].by_year[year] && list[i].by_year[year].all;
          var v = S ? S[r[0]] : null;
          if (v == null) return "—";
          if (r[2] === "pct") return v.toFixed(1) + "%";
          if (r[2] === "money") return fmtExact(v, r[0] === "reserve_median_pp");
          return Math.round(v).toLocaleString("en-GB");
        });
      });
      // The council's Dedicated Schools Grant balance (all four blocks), with its own year (the latest it has, which can
      // differ from the schools' year) and "provisional" where the source says so.
      t.row("Dedicated Schools Grant balance (all four blocks)", function (i) {
        var dsg = list[i].dsg || {}, y = dsg[year] && dsg[year].balance != null ? year : null;
        if (!y) Object.keys(dsg).sort().forEach(function (k) { if (dsg[k] && dsg[k].balance != null) y = k; });
        if (!y) return "—";
        var d = dsg[y], pp = isNum(d.per_pupil) ? d.per_pupil : isNum(d.balance_pp) ? d.balance_pp : null, box = el("span", null, fmtMoney(d.balance, true));
        var note = y + (d.provisional ? ", provisional" : "") + (pp != null ? "; " + fmtExact(pp, true) + " per pupil at the council's schools on this site" : "");
        box.appendChild(el("small", null, " (" + note + ")"));
        return box;
      });
      return t.wrap;
    }
    function chart(schools) {
      var NS = "http://www.w3.org/2000/svg", W = 640, H = 220, L = 48, R = 12, T = 12, B = 26;
      var labels = [];
      schools.forEach(function (s) { s.years.forEach(function (y) { if (y && y.y && labels.indexOf(y.y) === -1) labels.push(y.y); }); });
      labels.sort();
      function share(y) { return y && typeof y.income === "number" && y.income > 0 && typeof y.reserve === "number" ? y.reserve / y.income * 100 : null; }
      var vals = [];
      schools.forEach(function (s) { s.years.forEach(function (y) { var v = share(y); if (v != null) vals.push(v); }); });
      var lo = Math.min(0, Math.min.apply(null, vals.concat([0]))), hi = Math.max(5, Math.max.apply(null, vals.concat([5])));
      var step = (hi - lo) > 40 ? 10 : 5;
      lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
      function x(i) { return L + (labels.length < 2 ? 0 : i * (W - L - R) / (labels.length - 1)); }
      function y(v) { return T + (hi - v) / (hi - lo) * (H - T - B); }
      var svg = document.createElementNS(NS, "svg");
      svg.setAttribute("viewBox", "0 0 " + W + " " + H);
      svg.setAttribute("class", "chart");
      svg.setAttribute("role", "img");
      svg.setAttribute("aria-label", "Reserve as a share of income by year for the chosen schools; the same figures are in the table above");
      function add(tag, attrs, text) {
        var e = document.createElementNS(NS, tag);
        Object.keys(attrs).forEach(function (k) { e.setAttribute(k, attrs[k]); });
        if (text != null) e.textContent = text;
        svg.appendChild(e);
        return e;
      }
      for (var v = lo; v <= hi; v += step) {
        add("line", { "class": v === 0 ? "axis" : "grid", x1: L, x2: W - R, y1: y(v), y2: y(v) });
        add("text", { "class": "tick", x: L - 6, y: y(v) + 4, "text-anchor": "end" }, v + "%");
      }
      labels.forEach(function (lab, i) { add("text", { "class": "tick", x: x(i), y: H - 8, "text-anchor": "middle" }, lab); });
      schools.forEach(function (s, si) {
        var pts = s.years.map(function (yr) { return [labels.indexOf(yr && yr.y), share(yr), yr && yr.y]; }).filter(function (p) { return p[0] >= 0 && p[1] != null; });
        if (!pts.length) return;
        var path = add("path", { "class": "line", d: "M" + pts.map(function (p) { return x(p[0]).toFixed(1) + "," + y(p[1]).toFixed(1); }).join("L") });
        path.style.stroke = SERIES[si % SERIES.length];
        pts.forEach(function (p) {
          var g = add("g", { "class": "mark", tabindex: "0", "data-tip": s.name + ", " + p[2] + ": " + p[1].toFixed(1) + "% of income" });
          var c = document.createElementNS(NS, "circle");
          c.setAttribute("cx", x(p[0])); c.setAttribute("cy", y(p[1])); c.setAttribute("r", "4"); c.setAttribute("class", "ring");
          c.style.fill = SERIES[si % SERIES.length];
          g.appendChild(c);
          var hit = document.createElementNS(NS, "circle");
          hit.setAttribute("cx", x(p[0])); hit.setAttribute("cy", y(p[1])); hit.setAttribute("r", "12"); hit.setAttribute("class", "hit");
          g.appendChild(hit);
        });
      });
      var box = el("div");
      var legend = el("p", "legend");
      schools.forEach(function (s, i) {
        var k = el("span", "key line");
        k.style.background = SERIES[i % SERIES.length];
        legend.appendChild(k);
        legend.appendChild(document.createTextNode(s.name + "  "));
      });
      box.appendChild(legend);
      box.appendChild(svg);
      return box;
    }

    if (input) input.addEventListener("input", function () { search(input.value); });
    var params = new URLSearchParams(location.search);
    (params.get("urns") || "").split(",").filter(function (u) { return /^\d+$/.test(u); }).slice(0, MAX).forEach(function (u) { if (chosen.indexOf(u) === -1) chosen.push(u); });
    (params.get("areas") || "").split(",").filter(function (a) { return /^[a-z0-9-]+$/.test(a); }).slice(0, MAX_AREAS).forEach(function (a) { if (areas.indexOf(a) === -1) areas.push(a); });
    if (!chosen.length && !areas.length) {
      pins.forEach(function (p) { if (p.type === "school" && chosen.length < MAX) chosen.push(p.id); else if (p.type === "area" && areas.length < MAX_AREAS) areas.push(p.id); });
    }
    if (input && params.get("q")) { input.value = params.get("q"); search(input.value); }
    render();
  })();
})(typeof globalThis !== "undefined" ? globalThis : this);
