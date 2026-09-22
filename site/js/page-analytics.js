import { initAnalytics } from "./analytics.js";

// Static pages have no map state. Keep this off /embed/: its URL has a postcode.
try {
  initAnalytics();
} catch { /* Analytics must never break the page. */ }
