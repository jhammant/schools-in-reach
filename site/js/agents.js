import { CONFIG } from "./config.js";
import { track } from "./analytics.js";

// Funnel events shared by all of Jon's sites (signup, checkout, paid, promo_click, cta_click),
// so the side-projects tracker counts each step per site in the same way. Only these fixed
// values are ever sent with them: nothing a visitor typed, and no address or postcode.
const FUNNEL = { product: "schoolsinreach-agents", page_type: "agents" };

let checkout = null;
try {
  const url = new URL(CONFIG.agents.checkoutUrl);
  if (url.protocol === "https:") checkout = url.href;
} catch { /* Checkout has not been configured yet. */ }
for (const link of document.querySelectorAll(".trial-cta")) {
  if (checkout) {
    link.href = checkout;
    link.addEventListener("click", () => {
      track("agents_cta_click");                       // kept so the existing series continues
      track("checkout", { ...FUNNEL, plan: "branch-monthly" });
    });
  }
  else {
    link.textContent = "Coming soon";
    link.setAttribute("aria-disabled", "true");
    link.removeAttribute("href");
  }
}
// The page ships with the live checkout link so it works without this script;
// if checkout is ever switched off in config.js, say so instead.
if (!checkout) document.querySelector("#checkout-status").textContent = "Trial registration is coming soon.";
// A contact address is shown only once CONFIG.agents.contactEmail is set; none ships by default.
const contactEmail = String(CONFIG.agents.contactEmail || "").trim();
const contact = document.querySelector("#agents-contact");
const contactLink = document.querySelector("#agents-contact-link");
if (contact && contactLink && /^[^\s@<>"]+@[^\s@<>"]+\.[^\s@<>"]+$/.test(contactEmail)) {
  contactLink.href = `mailto:${contactEmail}`;
  contactLink.textContent = contactEmail;
  contact.hidden = false;
  contactLink.addEventListener("click", () => track("cta_click", { ...FUNNEL, offer: "agents-contact" }));
}
const copy = document.querySelector("#copy-code");
copy.hidden = false;
copy.addEventListener("click", async () => {
  track("agents_copy_snippet");
  const status = document.querySelector("#copy-status");
  try {
    await navigator.clipboard.writeText(document.querySelector("#embed-code").textContent);
    status.textContent = "Code copied";
  } catch { status.textContent = "Select the code above and copy it manually."; }
});

// A postcode passed to /agents/?postcode=… (see page-analytics.js) re-points the live demo.
function personaliseDemo(raw) {
  const compact = String(raw || "").toUpperCase().replace(/\s+/g, "");
  if (!/^[A-Z]{1,2}[0-9][A-Z0-9]?[0-9][A-Z]{2}$/.test(compact)) return;
  const postcode = `${compact.slice(0, -3)} ${compact.slice(-3)}`;
  const demo = document.querySelector(".demo[data-schools-in-reach]");
  if (!demo) return;
  demo.dataset.postcode = postcode;
  const frame = demo.querySelector("iframe");
  if (frame) {
    const src = new URL(frame.src);
    src.searchParams.set("postcode", postcode);
    frame.src = src.href;
  }
  document.querySelector("#demo-heading").textContent = `Here it is for ${postcode}`;
  document.querySelector("#demo-postcode").textContent = postcode;
  track("agents_demo_personalised");
}
personaliseDemo(window.sirDemoPostcode);
