import { useEffect, useState } from "react";
import { getForecast } from "../api/client";
import { formatCurrency } from "../utils/formatters";

const horizons = [7, 14, 30];
export default function ForecastPage({ sourceBatch }) {
  const [horizon, setHorizon] = useState(30);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setError("");
    getForecast({ horizonDays: horizon, sourceBatch })
      .then((value) => active && setData(value))
      .catch((requestError) => active && setError(requestError.message));
    return () => { active = false; };
  }, [horizon, sourceBatch]);
  const money = (value) => formatCurrency(value, data?.currency || "USD");
  return <div className="page-stack">
    <header className="page-header">
      <div><p className="eyebrow">CASH FORECASTING</p><h1>Know the runway before it changes</h1>
      <p>Database-backed projections with every component visible.</p></div>
      <div className="segmented" aria-label="Forecast horizon">
        {horizons.map((days) => <button type="button" key={days} className={horizon === days ? "is-active" : ""} onClick={() => setHorizon(days)}>{days} days</button>)}
      </div>
    </header>
    {error && <div className="alert alert--error">{error}</div>}
    {data && <>
      <section className="forecast-equation" aria-label="Cash forecast equation">
        <div><span>Current cash</span><strong>{money(data.current_cash)}</strong></div><b>+</b>
        <div><span>Expected receipts</span><strong>{money(data.expected_receipts)}</strong></div><b>−</b>
        <div><span>Expected expenses</span><strong>{money(data.expected_expenses)}</strong></div><b>−</b>
        <div><span>Pending settlements</span><strong>{money(data.pending_settlements)}</strong></div><b>=</b>
        <div className="forecast-equation__result"><span>Projected cash</span><strong>{money(data.projected_cash)}</strong></div>
      </section>
      <section className="surface table-surface">
        <div className="section-heading"><div><p className="eyebrow">DAILY OUTLOOK</p><h2>{horizon}-day movement</h2></div><span>As of {data.as_of_date}</span></div>
        <div className="table-scroll"><table><thead><tr><th>Date</th><th>Receipts</th><th>Expenses</th><th>Pending</th><th>Projected cash</th></tr></thead>
        <tbody>{data.series.map((row) => <tr key={row.date}><td>{row.date}</td><td className="numeric positive">{money(row.expected_receipts)}</td><td className="numeric">{money(row.expected_expenses)}</td><td className="numeric">{money(row.pending_settlements)}</td><td className="numeric"><strong>{money(row.projected_cash)}</strong></td></tr>)}</tbody></table></div>
      </section>
      <section className="surface assumptions"><p className="eyebrow">ASSUMPTIONS</p><ul>{data.assumptions.map((item) => <li key={item}>{item}</li>)}</ul></section>
    </>}
  </div>;
}
