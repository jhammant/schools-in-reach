import { CONFIG } from "./config.js";

// Everything here is a no-op until a publisher ID is configured. With an empty
// client string, no script tags are created and no network requests are made.
const client = CONFIG.adsense.client;
const built = new Set();
const pushed = new Set();
let scriptLoaded = false;

/** Load the AdSense library exactly once, asynchronously. */
function ensureScript() {
  if (scriptLoaded || !client) return;
  scriptLoaded = true;
  const s = document.createElement("script");
  s.async = true;
  s.crossOrigin = "anonymous";
  s.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${encodeURIComponent(client)}`;
  document.head.appendChild(s);
}

/**
 * Switch off personalised ads and page-level (auto) ads before the library
 * loads. Must run before ensureScript so the flag is set on the stub queue.
 */
function consentConfig() {
  if (!CONFIG.adsense.nonPersonalised) return;
  (window.adsbygoogle = window.adsbygoogle || []).requestNonPersonalizedAds = 1;
  (window.adsbygoogle = window.adsbygoogle || []).push({
    google_ad_client: client,
    enable_page_level_ads: false,
  });
}

/** Inject css/ads.css from JS so index.html doesn't need a link tag. */
function injectStyles() {
  if (document.getElementById("ads-css")) return;
  const link = document.createElement("link");
  link.id = "ads-css";
  link.rel = "stylesheet";
  link.href = "css/ads.css";
  document.head.appendChild(link);
}

/** Build the labelled <ins> markup for a slot. Returns false for an empty slot ID. */
function buildSlot(container, slotId) {
  if (!slotId || built.has(slotId)) return false;
  built.add(slotId);

  const wrap = document.createElement("div");
  wrap.className = "ad-slot";

  const label = document.createElement("span");
  label.className = "ad-label";
  label.textContent = "Advertisement";

  const ins = document.createElement("ins");
  ins.className = "adsbygoogle";
  ins.style.display = "block";
  ins.setAttribute("data-ad-client", client);
  ins.setAttribute("data-ad-slot", slotId);
  ins.setAttribute("data-ad-format", "horizontal");
  ins.setAttribute("data-full-width-responsive", "true");

  wrap.append(label, ins);
  container.appendChild(wrap);
  return true;
}

/** Ask AdSense to render any unprocessed slots. Once per slot. */
function pushSlot(slotId) {
  if (!slotId || pushed.has(slotId)) return;
  pushed.add(slotId);
  try {
    (window.adsbygoogle = window.adsbygoogle || []).push({});
  } catch {
    // The library may not be ready yet; AdSense retries its own queue.
  }
}

/** Bottom of the Schools list panel, after #school-list. Kept off the welcome screen. */
function renderListFooter() {
  const panel = document.getElementById("view-schools");
  const list = document.getElementById("school-list");
  if (!panel || !list) return;

  let container = document.getElementById("ad-list-footer");
  if (!container) {
    container = document.createElement("div");
    container.id = "ad-list-footer";
    list.after(container);
  }
  buildSlot(container, CONFIG.adsense.slots.listFooter);
  syncListFooter();
}

/** Only show the list-footer ad once a home is set (the welcome screen never shows it). */
function syncListFooter() {
  const container = document.getElementById("ad-list-footer");
  if (!container) return;
  const welcome = document.getElementById("welcome");
  const visible = welcome ? welcome.hidden : true;
  container.hidden = !visible;
  if (visible) pushSlot(CONFIG.adsense.slots.listFooter);
}

/** Watch #welcome so the ad appears the moment the welcome screen is dismissed. */
function watchWelcome() {
  const welcome = document.getElementById("welcome");
  if (!welcome) return;
  const mo = new MutationObserver(syncListFooter);
  mo.observe(welcome, { attributes: true, attributeFilter: ["hidden"] });
  syncListFooter();
}

/** Called from app.js on the Schools page. */
export function initAds() {
  if (!client) return;
  injectStyles();
  consentConfig();
  ensureScript();
  renderListFooter();
  watchWelcome();
}

/** Auto-init for pages that embed ads.js directly (the About page). */
function initAboutPage() {
  if (!client) return;
  injectStyles();
  consentConfig();
  ensureScript();

  const main = document.querySelector("main.page");
  if (!main) return;

  let container = document.getElementById("ad-about");
  if (!container) {
    container = document.createElement("div");
    container.id = "ad-about";
    main.appendChild(container);
  }
  if (buildSlot(container, CONFIG.adsense.slots.aboutPage)) pushSlot(CONFIG.adsense.slots.aboutPage);
}

if (/about\.html\/?$/.test(location.pathname)) initAboutPage();
