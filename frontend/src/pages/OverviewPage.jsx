import MetricCard from "../components/MetricCard";
import StatusBadge from "../components/StatusBadge";
import { predictionUrl } from "../api/client";

function formatRate(value) {
  return value == null ? "—" : `${(Number(value) * 100).toFixed(1)}%`;
}

export default function OverviewPage({
  apiHealthy,
  sourceBatch,
  setSourceBatch,
  run,
  loading,
  error,
  startRun,
}) {
  const metrics = [
    ["Records processed", run?.records_processed ?? "—", "Complete bank rows"],
    ["Automatic match rate", formatRate(run?.match_rate), "Globally assigned"],
    ["Review", run?.review ?? "—", "Needs human decision"],
    ["Exceptions", run?.exceptions ?? "—", "Deterministic controls"],
    [
      "Processing time",
      run ? `${run.processing_time_ms} ms` : "—",
      "End-to-end service",
    ],
    [
      "Throughput",
      run ? `${run.records_per_second}/s` : "—",
      "Complete records",
    ],
    [
      "Candidate pruning",
      run ? `${run.comparison_reduction}%` : "—",
      "Comparisons avoided",
    ],
    ["Matched", run?.matched ?? "—", "Invoice and settlement"],
  ];
  return (
    <main>
      <header className="topbar">
        <div>
          <p className="eyebrow">CONTROL ROOM</p>
          <h1>AI Finance Controller</h1>
        </div>
        <StatusBadge healthy={apiHealthy}>
          {apiHealthy ? "API connected" : "API unavailable"}
        </StatusBadge>
      </header>
      <section className="intro" aria-labelledby="overview-title">
        <div>
          <p className="eyebrow">PHASE 10</p>
          <h2 id="overview-title">Decide globally. Persist every outcome.</h2>
          <p>
            Reconcile an uploaded batch with one-to-one assignment,
            deterministic exceptions, evaluator-ready predictions, and separate
            throughput metrics.
          </p>
        </div>
        <div className="run-controls">
          <label htmlFor="source-batch">Source batch</label>
          <input
            id="source-batch"
            value={sourceBatch}
            onChange={(event) => setSourceBatch(event.target.value)}
            maxLength={128}
          />
          <button
            type="button"
            disabled={!apiHealthy || loading || !sourceBatch.trim()}
            onClick={startRun}
          >
            {loading ? "Reconciling…" : "Start reconciliation"}
          </button>
        </div>
      </section>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {run && (
        <div className="run-meta">
          <span>Run {run.run_id}</span>
          <span>Batch {run.source_batch}</span>
          <a href={predictionUrl(run.run_id)}>Download predictions.csv</a>
        </div>
      )}
      <section className="metric-grid" aria-label="Finance metrics">
        {metrics.map(([label, value, hint]) => (
          <MetricCard key={label} label={label} value={value} hint={hint} />
        ))}
      </section>
      <section className="workspace">
        <article className="panel">
          <div className="panel-head">
            <div>
              <p className="eyebrow">RECONCILIATION</p>
              <h3>Decision pipeline</h3>
            </div>
            <StatusBadge>{run ? "Completed" : "Not run"}</StatusBadge>
          </div>
          <ol className="pipeline">
            <li>
              <b>01</b>
              <div>
                <strong>Load batch</strong>
                <span>Bank · invoices · settlements</span>
              </div>
            </li>
            <li>
              <b>02</b>
              <div>
                <strong>Match</strong>
                <span>Indexed candidates · confidence</span>
              </div>
            </li>
            <li>
              <b>03</b>
              <div>
                <strong>Assign globally</strong>
                <span>Highest unused evidence wins</span>
              </div>
            </li>
            <li>
              <b>04</b>
              <div>
                <strong>Persist</strong>
                <span>Matched · review · exception</span>
              </div>
            </li>
          </ol>
        </article>
        <article className="panel">
          <div className="panel-head">
            <div>
              <p className="eyebrow">EVALUATION</p>
              <h3>Truth-isolated scoreboard</h3>
            </div>
            <StatusBadge>
              {run ? "Predictions ready" : "Awaiting run"}
            </StatusBadge>
          </div>
          <div className="evaluation-copy">
            <p>
              Download predictions, then evaluate them offline against hidden
              truth.
            </p>
            <p>
              Precision, recall, F1, exact-link accuracy, and status accuracy
              never enter the app.
            </p>
          </div>
        </article>
      </section>
    </main>
  );
}
