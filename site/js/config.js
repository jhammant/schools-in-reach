export const CONFIG = {
  adsense: { client: "", slots: { listFooter: "", aboutPage: "", schoolAfterAdmissions: "", schoolFooter: "" }, nonPersonalised: true },
  // Shares the RecOS organisation's only project (its plan allows one), so every event
  // carries site: "schoolsinreach" and can be filtered out of anything else in there.
  posthog: { key: "phc_oTseg3qqEWn88i3etv4UNPP564zcEk46FTk76M8SzgBH", host: "https://eu.i.posthog.com", cookieless: true },
  agents: { checkoutUrl: "https://buy.stripe.com/00w7sN8Of3e3dnfgS6bQY01", contactEmail: "" },
  // Demand test for the paid "Your chances" report (site/js/report-offer.js). The offer shows on
  // Reception results in councils with cut-offs until endsOn. notifyUrl is the sign-up endpoint in
  // deploy/report-signups/; empty it to keep the offer but drop the email box.
  parentsReport: { enabled: true, price: "£9.99", endsOn: "2027-01-15", notifyUrl: "https://pages.hammantlabs.com/sir-report/api/notify" },
  contactEmail: "",
};
