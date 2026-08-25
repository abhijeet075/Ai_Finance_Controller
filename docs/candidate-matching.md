# Phase 9 — Indexed candidate matching

Phase 9 adds `backend/app/services/candidate_matching.py`. It generates and scores small candidate
pools instead of comparing every bank transaction with every invoice and settlement. The Phase 8
baseline engine now consumes the same indexed invoice pool.

## Pipeline

```text
Bank transaction
  -> same-currency partition
  -> binary-search amount window
  -> exact-reference union for invoices
  -> cheap nearby-date / customer-token gate
  -> detailed deterministic scoring
  -> top three candidates
  -> confidence threshold and winner-margin gate
```

Indexes are built once per batch. Currency partitions, sorted amount arrays, and binary search make
lookup `O(log n + k)` per source, where `k` is the narrowed amount pool. Normalized customer names
are cached, and an inexpensive token gate runs before sequence similarity.

## Scores

Invoices use exact reference 30%, amount proximity 30%, date proximity 20%, and normalized customer
similarity 20%. Settlements use amount proximity 45%, date proximity 25%, and customer similarity
30%. Each candidate returns its overall score and complete feature breakdown.

Default auto-selection requires:

- confidence of at least 85%;
- a lead of at least 10 percentage points over the second candidate.

Otherwise the result remains unselected with `below_confidence_threshold` or
`insufficient_score_margin`. Currency is a hard filter. Failed and reversed settlements are
excluded. Results are deterministic and limited to the top three per source.

`CandidateBatch` reports theoretical Cartesian comparisons, records examined through the indexes,
and the comparison-reduction percentage.

## Verification

Tests cover ranking, thresholds, ambiguity, currency safety, settlement eligibility, deterministic
ordering, Phase 8 integration, and an indexed 1,000-invoice reduction check.
