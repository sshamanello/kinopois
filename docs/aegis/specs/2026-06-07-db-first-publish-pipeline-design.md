# DB-First Publish Pipeline

## TaskIntentDraft

- Goal: remove `pins.csv` from the critical path and write publishable pin rows directly into Postgres.
- Success evidence: the daily pipeline creates or updates `kinopois_pins` directly, n8n reads from that table, and the publish flow no longer depends on `pins.csv`.
- Stop condition: the DB-first path is specified clearly enough to implement without ambiguity.
- Non-goals: redesigning poster generation, changing Pinterest content rules, or reworking Google Sheets semantics unless they depend on the new source-of-truth.

## BaselineReadSetHint

- [kinopois/publishing/export.py](/Users/nick/code/kinopois/kinopois/publishing/export.py)
- [kinopois/publishing/postgres_queue.py](/Users/nick/code/kinopois/kinopois/publishing/postgres_queue.py)
- [kinopois/publishing/pipeline_steps.py](/Users/nick/code/kinopois/kinopois/publishing/pipeline_steps.py)
- [kinopois/cli.py](/Users/nick/code/kinopois/kinopois/cli.py)
- [deploy/cron-setup.sh](/Users/nick/code/kinopois/deploy/cron-setup.sh)
- n8n workflow `Pinterest KinoVezde Base64`

## ImpactStatementDraft

- Affected layers: exporter, queue sync, CLI, daily scheduler, n8n input contract.
- Canonical owner: `kinopois_pins` for publishable rows.
- Compatibility boundary: `pins.csv` may remain as an optional debug/export artifact, but it must not be required for publication.
- Invariant: published and failed rows remain immutable across later syncs.

## Product Risk Lens

- Value: remove a redundant intermediate file and reduce stale queue drift.
- Non-goals: changing the visual/title generation strategy.
- Trade-offs: direct DB writes simplify the path, but reduce the convenience of inspecting a standalone CSV artifact.
- Decision made: `pins.csv` is removed from the default pipeline and kept only as an explicit, manual export/debug artifact.

## Architecture Integrity Lens

- Invariant: the publish queue must have a single canonical write path.
- Canonical owner / contract: Postgres `kinopois_pins` should be written directly by the pipeline and read by n8n.
- Responsibility overlap: today CSV export and DB sync both participate in queue creation.
- Higher-level simplification: make CSV optional and derive it only when explicitly requested.
- Retirement / falsifier: if a later run still requires `pins.csv` to populate the queue, the DB-first change is incomplete.
- Verdict: `kinopois_pins` is the correct runtime source-of-truth for publishable rows.

## Baseline Role Alignment

- Product / Requirement Baseline: the user wants publishable rows to go straight into the database.
- Architecture / Runtime Boundary Baseline: n8n already publishes from `kinopois_pins`, so the queue owner should become the direct writer.
- Result: aligned
- scope: both
- Next action: implement a direct DB writer and demote `pins.csv` to optional export.

## Plan-Time Complexity Check

- Better file boundary: `export.py` currently owns CSV generation and should gain a DB-write path or delegate to a DB writer helper.
- Recommendation: extract helper rather than grow the CLI.

## Options

1. Direct DB writer in exporter
   - `export_movie_pins_csv` becomes `export_movie_pins_to_db` or calls a DB helper after building rows.
   - Lowest runtime drift, but larger refactor in the exporter.
2. Split builder and writer
   - Keep a pure row-builder, add a DB persistence helper, and optionally keep CSV export as a debug-only path.
   - Best balance of testability and migration safety.
3. Move all publishable-row creation into the queue layer
   - Queue layer becomes the sole owner of row construction and persistence.
   - Clean ownership, but wider blast radius and more code movement.

## Decision Needed

- Recommended path: option 2.
- Rationale: it preserves the current row-building logic while removing the CSV dependency from the main flow.
- Final boundary: no default command should require `pins.csv` for publication.

## Proposed Design

### Canonical flow

1. Download movie metadata and posters.
2. Process/clean movie rows.
3. Build publishable pin rows in memory.
4. Upsert those rows directly into `kinopois_pins`.
5. Let n8n publish from `kinopois_pins`.

### CSV role after the change

- `pins.csv` is no longer required for the main pipeline.
- It may be kept only as an explicit export/debug artifact if we still want a human-readable snapshot.
- Default commands should no longer depend on it.

### Queue semantics

- Upsert by `id` remains the dedupe key.
- `published`, `failed`, and `posted` rows remain terminal and immutable under later syncs.
- `ready` rows can still be refreshed from newer data for rows that are not terminal.

### CLI / scheduler behavior

- `run-base-pipeline` and daily prepare should write directly to DB.
- `queue-sync` becomes optional or legacy-only, not the default path.
- The daily cron should no longer require a `pins.csv` handoff to populate the publish queue.

## Acceptance Criteria

- A daily run can populate `kinopois_pins` without writing or reading `pins.csv`.
- n8n can keep publishing from `kinopois_pins` unchanged or with a minimal query update.
- Existing published/failed rows remain stable after a new harvest.
- The default pipeline does not require `pins.csv` to exist for publication.

## Risks

- A direct DB write path could accidentally diverge from the current CSV field contract.
- Any downstream consumer that still expects `pins.csv` may need a compatibility switch.
- If the queue writer is not carefully separated from the row builder, the exporter may become harder to test.
