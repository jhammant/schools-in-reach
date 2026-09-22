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
