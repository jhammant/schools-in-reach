/* School Money — app.js. Defer-loaded; every page works without it.
   Pure helpers are exported as globalThis.MoneyApp (loadable under node for tests); DOM wiring
   runs only in a browser. All data goes through textContent: no HTML built from strings of data.

   Reads: /assets/glossary.json, /data/search.json, /data/s/<urn>.json, /data/a/<id>.json,
          /data/postcodes/<district>.json (optional, 404 = no suggestions).
   Stores: localStorage moneyAudience ("parent"|...), moneyPinned ([{type,id,name,p}]).
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
  // Ranking: name prefix > every query word is a word prefix in the name > substring (name or sub);
  // ties broken by type (school, council, constituency, trust), then shorter name, then index order.
  function rankSearch(rows, q, limit) {
    limit = limit || 8;
    var needle = norm(q).trim().replace(/\s+/g, " ");
    if (!needle || !Array.isArray(rows)) return [];
    var words = needle.split(" ");
    var hits = [];
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      if (!r || !r.name) continue;
      var name = norm(r.name), sub = norm(r.sub), score = 0;
      if (name.indexOf(needle) === 0) score = 3;
      else {
        var tokens = name.split(/[^a-z0-9]+/);
        if (words.every(function (w) { return tokens.some(function (t) { return t.indexOf(w) === 0; }); })) score = 2;
        else if (name.indexOf(needle) !== -1 || (name + " " + sub).indexOf(needle) !== -1) score = 1;
      }
      if (score) hits.push({ row: r, score: score, i: i, name: name });
    }
    hits.sort(function (a, b) {
      return b.score - a.score
        || (TYPE_ORDER[a.row.t] == null ? 9 : TYPE_ORDER[a.row.t]) - (TYPE_ORDER[b.row.t] == null ? 9 : TYPE_ORDER[b.row.t])
        || a.name.length - b.name.length
        || a.i - b.i;
    });
    return hits.slice(0, limit).map(function (h) { return h.row; });
  }
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
  function postcodeLookup(district) {
    var d = String(district || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
    if (!d || typeof fetch !== "function") return Promise.resolve(null);
    return fetch("/data/postcodes/" + encodeURIComponent(d) + ".json").then(function (r) {
      if (!r.ok) return null;
      return r.json();
    }).catch(function () { return null; });
  }

  var API = {
    fmtMoney: fmtMoney, perPupil: perPupil, parsePostcode: parsePostcode, rankSearch: rankSearch,
    pinLimits: pinLimits, togglePin: togglePin, importShortlist: importShortlist, postcodeLookup: postcodeLookup,
    slugify: slugify
  };
  root.MoneyApp = API;
  if (typeof document === "undefined") return;

  // ======================================================================
  // DOM wiring
  // ======================================================================
  var LABELS = { in_deficit: "In deficit", heading_for_deficit: "Heading for deficit", tight: "Tight", healthy: "Healthy", large_reserves: "Large reserves" };
  var ICONS = { in_deficit: "▼", heading_for_deficit: "↘", tight: "●", healthy: "✓", large_reserves: "▲" };
  var KEY_AUD = "moneyAudience", KEY_PIN = "moneyPinned";
  var AUDIENCES = ["parent", "governor", "ptfa", "leader", "pupil"];

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

  // ---------------------------------------------------------------- audience
  (function audience() {
    var current = storeGet(KEY_AUD, null);
    if (AUDIENCES.indexOf(current) === -1) current = document.documentElement.getAttribute("data-audience") || "parent";
    function apply(a) {
      document.documentElement.setAttribute("data-audience", a);
      $$("[data-audience]").forEach(function (b) {
        if (b.tagName === "BUTTON") b.setAttribute("aria-pressed", b.getAttribute("data-audience") === a ? "true" : "false");
      });
    }
    apply(current);
    document.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("button[data-audience]");
      if (!b) return;
      var a = b.getAttribute("data-audience");
      if (AUDIENCES.indexOf(a) === -1) return;
      storeSet(KEY_AUD, a);
      apply(a);
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
    return {
      key: key,
      label: mf.getAttribute("data-label") || g.label || key.replace(/_/g, " "),
      v: num(mf.getAttribute("data-v")),
      pp: num(mf.getAttribute("data-pp")),
      year: mf.getAttribute("data-year") || "",
      src: mf.getAttribute("data-src") || "",
      similar: num(mf.getAttribute("data-cmp-similar")),
      england: num(mf.getAttribute("data-cmp-england")),
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
    var row = el("div", "row");
    row.appendChild(el("span", null, "Total"));
    row.appendChild(el("span", "num", fmtExact(d.v, d.signed)));
    tip.appendChild(row);
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
    drill.hidden = true;
    backdrop.hidden = true;
    drillStack = [];
    document.body.style.overflow = "";
    if (drillOpener && drillOpener.focus) drillOpener.focus();
    drillOpener = null;
  }
  function sparkline(series) {
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
    svg.setAttribute("aria-label", pts.map(function (p) { return p.y + ": " + fmtMoney(p.v); }).join(", "));
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
  function figureSpan(key, v, pp, year, label, src) {
    var s = el("span", "mf", fmtMoney(v));
    s.setAttribute("data-mf", key || "cfr_line");
    s.setAttribute("data-v", v == null ? "" : String(v));
    if (pp != null) s.setAttribute("data-pp", String(pp));
    s.setAttribute("data-year", year || "");
    if (label) s.setAttribute("data-label", label);
    if (src) s.setAttribute("data-src", src);
    if (pp != null) { s.appendChild(document.createTextNode(" ")); s.appendChild(el("small", null, fmtExact(pp) + " per pupil")); }
    return s;
  }
  function renderDrill(d, data) {
    drill.textContent = "";
    var head = el("header");
    var h2 = el("h2", null, (data && data.title) || d.label);
    h2.id = "drill-title";
    head.appendChild(h2);
    var close = el("button", "close", "×");
    close.type = "button";
    close.setAttribute("aria-label", "Close");
    close.addEventListener("click", closeDrill);
    head.appendChild(close);
    drill.appendChild(head);
    if (drillStack.length > 1) {
      var back = el("button", "button quiet", "‹ Back");
      back.type = "button";
      back.addEventListener("click", function () { drillStack.pop(); var prev = drillStack[drillStack.length - 1]; renderDrill(prev.d, prev.data); });
      drill.appendChild(back);
    }
    var year = (data && data.year) || d.year;
    if (year) drill.appendChild(el("p", "year", year));
    var headline = el("p", "headline", fmtExact(d.v, d.signed));
    if (d.pp != null) headline.appendChild(el("small", null, fmtExact(d.pp, d.signed) + " per pupil"));
    drill.appendChild(headline);
    var s = compareText(d.pp, d.similar, "similar schools"), e = compareText(d.pp, d.england, "England");
    if (s || e) {
      drill.appendChild(el("h3", null, "Compared with"));
      var cmp = el("div", "cmp");
      if (s) { cmp.appendChild(el("span", null, "Similar schools")); cmp.appendChild(el("span", null, s)); }
      if (e) { cmp.appendChild(el("span", null, "England")); cmp.appendChild(el("span", null, e)); }
      drill.appendChild(cmp);
    }
    var spark = data && sparkline(data.series);
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
        var td = tr.insertCell();
        td.appendChild(figureSpan(r.key, r.v, r.pp, year, r.label, data.src));
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
  function openDrill(mf) {
    buildDrill();
    hideTip();
    var inPanel = drill.contains(mf);
    if (!inPanel) { drillOpener = mf; drillStack = []; }
    drill.hidden = false;
    backdrop.hidden = false;
    document.body.style.overflow = "hidden";
    loadGlossary().then(function () {
      var d = figureData(mf);
      var ref = d.drill;
      var loader;
      if (ref && ref.charAt(0) === "#") {
        var script = document.getElementById(ref.slice(1));
        var inline = null;
        try { inline = script ? JSON.parse(script.textContent) : null; } catch (err) { inline = null; }
        loader = Promise.resolve(inline);
      } else if (ref) loader = fetchJSON(ref);
      else loader = Promise.resolve(null);
      loader.then(function (data) {
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
  var indexPromise = null;
  function loadIndex() {
    if (!indexPromise) indexPromise = fetchJSON("/data/search.json").then(function (d) { return Array.isArray(d) ? d : []; });
    return indexPromise;
  }
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
    var sl = storeGet("shortlist", null), pl = storeGet("plan", null);
    [["shortlist", sl], ["plan", pl]].forEach(function (pair) {
      if (!Array.isArray(pair[1]) || !pair[1].length) return;
      var btn = el("button", null, "Import Schools in Reach " + pair[0] + " (" + pair[1].length + ")");
      btn.type = "button";
      btn.addEventListener("click", function () {
        loadIndex().then(function (rows) {
          var r = importShortlist(pins, pair[1], schoolLookup(rows));
          pins = r.list;
          pinMsg = r.added ? "Added " + r.added + " from your " + pair[0] + "." : "Nothing new to add from your " + pair[0] + ".";
          if (r.skipped) pinMsg += " " + r.skipped + " left out: up to " + pinLimits.school + " schools can be pinned.";
          if (r.unknown) pinMsg += " " + r.unknown + " without a money page.";
          refreshPins();
        });
      });
      pinbar.appendChild(btn);
    });
    if (msg) {
      var m = el("span", "msg", msg);
      m.setAttribute("aria-live", "polite");
      pinbar.appendChild(m);
    }
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

  // ---------------------------------------------------------------- global search (#q)
  (function search() {
    var input = document.getElementById("q");
    if (!input) return;
    var list = document.getElementById("q-list");
    if (!list) {
      list = el("ul", "listbox");
      list.id = "q-list";
      list.setAttribute("role", "listbox");
      list.hidden = true;
      input.parentNode.appendChild(list);
    }
    input.setAttribute("aria-controls", list.id);
    var options = [], active = -1, timer = null, lastQuery = "";
    function hide() { list.hidden = true; list.textContent = ""; options = []; active = -1; input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); }
    function setActive(i) {
      active = i;
      options.forEach(function (o, k) { o.setAttribute("aria-selected", k === i ? "true" : "false"); });
      if (i >= 0) { input.setAttribute("aria-activedescendant", options[i].id); options[i].scrollIntoView({ block: "nearest" }); }
      else input.removeAttribute("aria-activedescendant");
    }
    function normalisePostcodeRows(d) {
      var rows = Array.isArray(d) ? d : (d && (d.schools || d.results || d.rows)) || [];
      return rows.map(function (r) {
        if (!r) return null;
        var id = r.id != null ? r.id : r.urn;
        return { t: r.t || "school", id: id, name: r.name || ("School " + id), sub: r.sub || [r.town, r.postcode].filter(Boolean).join(" "),
          status: r.status || null, p: r.p || ("/school/" + id + "-" + slugify(r.name || "") + "/") };
      }).filter(Boolean).slice(0, 10);
    }
    function render(rows, note) {
      list.textContent = "";
      options = [];
      if (!rows.length) {
        if (note) list.appendChild(el("li", "empty", note));
        else { hide(); return; }
      }
      rows.forEach(function (r, i) {
        var li = el("li");
        li.id = "q-opt-" + i;
        li.setAttribute("role", "option");
        li.setAttribute("aria-selected", "false");
        li.appendChild(el("span", "kind", r.t || ""));
        li.appendChild(el("span", "name", r.name || ""));
        if (r.status && LABELS[r.status]) li.appendChild(badge(r.status));
        if (r.sub) li.appendChild(el("span", "sub", r.sub));
        li.addEventListener("mousedown", function (e) { e.preventDefault(); });
        li.addEventListener("click", function () { if (r.p) location.href = r.p; });
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
      if (q.length < 2) { hide(); return; }
      var pc = parsePostcode(q);
      if (pc && /\d/.test(q)) {
        Promise.resolve(API.postcodeLookup(pc.district)).then(function (d) {
          if (lastQuery !== q) return;
          if (!d) { hide(); return; }
          render(normalisePostcodeRows(d), "No schools near " + pc.district);
        });
        return;
      }
      loadIndex().then(function (rows) {
        if (lastQuery !== q) return;
        render(rankSearch(rows, q, 8), "No matches");
      });
    }
    input.addEventListener("focus", function () { loadIndex(); });
    input.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(run, 80); });
    input.addEventListener("keydown", function (e) {
      if (list.hidden && (e.key === "ArrowDown") && input.value.trim()) { run(); return; }
      if (list.hidden) return;
      if (e.key === "ArrowDown") { e.preventDefault(); setActive(options.length ? (active + 1) % options.length : -1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); setActive(options.length ? (active - 1 + options.length) % options.length : -1); }
      else if (e.key === "Enter" && active >= 0) { e.preventDefault(); options[active].click(); }
      else if (e.key === "Escape") { hide(); }
    });
    input.addEventListener("blur", function () { setTimeout(hide, 120); });
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
    document.addEventListener("pointerover", function (e) {
      if (e.pointerType === "touch") return;
      var t = e.target.closest && e.target.closest("[data-preview]");
      if (!t || t === cardFor) return;
      clearTimeout(timer);
      timer = setTimeout(function () { show(t); }, 150);
    });
    document.addEventListener("pointerout", function (e) {
      var t = e.target.closest && e.target.closest("[data-preview]");
      if (t && !(e.relatedTarget && t.contains(e.relatedTarget))) hide();
    });
    document.addEventListener("focusin", function (e) {
      var t = e.target.closest && e.target.closest("[data-preview]");
      if (t) show(t);
    });
    document.addEventListener("focusout", hide);
    document.addEventListener("click", function (e) {
      var t = e.target.closest && e.target.closest("[data-preview]");
      if (t && t.tagName !== "A" && !t.closest("a")) { if (cardFor === t) hide(); else show(t); }
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
  $$("table[data-sortable]").forEach(function (t) {
    $$("thead th", t).forEach(function (th, col) {
      th.tabIndex = 0;
      function sort() {
        var asc = th.getAttribute("aria-sort") !== "ascending";
        $$("thead th", t).forEach(function (o) { o.removeAttribute("aria-sort"); });
        th.setAttribute("aria-sort", asc ? "ascending" : "descending");
        var body = t.tBodies[0];
        var rows = Array.prototype.slice.call(body.rows);
        rows.sort(function (a, b) { return compareCells(cellValue(a.cells[col]), cellValue(b.cells[col]), asc); });
        rows.forEach(function (r) { body.appendChild(r); });
      }
      th.addEventListener("click", sort);
      th.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sort(); } });
    });
  });

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
    var chosen = [], areas = [];

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
    function search(q) {
      if (!results) return;
      results.textContent = "";
      if (!q.trim()) return;
      loadIndex().then(function (rows) {
        var hits = rankSearch(rows.filter(function (r) { return r.t === "school"; }), q, 12);
        results.textContent = "";
        if (!hits.length) { results.appendChild(el("li", "muted", "No schools match.")); return; }
        hits.forEach(function (h) {
          var li = el("li");
          var left = el("div");
          left.appendChild(el("strong", null, h.name));
          left.appendChild(el("div", "where", h.sub || ""));
          var right = el("div");
          if (h.status && LABELS[h.status]) right.appendChild(badge(h.status));
          var add = el("button", null, chosen.indexOf(String(h.id)) === -1 ? "Compare" : "Added");
          add.type = "button";
          add.disabled = chosen.indexOf(String(h.id)) !== -1 || chosen.length >= MAX;
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
      t.row("Reserve", function (i) { var s = at(i); return figureSpan("revenue_reserve", s.reserve, s.reserve_pp, s.year, null, s.check); });
      t.row("Reserve as % of income", function (i) { var s = at(i); return s.share == null ? "—" : (s.share * 100).toFixed(1) + "%"; });
      t.row("Last year's balance", function (i) { var s = at(i); return fmtMoney(s.balance, true); });
      t.row("Years spending more than income", function (i) { var s = at(i); return s.streak ? String(s.streak) : "—"; });
      t.row("Pupils since first year", function (i) { var s = at(i); return s.pupils_change == null ? "—" : (s.pupils_change > 0 ? "+" : "") + Math.round(s.pupils_change * 100) + "%"; });
      CATS.forEach(function (c) {
        t.row(c[1], function (i) {
          var s = at(i), v = s.pp[c[0]];
          if (typeof v !== "number") return "—";
          var m = s.similar[c[0]];
          return fmtExact(v) + (typeof m === "number" ? " (similar schools " + fmtExact(m) + ")" : "");
        });
      });
      t.row("Check at source", function (i) { var s = at(i); if (!s.check) return "—"; var a = el("a", null, "DfE benchmarking"); a.href = s.check; a.rel = "noopener"; return a; });
      return t.wrap;
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
      t.row("Council schools budget (DSG) balance", function (i) {
        var d = list[i].dsg && list[i].dsg[year];
        return d && d.balance != null ? fmtMoney(d.balance, true) : "—";
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
