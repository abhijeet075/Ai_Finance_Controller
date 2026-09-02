# Phase 11 recheck

The September 2 recheck corrected the following reliability issues before delivery:

1. All three source files are now validated before persistence, then inserted in one database
   transaction. A failure can no longer leave only part of an evaluation batch stored.
2. End-to-end evaluation now fails closed when hidden truth, predictions, or the unresolved
   exception report do not cover the complete bank-transaction population.
3. Matrix manifests reject missing keys, empty lists, duplicate sizes, duplicate source batches,
   blank source batches, and declared sizes that disagree with actual source rows.
4. Currency-mismatch exceptions now preserve the cross-currency amount-matched record as diagnostic
   evidence instead of reporting no best candidate.
5. Exact-reference amount mismatches now preserve the nearest referenced invoice, invoice amount,
   and absolute difference even when candidate hard gates reject it.
6. Debit rows retain the required `no_match` class but now explain that they are outside the
   receivables workflow rather than incorrectly claiming that no candidate existed.
7. Existing upload API behavior remains compatible because transactional batch persistence is
   opt-in; ordinary upload calls still commit as before.

Verification includes compilation, deterministic reconciliation tests, normalization, hidden-truth
isolation, generator semantics, evaluation metrics, coverage checks, and archive integrity. Run the
full PostgreSQL/FastAPI suite locally before merging because the sandbox does not contain those
runtime dependencies.
