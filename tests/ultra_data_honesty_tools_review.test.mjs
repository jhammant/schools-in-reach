// Independent contract C3 regression: the own-reserve series is optional.
import { test } from "node:test";
import assert from "node:assert/strict";
import "../pipeline/money/assets/tools.js";

const T = globalThis.MoneyTools;

test("trust-inclusive history loads when the optional own-reserve metric is absent", () => {
  // Arrange: a valid compact sx response; /data/s can fail independently.
  const sx = {
    years: ["2024-25"], reserve_basis: "incl_trust_share",
    source: { "2024-25": "AAR" }, pupils: { "2024-25": 200 },
    m: {
      total_income: { "2024-25": { v: 1_000_000 } },
      total_expenditure: { "2024-25": { v: 950_000 } },
      revenue_reserve: { "2024-25": { v: 200_000 } },
    },
    flags: { suspect: {} },
  };

  // Act.
  const prefill = T.prefillFrom(sx, null);
  const assessment = T.assess(prefill.rows);

  // Assert: lack of an optional second series must not erase the usable history.
  assert.equal(prefill.rows.length, 1, "The required trust-inclusive reserve was discarded");
  assert.equal(assessment.reserve, 200_000);
  assert.equal(assessment.trust_share_included, true);
  assert.equal(assessment.reserve_basis, "incl_trust_share");
});
