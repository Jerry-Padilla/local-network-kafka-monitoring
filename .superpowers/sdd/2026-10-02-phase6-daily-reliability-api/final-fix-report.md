# Final fix wave report

## Scope

Base: `ee0a141`

This single fix wave addresses all four Important findings from the final
whole-branch review. It preserves migration head `0008`, the direct daily-view
grant, zero inherited roles, grantor-aware cleanup, loopback publishing,
non-root execution, and secret handling.

## RED / GREEN evidence

1. Unicode cursor size
   - RED: the maximum-length non-BMP endpoint regression produced a 2,234
     character token and the HTTP continuation returned 422 (`2 failed`).
   - GREEN: canonical JSON now emits UTF-8 directly (`ensure_ascii=False`);
     the cursor round trip and HTTP continuation both pass while the token
     remains URL-safe, unpadded, strictly decoded, and at most 2,048
     characters.
2. Lossless stored/cursor keys
   - RED: stored and cursor identifiers `" agent "`, `" endpoint "`, and
     `" http "` were normalized to stripped values (`1 failed`).
   - GREEN: normalized request identifiers and lossless stored identifiers are
     separate types. Stored values retain leading/trailing whitespace while
     still rejecting empty/whitespace-only and overlong values. A two-page
     HTTP regression proves the exact ordering key survives the cursor.
3. Index-seek continuation
   - RED: the repository returned only the same-date batch, reported no
     lookahead, and emitted the old OR predicate (`1 failed`).
   - GREEN: continuation runs a same-date tuple-tail seek and, only when
     needed, an older-date seek in the same read-only transaction. Both use
     bound parameters, deterministic order, and a combined `limit + 1` cap.
     Unit tests prove query shape/bounds/order and live EXPLAIN acceptance
     proves the cursor predicates appear as index conditions without Sort or
     Incremental Sort.
4. Integration routing
   - RED: legacy selection included both query API modules and the API-specific
     marker selected nothing (`2 failed`).
   - GREEN: `api_integration` and `host_integration` markers are disjoint;
     legacy selection excludes both. `api-integration` starts and waits for
     the API before running the exact container-safe module. The delegated
     grant regression runs explicitly on the host through
     `api-provisioning-test`. CI and operator documentation use those routes.

Additional environment RED/GREEN:

- Docker build initially failed because inaccessible local `.superpowers`
  review artifacts entered the root build context. `.dockerignore` now excludes
  them; the full API image/test build completed.
- The host provisioning command initially selected a system Python without
  pytest. It now prefers the worktree `.venv` and falls back to the configured
  host Python; the host regression passed.

## Verification

- Focused query API, deployment, routing, and migration suites:
  `103 passed`.
- Full Python 3.12 non-integration suite with coverage:
  `307 passed, 13 deselected`, `87.14%` coverage, exit 0. The trailing
  `ERROR: Access denied` is the known post-exit PySpark taskkill noise.
- Migration contract suite: `11 passed`.
- Ruff formatting: `155 files already formatted`.
- Ruff lint: `All checks passed`.
- Strict mypy: `Success: no issues found in 73 source files`.
- Compose all-profile configuration: exit 0 (Docker config-file access warning
  only).
- Exact live API integration: `6 passed`.
- Explicit host provisioning regression: `1 passed`.
- Legacy integration collection: 6 selected legacy tests, 9 API/host tests
  deselected.
- API verifier: health OK; first page 1 row; second page 1 row.
- Repeated provisioning: exit 0.
- Live migration head: `0008`.
- Query API container: running, healthy, published only on
  `127.0.0.1:8000`.
- `git diff --check`: exit 0.

## Files changed

- Cursor/model/repository implementation and focused unit/HTTP tests under
  `services/query-api`.
- Live API and host provisioning tests plus executable selection contract
  under `tests`.
- Integration markers and routing in `pyproject.toml`, both operator scripts,
  `Makefile`, and CI.
- Operator documentation in `README.md` and `docs/query-api.md`.
- `.dockerignore` excludes local superpowers artifacts from image contexts.

## Concerns

- No load or scale benchmark was run or claimed.
- Existing unrelated dirty and untracked files were preserved and excluded
  from this change.
