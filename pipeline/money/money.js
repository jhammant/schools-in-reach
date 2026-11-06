// Money section: hover/focus tooltips, sortable tables and the compare tool.
// Copied to site/money/ by pipeline/money/build_money.py. School names are data: textContent only.
(function () {
  "use strict";

  // ---- tooltips: any [data-tip] element, on hover and on keyboard focus
  var tip = document.createElement("div");
  tip.className = "money-tip";
  tip.hidden = true;
  document.body.appendChild(tip);
  function show(el, x, y) {
    tip.textContent = el.getAttribute("data-tip");
    tip.hidden = false;
    var r = tip.getBoundingClientRect();
    var left = Math.min(Math.max(8, x + 12), window.innerWidth - r.width - 8);
    var top = y - r.height - 12 < 8 ? y + 16 : y - r.height - 12;
    tip.style.left = left + "px";
    tip.style.top = top + "px";
  }
  document.addEventListener("pointermove", function (e) {
    var el = e.target.closest && e.target.closest("[data-tip]");
    if (el) show(el, e.clientX, e.clientY); else tip.hidden = true;
  });
  document.addEventListener("focusin", function (e) {
    var el = e.target.closest && e.target.closest("[data-tip]");
    if (!el) return;
    var r = el.getBoundingClientRect();
    show(el, r.left + r.width / 2, r.top);
  });
  document.addEventListener("focusout", function () { tip.hidden = true; });

  // ---- sortable tables: cells may carry data-sort with a raw value
  function cellValue(td) {
    if (!td) return "";
    var raw = td.querySelector("[data-sort]");
    if (raw) {
      var n = parseFloat(raw.getAttribute("data-sort"));
      if (isFinite(n)) return n;
    }
    return td.textContent.trim().toLowerCase();
  }
  // Numbers sort before text in either direction, so "n/a" cells sit together at the end.
  function compareCells(x, y, asc) {
    var xn = typeof x === "number", yn = typeof y === "number";
    if (xn && yn) return asc ? x - y : y - x;
    if (xn !== yn) return xn ? -1 : 1;
    var c = String(x).localeCompare(String(y));
    return asc ? c : -c;
  }
  document.querySelectorAll("table[data-sortable]").forEach(function (t) {
    t.querySelectorAll("thead th").forEach(function (th, col) {
      th.tabIndex = 0;
      function sort() {
        var asc = th.getAttribute("aria-sort") !== "ascending";
        t.querySelectorAll("thead th").forEach(function (o) { o.removeAttribute("aria-sort"); });
        th.setAttribute("aria-sort", asc ? "ascending" : "descending");
        var body = t.tBodies[0];
        var rows = Array.prototype.slice.call(body.rows);
        rows.sort(function (a, b) {
          return compareCells(cellValue(a.cells[col]), cellValue(b.cells[col]), asc);
        });
        rows.forEach(function (r) { body.appendChild(r); });
      }
      th.addEventListener("click", sort);
      th.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sort(); } });
    });
  });

  // ---- compare tool
  var app = document.getElementById("compare-app");
  if (!app) return;
  var MAX = 4;
  var LABELS = {in_deficit: "In deficit", heading_for_deficit: "Heading for deficit", tight: "Tight", healthy: "Healthy", large_reserves: "Large reserves"};
  var ICONS = {in_deficit: "▼", heading_for_deficit: "↘", tight: "●", healthy: "✓", large_reserves: "▲"};
  var CATS = [["total_income", "Income per pupil"], ["total_expenditure", "Spending per pupil"], ["teaching_staff", "Teachers per pupil"],
    ["education_support_staff", "Support staff per pupil"], ["supply_staff", "Supply staff per pupil"], ["admin_clerical_staff", "Admin per pupil"],
    ["premises", "Premises per pupil"], ["energy", "Energy per pupil"], ["educational_supplies", "Learning resources per pupil"]];
  var SERIES = ["var(--c1)", "var(--c2)", "var(--c3)", "var(--c4)"];
  var input = document.getElementById("cmp-find");
  var results = document.getElementById("cmp-results");
  var chosenList = document.getElementById("cmp-chosen");
  var out = document.getElementById("cmp-out");
  var index = null, chosen = [], cache = {};

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function money(v, signed) {
    if (v == null) return "—";
    var s = v < 0 ? "-" : (signed && v > 0 ? "+" : ""), a = Math.abs(v);
    if (a >= 1e6) return s + "£" + (a / 1e6).toFixed(1) + "m";
    if (a >= 1e3) return s + "£" + Math.round(a / 1e3) + "k";
    return s + "£" + Math.round(a);
  }
  function badge(status) {
    var b = el("span", "badge small s-" + status);
    var i = el("span", null, ICONS[status]);
    i.setAttribute("aria-hidden", "true");
    b.appendChild(i);
    b.appendChild(document.createTextNode(" " + LABELS[status]));
    return b;
  }
  function loadIndex() {
    if (index) return Promise.resolve(index);
    return fetch("/money/data/index.json").then(function (r) { return r.json(); }).then(function (d) { index = d; return d; });
  }
  function loadSchool(urn) {
    if (cache[urn]) return Promise.resolve(cache[urn]);
    return fetch("/money/data/s/" + encodeURIComponent(urn) + ".json").then(function (r) {
      if (!r.ok) throw new Error("not found");
      return r.json();
    }).then(function (d) {
      if (!d || typeof d !== "object" || !Array.isArray(d.years) || !d.pp) throw new Error("bad data");
      d.similar = d.similar || {};
      cache[urn] = d;
      return d;
    }).catch(function () {
      // Keep the URN in the list with a message; the other schools still render.
      return {urn: urn, name: "School " + urn, missing: true};
    });
  }
  function search(q) {
    var words = q.toLowerCase().split(/\s+/).filter(Boolean);
    results.textContent = "";
    if (!words.length) return;
    loadIndex().then(function (rows) {
      var hits = [];
      for (var i = 0; i < rows.length && hits.length < 12; i++) {
        var hay = (rows[i][1] + " " + rows[i][2] + " " + rows[i][3]).toLowerCase();
        if (words.every(function (w) { return hay.indexOf(w) !== -1; })) hits.push(rows[i]);
      }
      results.textContent = "";
      if (!hits.length) { results.appendChild(el("li", "muted", "No schools match.")); return; }
      hits.forEach(function (h) {
        var li = el("li");
        li.setAttribute("role", "option");
        var left = el("div");
        left.appendChild(el("strong", null, h[1]));
        left.appendChild(el("div", "where", [h[2], h[3]].filter(Boolean).join(" · ")));
        var right = el("div");
        right.appendChild(badge(h[4]));
        var add = el("button", null, chosen.indexOf(h[0]) === -1 ? "Compare" : "Added");
        add.type = "button";
        add.disabled = chosen.indexOf(h[0]) !== -1 || chosen.length >= MAX;
        add.addEventListener("click", function () { addSchool(h[0]); });
        right.appendChild(document.createTextNode(" "));
        right.appendChild(add);
        li.appendChild(left);
        li.appendChild(right);
        results.appendChild(li);
      });
    });
  }
  function syncUrl() {
    var url = new URL(location.href);
    if (chosen.length) url.searchParams.set("urns", chosen.join(",")); else url.searchParams.delete("urns");
    url.searchParams.delete("q");
    history.replaceState(null, "", url);
  }
  function addSchool(urn) {
    if (chosen.indexOf(urn) !== -1 || chosen.length >= MAX) return;
    chosen.push(urn);
    syncUrl();
    render();
    if (input.value) search(input.value);
  }
  function removeSchool(urn) {
    chosen = chosen.filter(function (u) { return u !== urn; });
    syncUrl();
    render();
  }
  function render() {
    Promise.all(chosen.map(loadSchool)).then(function (loaded) {
      var schools = loaded.filter(function (s) { return !s.missing; });
      chosenList.textContent = "";
      loaded.forEach(function (s) {
        var li = el("li");
        if (s.missing) {
          li.appendChild(el("span", "muted", "No finance data for school " + s.urn));
        } else {
          var key = el("span", "key dot");
          key.style.background = SERIES[schools.indexOf(s)];
          li.appendChild(key);
          var a = el("a", null, s.name);
          a.href = s.path;
          li.appendChild(a);
        }
        var x = el("button", null, "×");
        x.type = "button";
        x.setAttribute("aria-label", "Remove " + s.name);
        x.addEventListener("click", function () { removeSchool(s.urn); });
        li.appendChild(x);
        chosenList.appendChild(li);
      });
      out.textContent = "";
      if (!schools.length) {
        out.appendChild(el("p", "muted", loaded.length ? "None of the chosen schools has finance data to compare." : "Search above to add up to four schools."));
        return;
      }
      out.appendChild(el("h2", null, "Side by side"));
      out.appendChild(table(schools));
      if (schools.some(function (s) { return s.years.length > 1; })) {
        out.appendChild(el("h2", null, "Reserve as a share of income, by year"));
        out.appendChild(chart(schools));
      }
    });
  }
  function table(schools) {
    var wrap = el("div", "cmp-table");
    var t = el("table", "responsive");
    var head = t.createTHead().insertRow();
    head.appendChild(el("th", null, ""));
    schools.forEach(function (s) { var th = el("th", null, s.name); th.scope = "col"; head.appendChild(th); });
    var body = t.createTBody();
    function row(label, fn) {
      var r = body.insertRow();
      var th = el("th", null, label);
      th.scope = "row";
      r.appendChild(th);
      schools.forEach(function (s) {
        var td = r.insertCell();
        td.setAttribute("data-label", s.name);
        var v = fn(s);
        if (v instanceof Node) td.appendChild(v); else td.textContent = v;
      });
    }
    row("Status", function (s) { return LABELS[s.status] ? badge(s.status) : "—"; });
    row("Why", function (s) { return s.reason; });
    row("Council", function (s) { return s.council; });
    row("Latest year", function (s) { return s.year + (s.academy ? " (academy)" : ""); });
    row("Reserve", function (s) { return money(s.reserve); });
    row("Reserve as % of income", function (s) { return s.share == null ? "—" : (s.share * 100).toFixed(1) + "%"; });
    row("Last year's balance", function (s) { return money(s.balance, true); });
    row("Years spending more than income", function (s) { return s.streak ? String(s.streak) : "—"; });
    row("Pupils since first year", function (s) { return s.pupils_change == null ? "—" : (s.pupils_change > 0 ? "+" : "") + Math.round(s.pupils_change * 100) + "%"; });
    CATS.forEach(function (c) {
      row(c[1], function (s) {
        var v = s.pp[c[0]];
        if (typeof v !== "number") return "—";
        var m = s.similar[c[0]];
        return "£" + v.toLocaleString("en-GB") + (m ? " (similar schools £" + m.toLocaleString("en-GB") + ")" : "");
      });
    });
    row("Check at source", function (s) { var a = el("a", null, "DfE benchmarking"); a.href = s.check; a.rel = "noopener"; return a; });
    wrap.appendChild(t);
    return wrap;
  }
  function chart(schools) {
    var NS = "http://www.w3.org/2000/svg", W = 640, H = 220, L = 48, R = 12, T = 12, B = 26;
    var labels = [];
    schools.forEach(function (s) { s.years.forEach(function (y) { if (labels.indexOf(y[0]) === -1) labels.push(y[0]); }); });
    labels.sort();
    var vals = [];
    schools.forEach(function (s) { s.years.forEach(function (y) { if (y[1] && typeof y[3] === "number") vals.push(y[3] / y[1] * 100); }); });
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
      add("line", {"class": v === 0 ? "axis" : "grid", x1: L, x2: W - R, y1: y(v), y2: y(v)});
      add("text", {"class": "tick", x: L - 6, y: y(v) + 4, "text-anchor": "end"}, v + "%");
    }
    labels.forEach(function (lab, i) { add("text", {"class": "tick", x: x(i), y: H - 8, "text-anchor": "middle"}, lab); });
    schools.forEach(function (s, si) {
      var pts = s.years.filter(function (yr) { return yr[1] && typeof yr[3] === "number"; }).map(function (yr) { return [labels.indexOf(yr[0]), yr[3] / yr[1] * 100, yr[0]]; });
      if (!pts.length) return;
      var path = add("path", {"class": "line", d: "M" + pts.map(function (p) { return x(p[0]).toFixed(1) + "," + y(p[1]).toFixed(1); }).join("L")});
      path.style.stroke = SERIES[si];
      pts.forEach(function (p) {
        var g = add("g", {"class": "mark", tabindex: "0", "data-tip": s.name + ", " + p[2] + ": " + p[1].toFixed(1) + "% of income"});
        var c = document.createElementNS(NS, "circle");
        c.setAttribute("cx", x(p[0])); c.setAttribute("cy", y(p[1])); c.setAttribute("r", "4");
        c.setAttribute("class", "ring");
        c.style.fill = SERIES[si];
        g.appendChild(c);
        var hit = document.createElementNS(NS, "circle");
        hit.setAttribute("cx", x(p[0])); hit.setAttribute("cy", y(p[1])); hit.setAttribute("r", "12");
        hit.setAttribute("class", "hit");
        g.appendChild(hit);
      });
    });
    var box = el("div");
    var legend = el("p", "legend");
    schools.forEach(function (s, i) {
      var k = el("span", "key line");
      k.style.background = SERIES[i];
      legend.appendChild(k);
      legend.appendChild(document.createTextNode(s.name + "  "));
    });
    box.appendChild(legend);
    box.appendChild(svg);
    return box;
  }

  input.addEventListener("input", function () { search(input.value); });
  var params = new URLSearchParams(location.search);
  (params.get("urns") || "").split(",").filter(function (u) { return /^\d+$/.test(u); }).slice(0, MAX).forEach(function (u) { chosen.push(u); });
  if (params.get("q")) { input.value = params.get("q"); search(input.value); }
  render();
})();
