/* School Money — trend.js. Defer-loaded on pages with a .trend block; the markup works without it.
   Inside a .trend container, buttons [data-basis-toggle="cash"|"real"] show the matching g[data-basis]
   chart groups (through their display attribute; other [data-basis] elements through hidden), and
   [data-unit-toggle="pp"|"total"] show the matching [data-unit] blocks (through hidden). Every toggle
   carries aria-pressed. Default markup: cash and per pupil.
   The basis choice applies to every .trend on the page and persists in localStorage moneyBasis.
   Pure helpers are exported as globalThis.MoneyTrend for tests. */
(function (root) {
  "use strict";

  var KEY = "moneyBasis";
  var BASES = ["cash", "real"], UNITS = ["pp", "total"];

  function each(list, fn) { Array.prototype.forEach.call(list || [], fn); }
  function storage() {
    try { return root.localStorage || null; } catch (e) { return null; }
  }
  function readBasis(store) {
    try {
      var v = store ? store.getItem(KEY) : null;
      return BASES.indexOf(v) === -1 ? null : v;
    } catch (e) { return null; }
  }
  function saveBasis(store, basis) {
    try { if (store) store.setItem(KEY, basis); } catch (e) { /* private mode or full */ }
  }
  function press(box, attr, value) {
    each(box.querySelectorAll("[" + attr + "]"), function (b) {
      b.setAttribute("aria-pressed", b.getAttribute(attr) === value ? "true" : "false");
    });
  }
  function applyBasis(box, basis) {
    if (BASES.indexOf(basis) === -1) return;
    each(box.querySelectorAll("[data-basis]"), function (n) {
      var on = n.getAttribute("data-basis") === basis;
      if (String(n.tagName).toLowerCase() === "g") {
        if (on) n.removeAttribute("display"); else n.setAttribute("display", "none");
      } else if (on) n.removeAttribute("hidden");
      else n.setAttribute("hidden", "");
    });
    press(box, "data-basis-toggle", basis);
  }
  function applyUnit(box, unit) {
    if (UNITS.indexOf(unit) === -1) return;
    each(box.querySelectorAll("[data-unit]"), function (n) {
      if (n.getAttribute("data-unit") === unit) n.removeAttribute("hidden"); else n.setAttribute("hidden", "");
    });
    press(box, "data-unit-toggle", unit);
  }
  // ---------------------------------------------------------------- readout: every line's value for one year
  // charts.trend_chart writes data-years ("2018-19|2019-20"), data-x ("<x of first year>,<step>") and data-unit on the
  // svg, and data-l / data-v ("398,,537") on each line's path. Hover, tap (pins on touch) or arrow keys pick a year.
  function parseValues(text) {
    return String(text || "").split(",").map(function (v) { return v === "" ? null : Number(v); });
  }
  function nearestIndex(x, x0, step, n) {
    if (!(n > 0)) return -1;
    if (!step) return 0;
    return Math.max(0, Math.min(n - 1, Math.round((x - x0) / step)));
  }
  function fmtValue(v, unit) {
    if (v == null || !isFinite(v)) return "—";
    if (unit === "%") return (Math.round(v * 10) / 10) + "%";
    if (unit !== "£") return Math.round(v).toLocaleString("en-GB");
    var a = Math.abs(v), sign = v < 0 ? "-" : "";
    if (a >= 1e6) return sign + "£" + (a / 1e6).toFixed(a >= 1e7 ? 0 : 1) + "m";
    if (a >= 1e5) return sign + "£" + Math.round(a / 1e3) + "k";
    return sign + "£" + Math.round(a).toLocaleString("en-GB");
  }
  // [{label, v, colour}] for the year at index i, from the lines currently shown (not a hidden basis group).
  function readout(svg, i) {
    var rows = [];
    each(svg.querySelectorAll("path[data-v]"), function (path) {
      var g = path.closest ? path.closest("g[data-basis]") : null;
      if (g && g.getAttribute("display") === "none") return;
      var v = parseValues(path.getAttribute("data-v"))[i];
      if (v == null) return;
      var colour = "";
      try { colour = root.getComputedStyle(path).stroke; } catch (e) { /* not in a browser */ }
      rows.push({ label: path.getAttribute("data-l") || "", v: v, colour: colour });
    });
    return rows.sort(function (a, b) { return b.v - a.v; });
  }
  function interactive(doc) {
    var tip = null, pinned = null, NS = "http://www.w3.org/2000/svg";
    function ensureTip() {
      if (tip) return tip;
      tip = doc.createElement("div");
      tip.className = "tooltip trend-tip";
      tip.setAttribute("role", "status");
      tip.hidden = true;
      doc.body.appendChild(tip);
      return tip;
    }
    function meta(svg) {
      var years = String(svg.getAttribute("data-years") || "").split("|"), xs = String(svg.getAttribute("data-x") || "").split(",");
      return { years: years, x0: Number(xs[0]), step: Number(xs[1]) || 0, unit: svg.getAttribute("data-unit") || "" };
    }
    function hide(svg) {
      if (tip) tip.hidden = true;
      var line = svg && svg.querySelector("line.xhair");
      if (line) line.setAttribute("display", "none");
    }
    function show(svg, i, cx, cy) {
      var m = meta(svg), rows = readout(svg, i);
      if (i < 0 || !rows.length) { hide(svg); return; }
      var line = svg.querySelector("line.xhair");
      if (!line) {
        line = doc.createElementNS(NS, "line");
        line.setAttribute("class", "xhair");
        line.setAttribute("stroke", "currentColor");
        line.setAttribute("stroke-opacity", "0.45");
        line.setAttribute("stroke-dasharray", "3 3");
        line.setAttribute("pointer-events", "none");
        var vb = (svg.getAttribute("viewBox") || "0 0 480 220").split(/\s+/);
        line.setAttribute("y1", "8"); line.setAttribute("y2", String(Number(vb[3]) - 22));
        svg.appendChild(line);
      }
      var x = m.x0 + i * m.step;
      line.setAttribute("x1", String(x)); line.setAttribute("x2", String(x)); line.removeAttribute("display");
      var t = ensureTip();
      t.textContent = "";
      var head = doc.createElement("b"); head.textContent = m.years[i]; t.appendChild(head);
      rows.forEach(function (r) {
        var row = doc.createElement("div"), name = doc.createElement("span"), val = doc.createElement("span"), sw = doc.createElement("i");
        row.className = "row";
        sw.setAttribute("aria-hidden", "true");
        sw.style.cssText = "display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;background:" + (r.colour || "currentColor");
        name.appendChild(sw); name.appendChild(doc.createTextNode(r.label));
        val.textContent = fmtValue(r.v, m.unit);
        row.appendChild(name); row.appendChild(val); t.appendChild(row);
      });
      t.hidden = false;
      var w = t.offsetWidth || 200, h = t.offsetHeight || 80, vw = root.innerWidth || 800;
      t.style.left = Math.max(8, Math.min(vw - w - 8, cx + 14)) + "px";
      t.style.top = Math.max(8, cy - h - 12) + "px";
    }
    function indexAt(svg, e) {
      var m = meta(svg), ctm = svg.getScreenCTM && svg.getScreenCTM();
      if (!ctm) return -1;
      var pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
      return nearestIndex(pt.matrixTransform(ctm.inverse()).x, m.x0, m.step, m.years.length);
    }
    each(doc.querySelectorAll("svg.chart.trend[data-years]"), function (svg) {
      if (!svg.querySelector("path[data-v]")) return;
      svg.setAttribute("tabindex", "0");
      svg.style.cursor = "crosshair";
      svg.setAttribute("aria-description", "Hover, tap or use the arrow keys for each year's figures");
      var current = -1;
      svg.addEventListener("pointermove", function (e) {
        if (pinned && pinned !== svg) return;
        current = indexAt(svg, e); show(svg, current, e.clientX, e.clientY);
      });
      svg.addEventListener("pointerleave", function () { if (pinned !== svg) hide(svg); });
      svg.addEventListener("pointerdown", function (e) {
        if (pinned && pinned !== svg) hide(pinned);
        pinned = svg; current = indexAt(svg, e); show(svg, current, e.clientX, e.clientY);
      });
      svg.addEventListener("keydown", function (e) {
        var n = meta(svg).years.length, r = svg.getBoundingClientRect();
        if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
          e.preventDefault();
          current = current < 0 ? n - 1 : Math.max(0, Math.min(n - 1, current + (e.key === "ArrowRight" ? 1 : -1)));
          var m = meta(svg), ctm = svg.getScreenCTM && svg.getScreenCTM();
          var cx = ctm ? ctm.a * (m.x0 + current * m.step) + ctm.e : r.left + r.width / 2;
          show(svg, current, cx, r.top + 40);
        } else if (e.key === "Escape") { hide(svg); current = -1; }
      });
      svg.addEventListener("blur", function () { if (pinned !== svg) hide(svg); });
    });
    doc.addEventListener("pointerdown", function (e) {
      if (pinned && !(e.target.closest && e.target.closest("svg.chart.trend"))) { hide(pinned); pinned = null; }
    });
    root.addEventListener && root.addEventListener("scroll", function () { if (pinned) { hide(pinned); pinned = null; } }, { passive: true });
  }

  function init(doc, store) {
    var saved = readBasis(store);
    if (saved) each(doc.querySelectorAll(".trend"), function (box) { applyBasis(box, saved); });
    doc.addEventListener("click", function (e) {
      var t = e.target;
      var btn = t && t.closest ? t.closest("[data-basis-toggle], [data-unit-toggle]") : null;
      var box = btn && btn.closest(".trend");
      if (!box) return;
      if (btn.hasAttribute("data-basis-toggle")) {
        var basis = btn.getAttribute("data-basis-toggle");
        if (BASES.indexOf(basis) === -1) return;
        saveBasis(store, basis);
        each(doc.querySelectorAll(".trend"), function (b) { applyBasis(b, basis); });
      } else {
        applyUnit(box, btn.getAttribute("data-unit-toggle"));
      }
    });
    if (doc.body && typeof doc.createElementNS === "function") interactive(doc);
  }

  root.MoneyTrend = { KEY: KEY, readBasis: readBasis, saveBasis: saveBasis, applyBasis: applyBasis, applyUnit: applyUnit, init: init,
    parseValues: parseValues, nearestIndex: nearestIndex, fmtValue: fmtValue, readout: readout };
  if (typeof document !== "undefined") init(document, storage());
})(typeof globalThis !== "undefined" ? globalThis : this);
