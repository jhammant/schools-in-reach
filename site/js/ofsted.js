/** One short Ofsted label for lists and headers, from an ofsted.json school entry. */
export function ofstedHeadline(o) {
  if (!o) return null;
  if (o.inspectorate === "ISI") return "Inspected by ISI";
  const latest = o.latest;
  if (!latest) return null;
  const year = latest.date ? latest.date.slice(0, 4) : "";
  if (latest.kind === "report_card") return `Report card ${year}`.trim();
  const graded = (insp) => insp?.judgements?.overall_effectiveness || insp?.overall_effectiveness;
  if (latest.kind === "graded" && graded(latest)) return graded(latest) === "Not judged" ? `Inspected ${year}` : graded(latest);
  if (latest.kind === "ungraded") {
    const prior = graded(o.last_graded) || graded(o.previous);
    return prior || latest.outcome || null;
  }
  return graded(latest) || null;
}
