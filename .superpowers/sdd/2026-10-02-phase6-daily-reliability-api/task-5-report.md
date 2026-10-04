# Task 5 report: least-privilege provisioning and Compose deployment

## Result

Committed as `0f069d5 feat: deploy query API with read-only identity`.

Changed only these six committed paths: `.env.example`, `database/init/02-create-query-api-user.sh`, `database/tests/test_migration.py`, `docker-compose.yml`, `services/query-api/Dockerfile`, and `tests/test_query_api_deployment.py`.

The new init script requires `QUERY_API_POSTGRES_PASSWORD`, passes it to psql as a variable, creates or rotates `netpulse_query_api`, restores restricted role attributes, removes inherited roles other than `netpulse_report`, and grants `netpulse_report` only when it exists. PostgreSQL receives the password during fresh initialization; `query-api-init` repeats provisioning after migration for existing volumes and to establish the report membership. The API profile has a non-root UID/GID 10001 image, a loopback-only port, dedicated login URL, explicit pool and timeout settings, and a standard-library `/healthz` check.

## Verification

- RED: `.venv\Scripts\python.exe -m pytest tests/test_query_api_deployment.py database/tests/test_migration.py -q -p no:cacheprovider` exited 1: 5 expected missing-artifact failures, 10 passed.
- GREEN: the same command exited 0: 15 passed in 0.26s.
- Compose: `docker compose --profile api config --quiet` exited 0, with two Docker CLI warnings that the sandbox could not read `C:\Users\GERAR\.docker\config.json`. Rerunning as `docker compose --profile api config --quiet 2>$null` exited 0 with no output. Setting `DOCKER_CONFIG` to an empty path made the Compose plugin unavailable on this host, so the final check used the existing CLI configuration.
- Static checks: `.venv\Scripts\python.exe -m ruff check tests/test_query_api_deployment.py database/tests/test_migration.py` and `.venv\Scripts\python.exe -m ruff format --check tests/test_query_api_deployment.py database/tests/test_migration.py` both exited 0. `git diff --cached --check` also exited 0.
- Full non-integration suite: `.venv\Scripts\python.exe -m pytest -q -m "not integration" -p no:cacheprovider` exited 0: 290 passed, 6 deselected, 1 warning in 42.08s. The warning was Starlette's AnyIO `BlockingPortal` deprecation. The command output also ended with `ERROR: Access denied` after the passing summary; the process exit code remained 0.

## Selective staging and self-review

Before commit, `git diff --cached --name-only` listed exactly the six Task 5 paths. `git add -p -- docker-compose.yml` staged hunks 1 and 2 (PostgreSQL password and API services) and rejected hunk 3 (the pre-existing Grafana volume change). After commit, `git diff -- docker-compose.yml` contains only that original Grafana change. Other dirty worktree files remain untouched and unstaged.

I checked the required service dependencies, profile, port, credential separation, image user, role grants, and health check against the brief. No Docker image build or live PostgreSQL provisioning test was run; the checks cover source contracts and Compose validity. Runtime database behavior remains the main unverified item.

## Fix round 1

### Changes

Added `services/query-api/src/netpulse_query_api/entrypoint.py`. It reads the five dedicated query-role connection components, percent-encodes the username, password, and database name, assigns `NETPULSE_DATABASE_URL`, and replaces itself with Uvicorn using `os.execvp`. Compose now gives the API only those components and the existing nonsecret tuning/log settings; it no longer injects a preassembled URL. The Dockerfile now invokes the entrypoint with JSON exec-form CMD.

Added `services/query-api/tests/test_entrypoint.py` to verify the URL round-trips the password `secret%41/@pass` unchanged through Psycopg's `conninfo_to_dict`, and checks the exec program, arguments, and generated environment. Updated deployment assertions for the component-based environment and JSON CMD. No credentials or URLs are logged.

### TDD and verification

- RED: `.venv\Scripts\python.exe -m pytest services/query-api/tests/test_entrypoint.py tests/test_query_api_deployment.py -q -p no:cacheprovider` exited 1: 3 failed, 2 passed. Failures showed the missing entrypoint, the old raw Compose URL, and the old shell-form CMD.
- GREEN: `.venv\Scripts\python.exe -m pytest services/query-api/tests/test_entrypoint.py tests/test_query_api_deployment.py database/tests/test_migration.py -q -p no:cacheprovider` exited 0: 16 passed in 0.45s. After final typing cleanup, rerun exited 0: 16 passed in 0.38s.
- Compose: `docker compose --profile api config --quiet 2>$null` exited 0 with no output.
- Ruff: `ruff check` on `entrypoint.py`, `test_entrypoint.py`, and `test_query_api_deployment.py` exited 0 (`All checks passed!`); `ruff format --check` on the same files exited 0 (`3 files already formatted`).
- Mypy: `.venv\Scripts\mypy.exe services/query-api/src/netpulse_query_api services/query-api/tests/test_entrypoint.py tests/test_query_api_deployment.py` exited 0: `Success: no issues found in 10 source files`.
- Full non-integration suite: `.venv\Scripts\python.exe -m pytest -q -m "not integration" -p no:cacheprovider` exited 0: 291 passed, 6 deselected, 1 Starlette/AnyIO deprecation warning in 44.14s. The process printed `ERROR: Access denied` after the passing summary despite exit code 0.

### Selective staging and self-review

Preserve the pre-existing Grafana volume change in `docker-compose.yml`; only the query-api environment hunk is part of this fix. Stage the entrypoint, its test, the Dockerfile change, deployment-test changes, and this report. All unrelated existing dirty paths remain untouched and unstaged.

Self-review confirmed the API has no raw URL, admin credential, or application credential in its Compose environment, the percent-encoded password parses back to the original reserved characters, and the Docker command uses exec form. No image build or live PostgreSQL provisioning was run; the existing runtime database limitation still applies. Fix-round code commit: `07558d4`.

## Fix round 2

### Changes

Added the `if __name__ == "__main__": main()` guard to `services/query-api/src/netpulse_query_api/entrypoint.py`. Added a regression to `services/query-api/tests/test_entrypoint.py` that runs the module as `__main__` with `os.execvp` replaced by a recorder, so it verifies the Docker `python -m` execution path without starting Uvicorn.

### TDD and verification

- RED: `.venv\Scripts\python.exe -m pytest services/query-api/tests/test_entrypoint.py::test_module_execution_invokes_uvicorn -q -p no:cacheprovider` exited 1: 1 failed. `runpy.run_module(..., run_name="__main__")` returned without any `os.execvp` call.
- GREEN: `.venv\Scripts\python.exe -m pytest services/query-api/tests/test_entrypoint.py tests/test_query_api_deployment.py database/tests/test_migration.py -q -p no:cacheprovider` exited 0: 18 passed in 0.48s.
- Ruff: `ruff check` on `entrypoint.py`, `test_entrypoint.py`, and `test_query_api_deployment.py` exited 0 (`All checks passed!`); `ruff format --check` on the same files exited 0 (`3 files already formatted`). The first Ruff lint pass caught unsorted imports in the new test; the imports were sorted and all final checks passed.
- Mypy: `.venv\Scripts\mypy.exe services/query-api/src/netpulse_query_api services/query-api/tests/test_entrypoint.py tests/test_query_api_deployment.py` exited 0: `Success: no issues found in 10 source files`.

### Self-review and concerns

The test exercises module execution with a controlled exec handoff, while the existing test continues to cover URL construction and the exact Uvicorn arguments. Only the module guard was added to production code. The live Compose `api-up` was not rerun in this fix round; runtime verification remains with Task 6. Fix-round-2 code commit: pending.
