import { useEffect, useState } from "react";

import EmptyState from "../components/EmptyState";
import Pagination from "../components/Pagination";
import StatusBadge from "../components/StatusBadge";
import { getResults, suggestAIMatch } from "../api/client";
import { formatConfidence, shortId } from "../utils/formatters";

const filters = [
  ["", "All"],
  ["matched", "Matched"],
  ["review", "Review"],
  ["exception", "Exception"],
];

export default function ResultsPage({ runId }) {
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState({ items: [], total: 0, page_size: 25 });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [suggestions, setSuggestions] = useState({});

  async function requestSuggestion(item) {
    setError("");
    try {
      const suggestion = await suggestAIMatch(runId, item.transaction_id);
      setSuggestions((current) => ({
        ...current,
        [item.id]: suggestion,
      }));
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  useEffect(() => {
    if (!runId) return undefined;
    let active = true;
    setLoading(true);
    setError("");
    getResults(runId, { page, pageSize: 25, status: filter })
      .then((response) => active && setData(response))
      .catch((requestError) => active && setError(requestError.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [runId, page, filter]);

  function changeFilter(value) {
    setFilter(value);
    setPage(1);
  }

  if (!runId) {
    return (
      <section className="surface">
        <EmptyState
          title="No reconciliation run selected"
          message="Start or select a run from Overview to inspect its results."
        />
      </section>
    );
  }

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="eyebrow">RECONCILIATION RESULTS</p>
          <h1>Every decision, fully traceable</h1>
          <p>Run {runId}</p>
        </div>
        <div className="segmented" aria-label="Result status filter">
          {filters.map(([value, label]) => (
            <button
              type="button"
              key={label}
              className={filter === value ? "is-active" : ""}
              onClick={() => changeFilter(value)}
            >
              {label}
            </button>
          ))}
        </div>
      </header>

      {error && <div className="alert alert--error" role="alert">{error}</div>}

      <section className="surface table-surface" aria-busy={loading}>
        {loading ? (
          <div className="loading-state">Loading reconciliation results…</div>
        ) : data.items.length === 0 ? (
          <EmptyState title="No results" message="No decisions match this filter." />
        ) : (
          <div className="table-scroll">
            <table>
              <caption className="sr-only">Reconciliation results</caption>
              <thead>
                <tr>
                  <th>Transaction</th>
                  <th>Invoice</th>
                  <th>Settlement</th>
                  <th>Status</th>
                  <th>Confidence</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.id}>
                    <td title={item.transaction_id}>{shortId(item.transaction_id, 12)}</td>
                    <td title={item.invoice_id || ""}>{shortId(item.invoice_id, 12)}</td>
                    <td title={item.settlement_id || ""}>{shortId(item.settlement_id, 12)}</td>
                    <td><StatusBadge status={item.status} /></td>
                    <td className="numeric">{formatConfidence(item.confidence)}</td>
                    <td className="reason-cell">
                      <span>{item.reason}</span>
                      {item.status !== "matched" && (
                        <button
                          type="button"
                          className="text-button"
                          onClick={() => requestSuggestion(item)}
                        >
                          AI assist
                        </button>
                      )}
                      {suggestions[item.id] && (
                        <small className="ai-suggestion">
                          {suggestions[item.id].explanation}
                        </small>
                      )}
                    </td>
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
    </div>
  );
}
