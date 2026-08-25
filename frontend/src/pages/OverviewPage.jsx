import MetricCard from "../components/MetricCard";
import StatusBadge from "../components/StatusBadge";

const metrics = [
  ["Records processed", "—", "Awaiting first run"],
  ["Automatic match rate", "—", "Target ≥ 85%"],
  ["Exceptions", "—", "Honest unresolved queue"],
  ["30-day cash", "—", "Forecast not generated"],
];

export default function OverviewPage({ apiHealthy }) {
  return (
    <main>
      <header className="topbar">
        <div><p className="eyebrow">CONTROL ROOM</p><h1>AI Finance Controller</h1></div>
        <StatusBadge healthy={apiHealthy}>{apiHealthy ? "API connected" : "API unavailable"}</StatusBadge>
      </header>
      <section className="intro" aria-labelledby="overview-title">
        <div><p className="eyebrow">OVERVIEW</p><h2 id="overview-title">Run the books. See the cash.</h2><p>Reconcile three sources, surface exceptions, and forecast liquidity with evidence attached to every decision.</p></div>
        <button type="button" disabled>Start reconciliation</button>
      </section>
      <section className="metric-grid" aria-label="Finance metrics">
        {metrics.map(([label, value, hint]) => <MetricCard key={label} label={label} value={value} hint={hint} />)}
      </section>
      <section className="workspace">
        <article className="panel">
          <div className="panel-head"><div><p className="eyebrow">RECONCILIATION</p><h3>Decision pipeline</h3></div><StatusBadge>Not run</StatusBadge></div>
          <ol className="pipeline"><li><b>01</b><div><strong>Ingest</strong><span>Bank · invoices · settlements</span></div></li><li><b>02</b><div><strong>Normalize</strong><span>Dates · currency · references</span></div></li><li><b>03</b><div><strong>Match and score</strong><span>Evidence · confidence · conflicts</span></div></li><li><b>04</b><div><strong>Resolve</strong><span>Matched · review · exception</span></div></li></ol>
        </article>
        <article className="panel forecast">
          <div className="panel-head"><div><p className="eyebrow">CASH POSITION</p><h3>30-day outlook</h3></div><StatusBadge>No data</StatusBadge></div>
          <div className="empty-chart" aria-label="Empty forecast chart"><div className="chart-line" /><p>Forecast will appear after verified records are available.</p></div>
        </article>
      </section>
    </main>
  );
}
