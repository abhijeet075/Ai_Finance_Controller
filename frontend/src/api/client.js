async function parseResponse(response) {
  if (response.ok) return response.json();
  const payload = await response.json().catch(() => ({}));
  throw new Error(payload.detail || `Request failed (${response.status})`);
}

export async function getHealth() {
  return parseResponse(await fetch("/api/health"));
}

export async function createReconciliationRun(sourceBatch) {
  return parseResponse(
    await fetch("/api/reconciliation/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_batch: sourceBatch }),
    }),
  );
}

export function predictionUrl(runId) {
  return `/api/reconciliation/runs/${runId}/predictions`;
}
