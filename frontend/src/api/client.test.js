import assert from "node:assert/strict";
import test from "node:test";

import { clientInternals } from "./client.js";

test("query strings omit empty filters and use API field names", () => {
  const query = clientInternals.queryString({
    page: 2,
    page_size: 25,
    status: "review",
    severity: "",
  });
  assert.equal(query, "?page=2&page_size=25&status=review");
});

test("API paths remain relative when no deployment base is configured", () => {
  assert.equal(clientInternals.apiUrl("/api/health"), "/api/health");
});
