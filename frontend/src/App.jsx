import { useCallback, useEffect, useState } from "react";

import {
  createReconciliationRun,
  getHealth,
  getMetrics,
  getRun,
  getRuns,
  getSourceBatches,
} from "./api/client";
import ExceptionsPage from "./pages/ExceptionsPage";
import OverviewPage from "./pages/OverviewPage";
import ResultsPage from "./pages/ResultsPage";
import ForecastPage from "./pages/ForecastPage";
import FinanceQAPage from "./pages/FinanceQAPage";
import { shortId } from "./utils/formatters";

const screens = [
  ["overview", "Overview"],
  ["results", "Results"],
  ["exceptions", "Exceptions"],
  ["forecast", "Forecast"],
  ["qa", "Ask Finance"],
];

function App() {
  const [screen, setScreen] = useState("overview");
  const [apiHealthy, setApiHealthy] = useState(false);
  const [batches, setBatches] = useState([]);
  const [history, setHistory] = useState([]);
  const [selectedBatch, setSelectedBatch] = useState("");
  const [run, setRun] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");

  const selectRun = useCallback(async (runId) => {
    if (!runId) return;
    setError("");
    try {
      const [selectedRun, runMetrics] = await Promise.all([
        getRun(runId),
        getMetrics(runId),
      ]);
      setRun(selectedRun);
      setMetrics(runMetrics);
      setSelectedBatch(selectedRun.source_batch);
    } catch (requestError) {
      setError(requestError.message);
    }
  }, []);

  const refreshHistory = useCallback(async () => {
    const response = await getRuns({ page: 1, pageSize: 50 });
    setHistory(response.items);
    return response.items;
  }, []);

  useEffect(() => {
    let active = true;
    async function bootstrap() {
      const [healthResult, batchResult, historyResult] = await Promise.allSettled([
        getHealth(),
        getSourceBatches(),
        getRuns({ page: 1, pageSize: 50 }),
      ]);
      if (!active) return;
      setApiHealthy(healthResult.status === "fulfilled");
      if (batchResult.status === "fulfilled") {
        const items = batchResult.value.items;
        setBatches(items);
        if (items.length) setSelectedBatch(items[0].source_batch);
      }
      if (historyResult.status === "fulfilled") {
        const items = historyResult.value.items;
        setHistory(items);
        if (items.length) selectRun(items[0].run_id);
      }
      const failed = [batchResult, historyResult].find(
        (result) => result.status === "rejected",
      );
      if (failed) setError(failed.reason.message);
    }
    bootstrap();
    return () => {
      active = false;
    };
  }, [selectRun]);

  async function startRun() {
    if (!selectedBatch) return;
    setStarting(true);
    setError("");
    try {
      const created = await createReconciliationRun(selectedBatch);
      setRun(created);
      setMetrics(await getMetrics(created.run_id));
      await refreshHistory();
    } catch (requestError) {
      setError(
        requestError.runId
          ? `${requestError.message} Run ${requestError.runId}`
          : requestError.message,
      );
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <a className="brand" href="#overview" onClick={() => setScreen("overview")}>
          <span className="brand__mark" aria-hidden="true">FC</span>
          <span>
            <strong>Finance Controller</strong>
            <small>Reconciliation operations</small>
          </span>
        </a>
        <nav className="main-nav" aria-label="Primary navigation">
          {screens.map(([value, label]) => (
            <button
              key={value}
              type="button"
              className={screen === value ? "is-active" : ""}
              aria-current={screen === value ? "page" : undefined}
              onClick={() => setScreen(value)}
            >
              {label}
            </button>
          ))}
        </nav>
        <div className="connection-status">
          <span className={apiHealthy ? "is-online" : "is-offline"} />
          <div>
            <strong>{apiHealthy ? "API connected" : "API offline"}</strong>
            <small>{run ? `Run ${shortId(run.run_id)}` : "No active run"}</small>
          </div>
        </div>
      </header>

      <main className="app-main">
        {screen === "overview" && (
          <OverviewPage
            batches={batches}
            selectedBatch={selectedBatch}
            onBatchChange={setSelectedBatch}
            onStartRun={startRun}
            starting={starting}
            run={run}
            metrics={metrics}
            history={history}
            onSelectRun={selectRun}
            error={error}
          />
        )}
        {screen === "results" && (
          <ResultsPage
            key={run?.run_id || "no-run"}
            runId={run?.run_id}
          />
        )}
        {screen === "exceptions" && <ExceptionsPage runId={run?.run_id} />}
        {screen === "forecast" && <ForecastPage sourceBatch={selectedBatch || undefined} />}
        {screen === "qa" && <FinanceQAPage sourceBatch={selectedBatch || undefined} />}
      </main>
      <footer className="app-footer">
        <span>Deterministic reconciliation</span>
        <span>Ground truth remains evaluation-only</span>
      </footer>
    </div>
  );
}

export default App;
