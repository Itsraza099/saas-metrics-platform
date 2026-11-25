# 0002. Incremental, append-only loading with a watermark

- Status: Proposed
- Date: 2026-11-25

## Context
The source billing API holds the *current* state of each record, and records change:
plans get upgraded, invoices go from failed to paid. Reloading everything every day doesn't
scale, and overwriting rows would throw away the history that churn and expansion metrics
need.

## Decision
- **Source API pages with a keyset cursor** on `(updated_at, id)`, not an offset, so rows
  changing mid-read can't make a page skip or repeat anything.
- **Watermark per resource** in `raw._load_state`: the latest `updated_at` loaded. The next
  run asks for rows `updated_since` the watermark. `updated_since` is **inclusive**, so
  rows sharing the boundary timestamp are never missed.
- **Append-only raw**: one row per version, primary key `(id, source_updated_at)`, payload
  kept as JSON exactly as received. Raw is never updated or deleted.
- **Idempotent inserts** (`on conflict do nothing`): re-reading the boundary, a lookback
  window or a retried run can't create duplicates.
- **Commit per page**: each page's rows and the new watermark commit together. A crash keeps
  every finished page and the next run resumes from there.
- **Run log** in `raw._load_runs`: one row per run, with pages, rows fetched, rows inserted,
  status and error.
- **dbt staging picks the latest version** of each row; older versions stay in raw for
  history (slowly changing dimensions, MRR movements).

## Alternatives considered
- **Full reload every run.** Simplest, and self-healing, but cost grows with history rather
  than with change, and it loses intermediate versions.
- **Upsert into raw (keep only the latest).** Smaller tables, but history is gone and a bad
  load overwrites good data.
- **Offset pagination.** Easy to write, but rows that change during the read shift between
  pages and get skipped or duplicated.
- **Exclusive watermark (`>`).** Misses rows that share the watermark's timestamp. Inclusive
  plus idempotent inserts costs one re-read row per run and is always correct.

## Consequences
- Raw grows with every change, not just every record. Fine at this scale; at 100x we'd
  partition raw by load date.
- Changes made *between* two loads are collapsed into one version. Hourly loads would keep
  more detail; the source doesn't expose a change log.
- If the source ever writes `updated_at` values in the past (late commits), a lookback window
  (`--lookback-minutes`) re-reads recent rows safely.
