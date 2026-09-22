import { CONFIG } from "./config.js";
import { track } from "./analytics.js";

let checkout = null;
try {
  const url = new URL(CONFIG.agents.checkoutUrl);
  if (url.protocol === "https:") checkout = url.href;
} catch { /* Checkout has not been configured yet. */ }
for (const link of document.querySelectorAll(".trial-cta")) {
  if (checkout) {
    link.href = checkout;
    link.addEventListener("click", () => track("agents_cta_click"));
  }
  else {
    link.textContent = "Coming soon";
    link.setAttribute("aria-disabled", "true");
    link.removeAttribute("href");
  }
}
if (checkout) document.querySelector("#checkout-status").textContent = "Start your 30-day free trial. We'll email your widget code within one working day.";
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
