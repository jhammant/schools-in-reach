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
  }

  root.MoneyTrend = { KEY: KEY, readBasis: readBasis, saveBasis: saveBasis, applyBasis: applyBasis, applyUnit: applyUnit, init: init };
  if (typeof document !== "undefined") init(document, storage());
})(typeof globalThis !== "undefined" ? globalThis : this);
