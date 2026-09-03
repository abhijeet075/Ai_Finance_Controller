import { useEffect } from "react";

import StatusBadge from "./StatusBadge";
import {
  formatConfidence,
  formatCurrency,
  titleCase,
} from "../utils/formatters";

export default function ExceptionDrawer({ item, onClose }) {
  useEffect(() => {
    if (!item) return undefined;
    function closeOnEscape(event) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [item, onClose]);

  if (!item) return null;

  const candidateLabel =
    item.best_candidate_type === "invoice"
      ? "Best invoice candidate"
      : item.best_candidate_type === "settlement"
        ? "Best settlement candidate"
        : "Best candidate";

  return (
    <div className="drawer-layer" role="presentation" onMouseDown={onClose}>
      <aside
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="exception-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="drawer__header">
          <div>
            <p className="eyebrow">EXCEPTION DETAIL</p>
            <h2 id="exception-title">{item.transaction_id}</h2>
          </div>
          <button
            type="button"
            className="icon-button"
            aria-label="Close exception details"
            onClick={onClose}
          >
            ×
          </button>
        </div>

        <div className="drawer__badges">
          <StatusBadge status={item.predicted_status} />
          <StatusBadge status={item.severity}>{titleCase(item.severity)}</StatusBadge>
          <StatusBadge status={item.status}>{titleCase(item.status)}</StatusBadge>
        </div>

        <section className="amount-panel" aria-label="Financial evidence">
          <div>
            <span>Bank amount</span>
            <strong>{formatCurrency(item.bank_amount, item.currency)}</strong>
          </div>
          <div>
            <span>Invoice amount</span>
            <strong>{formatCurrency(item.invoice_amount, item.currency)}</strong>
          </div>
          <div>
            <span>Settlement amount</span>
            <strong>{formatCurrency(item.settlement_amount, item.currency)}</strong>
          </div>
          <div className="amount-panel__difference">
            <span>Amount difference</span>
            <strong>{formatCurrency(item.amount_difference, item.currency)}</strong>
          </div>
        </section>

        <dl className="detail-list">
          <div>
            <dt>Type</dt>
            <dd>{titleCase(item.exception_type)}</dd>
          </div>
          <div>
            <dt>Confidence</dt>
            <dd>{formatConfidence(item.confidence)}</dd>
          </div>
          <div>
            <dt>{candidateLabel}</dt>
            <dd>{item.best_candidate_id || "No eligible candidate"}</dd>
          </div>
          <div>
            <dt>Invoice</dt>
            <dd>{item.invoice_id || "Not assigned"}</dd>
          </div>
          <div>
            <dt>Settlement</dt>
            <dd>{item.settlement_id || "Not assigned"}</dd>
          </div>
        </dl>

        <section className="narrative">
          <p className="eyebrow">REASON</p>
          <p>{item.description}</p>
        </section>
        <section className="narrative narrative--action">
          <p className="eyebrow">RECOMMENDED ACTION</p>
          <p>{item.recommended_action}</p>
        </section>
      </aside>
    </div>
  );
}
