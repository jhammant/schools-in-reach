(function () {
  "use strict";
  var script = document.currentScript;
  if (!script || !script.src) return;
  var origin = new URL(script.src).origin;
  var api = window.SchoolsInReach;
  if (!api) {
    api = window.SchoolsInReach = { frames: new Map() };
    window.addEventListener("message", function (event) {
      var frame = api.frames.get(event.source);
      var data = event.data;
      if (!frame || event.origin !== frame.origin || !data || data.type !== "sir:height") return;
      if (typeof data.height !== "number" || !Number.isFinite(data.height) || data.height <= 0 || data.height > 20000) return;
      frame.element.style.height = Math.ceil(data.height) + "px";
    });
  }
  function mount() {
    document.querySelectorAll("[data-schools-in-reach]").forEach(function (container) {
      if (container.dataset.sirMounted) return;
      container.dataset.sirMounted = "true";
      var url = new URL("/embed/", origin);
      ["postcode", "agent", "phase"].forEach(function (key) {
        if (container.dataset[key]) url.searchParams.set(key, container.dataset[key]);
      });
      var iframe = document.createElement("iframe");
      iframe.src = url.href;
      iframe.title = "Nearby schools";
      iframe.loading = "lazy";
      iframe.referrerPolicy = "strict-origin-when-cross-origin";
      iframe.style.cssText = "display:block;width:100%;border:0;height:480px";
      container.appendChild(iframe);
      api.frames.set(iframe.contentWindow, { element: iframe, origin: origin });
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount, { once: true });
  else mount();
}());
