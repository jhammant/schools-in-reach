import { CONFIG } from "./config.js";

// Everything here is a no-op until a PostHog key is configured. With an empty
// key, no script tags are created and no network requests are made.
let started = false;

/** Load the official PostHog array-queue loader (EU) and initialise it cookieless. */
function loadPostHog() {
  if (started || !CONFIG.posthog.key) return;
  started = true;

  // Official PostHog snippet (array-queue loader). Queues calls made before the library loads.
  !function (t, e) {
    var o, n, p, r;
    e.__SV || (window.posthog = e, e._i = [], e.init = function (i, s, a) {
      function g(t, e) {
        var o = e.split(".");
        2 == o.length && (t = t[o[0]], e = o[1]);
        t[e] = function () { t.push([e].concat(Array.prototype.slice.call(arguments, 0))); };
      }
      (p = t.createElement("script")).type = "text/javascript", p.crossOrigin = "anonymous", p.async = !0,
      p.src = s.api_host.replace(".i.posthog.com", "-assets.i.posthog.com") + "/static/array.js",
      (r = t.getElementsByTagName("script")[0]).parentNode.insertBefore(p, r);
      var u = e;
      for (void 0 !== a ? u = e[a] = [] : a = "posthog", u.people = u.people || [], u.toString = function (t) {
        var e = "posthog";
        return "posthog" !== a && (e += "." + a), t || (e += " (stub)"), e;
      }, u.people.toString = function () { return u.toString(1) + ".people (stub)"; },
        o = "capture identify alias people.set people.set_once set_config register register_once unregister opt_out_capturing has_opted_out_capturing opt_in_capturing reset isFeatureEnabled onFeatureFlags getFeatureFlag getFeatureFlagPayload reloadFeatureFlags group updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures getActiveMatchingSurveys getSurveys onSessionId".split(" "),
        n = 0; n < o.length; n++) g(u, o[n]);
      e._i.push([i, s, a]);
    }, e.__SV = 1);
  }(document, window.posthog || []);

  window.posthog.init(CONFIG.posthog.key, {
    api_host: CONFIG.posthog.host,
    persistence: CONFIG.posthog.cookieless ? "memory" : "localStorage+cookie",
    person_profiles: "identified_only",
    autocapture: false,
    capture_pageview: true,
    disable_session_recording: true,
    ip: false,
    respect_dnt: true,
  });
}

/** Called once from app.js. Safe to call again; it will not double-initialise. */
export function initAnalytics() {
  if (!CONFIG.posthog.key) return;
  loadPostHog();
}

/**
 * Send one event with coarse, non-identifying properties only. A no-op when
 * disabled, and never allowed to break the site.
 */
export function track(name, props = {}) {
  if (!CONFIG.posthog.key) return;
  try {
    if (window.posthog && typeof window.posthog.capture === "function") {
      window.posthog.capture(name, props);
    }
  } catch {
    // Analytics must never break the site.
  }
}
