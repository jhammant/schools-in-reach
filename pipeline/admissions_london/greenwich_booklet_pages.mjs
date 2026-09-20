/**
 * Royal Greenwich moved its admissions booklets off PDF and into a PageSuite reader, so the
 * old royalgreenwich.gov.uk PDF links now 500 and our figures froze at 2023 (primary) and
 * 2025 (secondary).
 *
 * The reader loads each page as its own public PDF from pages.pagesuite.com, and lists them
 * in a `flatPlanData` object on the page. There is no server-side manifest endpoint, so this
 * opens the reader the way a reader does and prints the page PDF URLs, one per line, for
 * b3_greenwich_booklet.py to download and parse.
 *
 *   node greenwich_booklet_pages.mjs <pubid>
 */
import puppeteer from "puppeteer-core";

const CHROME = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const pubid = process.argv[2];
if (!pubid) {
  console.error("usage: node greenwich_booklet_pages.mjs <pubid>");
  process.exit(2);
}

const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new" });
const page = await browser.newPage();
await page.setViewport({ width: 1400, height: 900 });
await page.goto(`https://edition.pagesuite-professional.co.uk/html5/reader/production/default.aspx?pubname=&pubid=${pubid}`, {
  waitUntil: "networkidle2",
  timeout: 90000,
});
await new Promise((r) => setTimeout(r, 8000));

const result = await page.evaluate(() => {
  const found = [];
  const seen = new WeakSet();
  const walk = (o, depth) => {
    if (o == null || depth > 6) return;
    if (typeof o === "string") {
      if (/pages\.pagesuite\.com\/.\/.\/[0-9a-f-]{36}\/page\.pdf/.test(o)) found.push(o);
      return;
    }
    if (typeof o !== "object" || seen.has(o)) return;
    seen.add(o);
    // pdf.js loading tasks are circular and hold no page URLs.
    if (o.constructor && /PDF|Worker/.test(o.constructor.name || "")) return;
    for (const k of Object.keys(o).slice(0, 40)) {
      try { walk(o[k], depth + 1); } catch {}
    }
  };
  walk(window.flatPlanData?.pageGroups, 0);
  return { name: window.editionName, date: window.editionDate, eid: window.editionguid, pages: [...new Set(found)] };
});

console.error(`${result.name} (${result.date}) — ${result.pages.length} page files`);
console.log(JSON.stringify(result));
await browser.close();
