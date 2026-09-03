import { useEffect, useState } from "react";

import EmptyState from "../components/EmptyState";
import ExceptionDrawer from "../components/ExceptionDrawer";
import Pagination from "../components/Pagination";
import StatusBadge from "../components/StatusBadge";
import { getExceptions } from "../api/client";
import {
  formatConfidence,
  formatCurrency,
  shortId,
  titleCase,
} from "../utils/formatters";

export default function ExceptionsPage({ runId }) {
  const [page, setPage] = useState(1);
  const [severity, setSeverity] = useState("");
  const [exceptionType, setExceptionType] = useState("");
  const [status, setStatus] = useState("");
  const [data, setData] = useState({ items: [], total: 0, page_size: 25 });
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!runId) return undefined;
    let active = true;
    setLoading(true);
    setError("");
    getExceptions(runId, {
      page,
      pageSize: 25,
      severity,
      exceptionType,
      status,
    })
      .then((response) => active && setData(response))
      .catch((requestError) => active && setError(requestError.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [runId, page, severity, exceptionType, status]);

  function updateFilter(setter, value) {
    setter(value);
    setPage(1);
  }

  if (!runId) {
    return (
      <section className="surface">
        <EmptyState
          title="No reconciliation run selected"
          message="Start or select a run from Overview to inspect its exceptions."
        />
      </section>
    );
  }

  return (
    <div className="page-stack">
      <header className="page-header page-header--exceptions">
        <div>
          <p className="eyebrow">EXCEPTION WORKBENCH</p>
          <h1>Resolve what automation could not</h1>
          <p>Click any row to inspect its financial evidence.</p>
        </div>
        <div className="filter-row">
          <label>
            <span>Severity</span>
            <select value={severity} onChange={(event) => updateFilter(setSeverity, event.target.value)}>
              <option value="">All</option>
              <option value="critical">Critical</option>
              <option value="warning">Warning</option>
              <option value="info">Info</option>
            </select>
          </label>
          <label>
            <span>Type</span>
            <select value={exceptionType} onChange={(event) => updateFilter(setExceptionType, event.target.value)}>
              <option value="">All</option>
              <option value="amount_mismatch">Amount mismatch</option>
              <option value="currency_mismatch">Currency mismatch</option>
              <option value="duplicate_payment">Duplicate payment</option>
              <option value="missing_settlement">Missing settlement</option>
              <option value="ambiguous_match">Ambiguous match</option>
              <option value="no_match">No match</option>
            </select>
          </label>
          <label>
            <span>Status</span>
            <select value={status} onChange={(event) => updateFilter(setStatus, event.target.value)}>
              <option value="">All</option>
              <option value="open">Open</option>
              <option value="in_review">In review</option>
              <option value="resolved">Resolved</option>
              <option value="dismissed">Dismissed</option>
            </select>
          </label>
        </div>
      </header>

      {error && <div className="alert alert--error" role="alert">{error}</div>}

      <section className="surface table-surface" aria-busy={loading}>
        {loading ? (
          <div className="loading-state">Loading exception evidence…</div>
        ) : data.items.length === 0 ? (
          <EmptyState title="No exceptions" message="No unresolved transactions match these filters." />
        ) : (
          <div className="table-scroll">
            <table className="clickable-table">
              <caption className="sr-only">Reconciliation exceptions</caption>
              <thead>
                <tr>
                  <th>Transaction</th>
                  <th>Type</th>
                  <th>Severity</th>
                  <th>Bank amount</th>
                  <th>Difference</th>
                  <th>Confidence</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr
                    key={item.id}
                    tabIndex="0"
                    onClick={() => setSelected(item)}
                    onKeyDown={(event) => event.key === "Enter" && setSelected(item)}
                  >
                    <td title={item.transaction_id}>{shortId(item.transaction_id, 12)}</td>
                    <td>{titleCase(item.exception_type)}</td>
                    <td><StatusBadge status={item.severity} /></td>
                    <td className="numeric">{formatCurrency(item.bank_amount, item.currency)}</td>
                    <td className="numeric">{formatCurrency(item.amount_difference, item.currency)}</td>
                    <td className="numeric">{formatConfidence(item.confidence)}</td>
                    <td><StatusBadge status={item.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pagination
          page={page}
          pageSize={data.page_size || 25}
          total={data.total}
          onPageChange={setPage}
        />
      </section>
      <ExceptionDrawer item={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
