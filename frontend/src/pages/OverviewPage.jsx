import DistributionBars from "../components/DistributionBars";
import EmptyState from "../components/EmptyState";
import MetricCard from "../components/MetricCard";
import StatusBadge from "../components/StatusBadge";
import { exceptionUrl, predictionUrl } from "../api/client";
import {
  formatDuration,
  formatNumber,
  formatPercent,
  formatThroughput,
  shortId,
} from "../utils/formatters";

export default function OverviewPage({
  batches,
  selectedBatch,
  onBatchChange,
  onStartRun,
  starting,
  run,
  metrics,
  history,
  onSelectRun,
  error,
}) {
  const cards = [
    ["Total records", formatNumber(metrics?.total_records), "Canonical decisions", "neutral"],
    ["Matched", formatNumber(metrics?.matched), "Automatically reconciled", "success"],
    ["Review", formatNumber(metrics?.review), "Human attention", "warning"],
    ["Exceptions", formatNumber(metrics?.exceptions), "Control failures", "danger"],
    ["Match rate", formatPercent(metrics?.match_rate), "Matched / total", "success"],
    ["Precision", formatPercent(metrics?.precision), "Requires evaluation truth", "neutral"],
    ["Recall", formatPercent(metrics?.recall), "Requires evaluation truth", "neutral"],
    ["F1 score", formatPercent(metrics?.f1), "Requires evaluation truth", "neutral"],
    ["Processing time", formatDuration(metrics?.processing_time_ms), "Complete service run", "neutral"],
    ["Throughput", formatThroughput(metrics?.throughput), "Bank records", "neutral"],
  ];

  return (
    <div className="page-stack">
      <section className="hero">
        <div>
          <p className="eyebrow">FINANCE OPERATIONS</p>
          <h1>Reconciliation control room</h1>
          <p className="hero__copy">
            Start a deterministic run, inspect every decision, and route unresolved
            payments with evidence—not guesswork.
          </p>
        </div>
        <div className="run-launcher">
          <label htmlFor="batch-select">Source batch</label>
          <select
            id="batch-select"
            value={selectedBatch}
            onChange={(event) => onBatchChange(event.target.value)}
          >
            <option value="">Select a batch</option>
            {batches.map((batch) => (
              <option key={batch.source_batch} value={batch.source_batch}>
                {batch.source_batch} · {batch.bank_transactions} bank rows
              </option>
            ))}
          </select>
          <button
            type="button"
            className="button button--primary"
            disabled={!selectedBatch || starting}
            onClick={onStartRun}
          >
            {starting ? "Running reconciliation…" : "Start reconciliation"}
          </button>
        </div>
      </section>

      {error && <div className="alert alert--error" role="alert">{error}</div>}

      <section className="toolbar-card" aria-label="Selected run">
        <div>
          <span className="toolbar-card__label">Active run</span>
          {run ? (
            <div className="toolbar-card__run">
              <strong>{shortId(run.run_id, 12)}</strong>
              <StatusBadge status={run.status} />
              <span>{run.source_batch}</span>
            </div>
          ) : (
            <strong>No run selected</strong>
          )}
        </div>
        <div className="toolbar-card__actions">
          <label className="sr-only" htmlFor="run-history">Previous runs</label>
          <select
            id="run-history"
            value={run?.run_id || ""}
            onChange={(event) => onSelectRun(event.target.value)}
          >
            <option value="">Previous runs</option>
            {history.map((item) => (
              <option key={item.run_id} value={item.run_id}>
                {item.source_batch} · {item.status} · {shortId(item.run_id)}
              </option>
            ))}
          </select>
          {run && (
            <>
              <a className="button button--secondary" href={predictionUrl(run.run_id)}>
                Predictions CSV
              </a>
              <a className="button button--secondary" href={exceptionUrl(run.run_id)}>
                Exceptions CSV
              </a>
            </>
          )}
        </div>
      </section>

      {!run ? (
        <section className="surface">
          <EmptyState
            title="Choose a source batch"
            message="Metrics and decision distribution appear after a real API run."
          />
        </section>
      ) : (
        <>
          <section className="metric-grid" aria-label="Run metrics">
            {cards.map(([label, value, hint, tone]) => (
              <MetricCard
                key={label}
                label={label}
                value={value}
                hint={hint}
                tone={tone}
              />
            ))}
          </section>
          <section className="dashboard-grid">
            <article className="surface surface--chart">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">DECISION DISTRIBUTION</p>
                  <h2>Where every transaction landed</h2>
                </div>
                <span>{formatNumber(metrics?.total_records)} records</span>
              </div>
              <DistributionBars metrics={metrics} />
            </article>
            <article className="surface performance-panel">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">RUN PERFORMANCE</p>
                  <h2>Execution profile</h2>
                </div>
              </div>
              <dl className="performance-list">
                <div><dt>Candidate matching</dt><dd>{formatDuration(run.matching_time_ms)}</dd></div>
                <div><dt>Decision engine</dt><dd>{formatDuration(run.decision_time_ms)}</dd></div>
                <div><dt>Persistence</dt><dd>{formatDuration(run.persistence_time_ms)}</dd></div>
                <div><dt>Candidate pruning</dt><dd>{Number(run.comparison_reduction).toFixed(1)}%</dd></div>
              </dl>
              <p className="quality-note">
                Accuracy fields remain “Not evaluated” for production runs. Precision,
                recall, and F1 are calculated only by the truth-isolated Phase 11 pipeline.
              </p>
            </article>
          </section>
        </>
      )}
    </div>
  );
}
