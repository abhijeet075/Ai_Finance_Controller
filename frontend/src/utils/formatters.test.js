import assert from "node:assert/strict";
import test from "node:test";

import {
  formatConfidence,
  formatCurrency,
  formatPercent,
  titleCase,
} from "./formatters.js";

test("quality metrics are honest when truth is unavailable", () => {
  assert.equal(formatPercent(null), "Not evaluated");
  assert.equal(formatPercent(0.875), "87.5%");
});

test("confidence is represented as a score out of one hundred", () => {
  assert.equal(formatConfidence(61), "61.0%");
});

test("amounts use the record currency", () => {
  assert.match(formatCurrency(9500, "INR"), /9,500/);
});

test("machine labels become readable labels", () => {
  assert.equal(titleCase("amount_mismatch"), "Amount Mismatch");
});
