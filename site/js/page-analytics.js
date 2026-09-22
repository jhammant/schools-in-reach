import { initAnalytics } from "./analytics.js";

// /agents/?postcode=… personalises the demo (the links in our follow-up emails). Keep the
// postcode out of analytics: hand it to agents.js, then drop it from the URL before tracking.
try {
  const url = new URL(window.location.href);
  if (url.searchParams.has("postcode")) {
    window.sirDemoPostcode = url.searchParams.get("postcode");
    url.searchParams.delete("postcode");
    window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
  }
} catch { /* Never block the page. */ }

// Static pages have no map state. Keep this off /embed/: its URL has a postcode.
try {
  initAnalytics();
} catch { /* Analytics must never break the page. */ }
