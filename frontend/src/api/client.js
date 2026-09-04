const API_BASE = (import.meta.env?.VITE_API_BASE_URL || "").replace(/\/$/, "");
const API_KEY = import.meta.env?.VITE_API_KEY || "";

function apiUrl(path) {
  return `${API_BASE}${path}`;
}

function queryString(values) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  });
  const query = params.toString();
  return query ? `?${query}` : "";
}

async function parseResponse(response) {
  if (response.ok) {
    if (response.status === 204) return null;
    return response.json();
  }
  const payload = await response.json().catch(() => ({}));
  const detail = payload.detail;
  const message =
    typeof detail === "string"
      ? detail
      : detail?.message || `Request failed (${response.status})`;
  const error = new Error(message);
  error.status = response.status;
  error.runId = detail?.run_id;
  throw error;
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (API_KEY) headers["X-API-Key"] = API_KEY;
  return parseResponse(await fetch(apiUrl(path), { ...options, headers }));
}

export function getHealth() {
  return request("/api/health");
}

export function getSourceBatches() {
  return request("/api/reconciliation/source-batches");
}

export function createReconciliationRun(sourceBatch) {
  return request("/api/reconciliation/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_batch: sourceBatch }),
  });
}

export function getRun(runId) {
  return request(`/api/reconciliation/runs/${encodeURIComponent(runId)}`);
}

export function getRuns({ page = 1, pageSize = 20, sourceBatch, status } = {}) {
  const query = queryString({
    page,
    page_size: pageSize,
    source_batch: sourceBatch,
    status,
  });
  return request(`/api/reconciliation/runs${query}`);
}

export function getMetrics(runId) {
  return request(
    `/api/reconciliation/runs/${encodeURIComponent(runId)}/metrics`,
  );
}

export function getResults(runId, { page = 1, pageSize = 25, status } = {}) {
  const query = queryString({ page, page_size: pageSize, status });
  return request(
    `/api/reconciliation/runs/${encodeURIComponent(runId)}/results${query}`,
  );
}

export function getExceptions(
  runId,
  { page = 1, pageSize = 25, severity, exceptionType, status } = {},
) {
  const query = queryString({
    page,
    page_size: pageSize,
    severity,
    exception_type: exceptionType,
    status,
  });
  return request(
    `/api/reconciliation/runs/${encodeURIComponent(runId)}/exceptions${query}`,
  );
}

export function predictionUrl(runId) {
  return apiUrl(
    `/api/reconciliation/runs/${encodeURIComponent(runId)}/predictions.csv`,
  );
}

export function exceptionUrl(runId) {
  return apiUrl(
    `/api/reconciliation/runs/${encodeURIComponent(runId)}/exceptions.csv`,
  );
}

export const clientInternals = { apiUrl, queryString };

export function getForecast({ horizonDays = 30, sourceBatch, currency } = {}) {
  const query = queryString({ horizon_days: horizonDays, source_batch: sourceBatch, currency });
  return request(`/api/forecasts${query}`);
}

export function analyzeException(exceptionId) {
  return request(`/api/ai/exceptions/${encodeURIComponent(exceptionId)}/analyze`, { method: "POST" });
}

export function suggestAIMatch(runId, transactionId) {
  return request("/api/ai/match", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ run_id: runId, transaction_id: transactionId }) });
}

export function askFinanceQuestion(question, sourceBatch) {
  return request("/api/ai/finance-qa", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, source_batch: sourceBatch || null }) });
}
