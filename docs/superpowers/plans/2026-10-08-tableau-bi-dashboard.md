# Tableau BI Dashboard Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a tested, privacy-conscious, atomic CSV exporter for Tableau Public using NetPulse's existing PostgreSQL reporting views.

**Architecture:** Extend the existing analytics Python distribution with a focused `netpulse_analytics.tableau` package. A read-only repository loads one repeatable-read database snapshot, pure transformations build four deterministic dataset contracts, and an atomic directory publisher replaces the prior export only after every CSV is complete. Existing Docker, Make, POSIX, and PowerShell entrypoints expose the optional command without adding Tableau to the runtime path.

**Tech Stack:** Python 3.12, Psycopg 3, standard-library `csv`/`hashlib`/`pathlib`, Pytest, Docker Compose, Bash, PowerShell, Markdown/Mermaid.

**Spec:** `docs/superpowers/specs/2026-10-08-tableau-bi-dashboard-design.md`

## Global Constraints

- Query only `v_daily_probe_reliability`, `v_incident_summary`, `v_sre_agent_status`, and `v_sre_pipeline_status`; do not read operational tables.
- Do not export display names, endpoint/target identifiers, addresses, SSIDs, BSSIDs, environment values, or credentials.
- Represent all percentages on a 0-to-100 scale and all latency/duration values in milliseconds.
- Use UTC dates and ISO 8601 UTC timestamps with a `Z` suffix; serialize nulls as empty CSV fields.
- Generate UTF-8 CSV with LF line endings, fixed column order, and deterministic row order.
- Replace all four output files as one directory-level publication; preserve the previous valid export on failure.
- Keep Tableau, Tableau credentials, and Tableau publishing out of NetPulse runtime dependencies and CI.
- Preserve existing Kafka, Spark, PostgreSQL, Grafana, monitoring, API, test, and deployment behavior.
- Follow TDD for every production behavior: observe the focused test fail for the intended reason before adding implementation.

## Review Focus

- Empty reporting views must still produce four header-only/snapshot-appropriate files without inventing observations; pin this in Tasks 3 and 4.
- Multiple endpoint-grain daily rows for the same public grain must use summed numerators/denominators, never averages of averages; pin this in Task 3.
- Naive or non-UTC incident/pipeline timestamps must be normalized only when unambiguous and rejected otherwise; pin this in Task 3.
- Dangerous output paths (filesystem root, current working directory, symlink, or existing regular file) must be rejected before any rename; pin this in Task 4.
- Database and filesystem errors must return a nonzero CLI result without exposing the database URL or damaging a prior export; pin this in Tasks 4 and 5.

---

### Task 1: Tableau Data and Configuration Contracts

**Files:**
- Create: `services/analytics/src/netpulse_analytics/tableau/__init__.py`
- Create: `services/analytics/src/netpulse_analytics/tableau/models.py`
- Modify: `services/analytics/src/netpulse_analytics/config.py`
- Create: `services/analytics/tests/test_tableau_config.py`

**Interfaces:**
- Consumes: existing `NETPULSE_DATABASE_URL` environment convention.
- Produces: `TableauExportConfig(database_url: str, output_dir: Path)`, `DailyReliabilitySource`, `IncidentSource`, `PipelineHealthSource`, `TableauSnapshot`, `CsvDataset(columns: tuple[str, ...], rows: tuple[tuple[CsvValue, ...], ...])`, and `ExportBundle(datasets: Mapping[str, CsvDataset])`.
- Define `CsvValue = str | int | float | None`; source timestamp fields use aware `datetime`, date fields use `date`, and source aggregate sums use `float | None` with explicit count fields.

- [ ] **Step 1: Write failing configuration and model tests**

Add tests named:

- `test_tableau_config_uses_existing_database_url_and_explicit_output_dir`
- `test_tableau_config_rejects_missing_database_url`
- `test_csv_dataset_rejects_rows_with_the_wrong_width`
- `test_snapshot_defaults_to_empty_daily_and_incident_rows`

Assert that `Path("tableau_exports")` is preserved as a path, the existing error names `NETPULSE_DATABASE_URL`, and invalid dataset row widths raise `ValueError`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python -m pytest services/analytics/tests/test_tableau_config.py -v`

Expected: collection/import failure because `netpulse_analytics.tableau.models` and `TableauExportConfig` do not exist.

- [ ] **Step 3: Implement the contracts**

Add frozen, slotted dataclasses with the exact names and field types above. Implement `TableauExportConfig.from_env(output_dir: Path) -> TableauExportConfig` beside `AnalyticsConfig` and retain the existing error behavior.

- [ ] **Step 4: Run the focused tests and existing analytics tests**

Run: `python -m pytest services/analytics/tests/test_tableau_config.py services/analytics/tests/test_config.py services/analytics/tests/test_cli.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/analytics/src/netpulse_analytics/config.py services/analytics/src/netpulse_analytics/tableau services/analytics/tests/test_tableau_config.py
git commit -m "feat(analytics): define Tableau export contracts"
```

### Task 2: Read-Only Reporting Snapshot Repository

**Files:**
- Create: `services/analytics/src/netpulse_analytics/tableau/repository.py`
- Create: `services/analytics/tests/test_tableau_repository.py`

**Interfaces:**
- Consumes: Task 1 source dataclasses and `NETPULSE_DATABASE_URL` value.
- Produces: `PostgresTableauRepository(database_url: str)` and `load_snapshot() -> TableauSnapshot`.
- `load_snapshot` performs all reads in one `REPEATABLE READ READ ONLY` transaction after `SET LOCAL TIME ZONE 'UTC'`.

- [ ] **Step 1: Write failing repository tests with a fake Psycopg connection**

Add tests named:

- `test_repository_reads_only_approved_reporting_views_in_one_utc_snapshot`
- `test_repository_maps_null_aggregates_and_end_times_without_coercing_to_zero`
- `test_repository_orders_every_query_explicitly`
- `test_repository_propagates_database_connection_failure`

The fake connection must record SQL and return representative rows. Assert that SQL contains only the four approved `v_` view names, joins daily reliability to agent status by `agent_id`, contains no operational table names, begins a read-only repeatable-read transaction, and constructs the exact Task 1 dataclasses.

- [ ] **Step 2: Run the focused repository tests and verify RED**

Run: `python -m pytest services/analytics/tests/test_tableau_repository.py -v`

Expected: import failure because `PostgresTableauRepository` does not exist.

- [ ] **Step 3: Implement `PostgresTableauRepository.load_snapshot`**

Use one `psycopg.connect` context and one transaction. Select the raw daily aggregate inputs (`total_count`, `success_count`, `failure_count`, `latency_count`, `latency_sum_ms`, `packet_loss_count`, `packet_loss_sum_pct`) plus `agent_role`; do not consume precomputed means when weighted aggregation can use the numerators. Map incident and pipeline columns exactly as specified.

- [ ] **Step 4: Run repository and existing analytics repository tests**

Run: `python -m pytest services/analytics/tests/test_tableau_repository.py services/analytics/tests -k "repository or tableau" -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/analytics/src/netpulse_analytics/tableau/repository.py services/analytics/tests/test_tableau_repository.py
git commit -m "feat(analytics): load read-only Tableau reporting snapshot"
```

### Task 3: Deterministic Transformations and Privacy

**Files:**
- Create: `services/analytics/src/netpulse_analytics/tableau/transform.py`
- Create: `services/analytics/tests/test_tableau_transform.py`

**Interfaces:**
- Consumes: Task 1 `TableauSnapshot` and source dataclasses.
- Produces: `pseudonymize_agent(agent_id: str) -> str` and `build_export_bundle(snapshot: TableauSnapshot) -> ExportBundle`.
- Dataset filenames and column tuples must exactly match the design specification.

- [ ] **Step 1: Write failing daily reliability tests**

Add tests named:

- `test_daily_reliability_has_exact_columns_and_logical_sort_order`
- `test_daily_reliability_aggregates_endpoint_rows_with_weighted_metrics`
- `test_daily_reliability_emits_empty_fields_for_unmeasured_latency_and_loss`
- `test_empty_daily_snapshot_produces_header_only_daily_and_agent_datasets`

Use two endpoint-grain rows with deliberately different counts so an average-of-averages implementation fails. Assert `success_rate_pct = 100 * sum(success) / sum(total)`, latency uses `sum(latency_sum_ms) / sum(latency_count)`, and loss uses the corresponding loss numerator/count.

- [ ] **Step 2: Run those tests and verify RED**

Run: `python -m pytest services/analytics/tests/test_tableau_transform.py -k "daily or empty" -v`

Expected: import failure because `build_export_bundle` does not exist.

- [ ] **Step 3: Implement daily and agent-performance transformations**

Use tuple keys `(date_utc, agent_key, agent_role, source_kind, measurement_type)` and `(agent_key, agent_role, source_kind, measurement_type)`. Calculate dates, day counts, integer totals, and weighted metrics from aggregate inputs. Sort by the exact contract order.

- [ ] **Step 4: Run daily tests and verify GREEN**

Run: `python -m pytest services/analytics/tests/test_tableau_transform.py -k "daily or empty" -v`

Expected: PASS.

- [ ] **Step 5: Write failing incident, health, timestamp, duplicate, and privacy tests**

Add tests named:

- `test_incidents_have_exact_columns_utc_timestamps_and_stable_order`
- `test_pipeline_health_has_exact_columns_and_utc_timestamps`
- `test_non_utc_aware_timestamp_is_converted_to_utc`
- `test_naive_timestamp_is_rejected`
- `test_equal_duplicate_incidents_collapse_but_conflicts_raise`
- `test_agent_keys_are_stable_namespaced_digests_and_raw_identifiers_never_appear`
- `test_export_bundle_contains_only_four_expected_filenames`

Assert keys match `agent_[0-9a-f]{12}`, identical identifiers produce identical keys, different identifiers do not, and no serialized row contains the raw agent identifier or any excluded field name.

- [ ] **Step 6: Run the new tests and verify RED**

Run: `python -m pytest services/analytics/tests/test_tableau_transform.py -k "incident or pipeline or timestamp or duplicate or agent_keys or filenames" -v`

Expected: FAIL because those datasets and validations are not implemented.

- [ ] **Step 7: Implement incident, pipeline, timestamp, duplicate, and privacy behavior**

Use the namespace bytes `b"netpulse-tableau-agent-v1\0"`, SHA-256, a 12-hex digest prefix, and the `agent_` display prefix. Convert aware datetimes with `astimezone(timezone.utc)` and format seconds or available microseconds with a terminal `Z`; reject naive datetimes with `ValueError`. Collapse exactly equal incident duplicates and reject conflicting rows sharing an incident ID.

- [ ] **Step 8: Run the full transformation tests**

Run: `python -m pytest services/analytics/tests/test_tableau_transform.py -v`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add services/analytics/src/netpulse_analytics/tableau/transform.py services/analytics/tests/test_tableau_transform.py
git commit -m "feat(analytics): build privacy-safe Tableau datasets"
```

### Task 4: CSV Rendering and Atomic Directory Publication

**Files:**
- Create: `services/analytics/src/netpulse_analytics/tableau/exporter.py`
- Create: `services/analytics/tests/test_tableau_exporter.py`

**Interfaces:**
- Consumes: Task 1 `ExportBundle` and Task 3 deterministic datasets.
- Produces: `publish_export(bundle: ExportBundle, output_dir: Path) -> None`.
- Internal boundaries: `_validate_output_path(output_dir: Path) -> Path`, `_write_staging(bundle: ExportBundle, staging_dir: Path) -> None`, and `_swap_directories(staging_dir: Path, output_dir: Path) -> None`.

- [ ] **Step 1: Write failing CSV rendering tests**

Add tests named:

- `test_publish_export_writes_exact_headers_utf8_lf_and_empty_null_fields`
- `test_publish_export_creates_all_four_csvs_for_empty_datasets`
- `test_publish_export_replaces_a_complete_previous_export`

Read files with `newline=""`, assert exact header order, no `\r\n`, UTF-8 text, empty fields for `None`, and exactly the four expected filenames.

- [ ] **Step 2: Run rendering tests and verify RED**

Run: `python -m pytest services/analytics/tests/test_tableau_exporter.py -k "writes or empty or replaces" -v`

Expected: import failure because `publish_export` does not exist.

- [ ] **Step 3: Implement staging and successful directory swap**

Create staging and backup directories as unique siblings of `output_dir` using `tempfile.mkdtemp(dir=output_dir.parent, prefix=f".{output_dir.name}.")`. Use `csv.writer(..., lineterminator="\n")`; close all handles before calling `os.replace`.

- [ ] **Step 4: Run rendering tests and verify GREEN**

Run: `python -m pytest services/analytics/tests/test_tableau_exporter.py -k "writes or empty or replaces" -v`

Expected: PASS.

- [ ] **Step 5: Write failing failure-safety and path-validation tests**

Add tests named:

- `test_staging_write_failure_preserves_previous_export`
- `test_second_rename_failure_restores_previous_export`
- `test_database_independent_publication_never_leaves_backup_as_active_output`
- `test_rejects_filesystem_root_current_directory_symlink_and_regular_file`
- `test_cleanup_failure_does_not_mask_the_primary_publication_error`

Inject failures by monkeypatching the module's CSV-write helper, `os.replace`, and cleanup helper at the named boundaries. Assert the old marker file remains byte-for-byte unchanged.

- [ ] **Step 6: Run failure-safety tests and verify RED**

Run: `python -m pytest services/analytics/tests/test_tableau_exporter.py -k "failure or preserves or restores or rejects or cleanup" -v`

Expected: FAIL until rollback and validation are implemented.

- [ ] **Step 7: Implement rollback, validation, and best-effort cleanup**

Resolve but do not dereference accepted output directories after checking symlinks. Reject the filesystem root, `Path.cwd()`, symlinks, and existing non-directories before creating staging state. On second rename failure, restore the backup with `os.replace`; preserve the primary exception if cleanup also fails.

- [ ] **Step 8: Run all exporter tests**

Run: `python -m pytest services/analytics/tests/test_tableau_exporter.py -v`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add services/analytics/src/netpulse_analytics/tableau/exporter.py services/analytics/tests/test_tableau_exporter.py
git commit -m "feat(analytics): publish Tableau CSVs atomically"
```

### Task 5: Export Service and CLI Failure Behavior

**Files:**
- Create: `services/analytics/src/netpulse_analytics/tableau/service.py`
- Create: `services/analytics/src/netpulse_analytics/tableau/cli.py`
- Modify: `services/analytics/pyproject.toml`
- Create: `services/analytics/tests/test_tableau_cli.py`

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: `export_tableau(config: TableauExportConfig, repository: PostgresTableauRepository | None = None) -> ExportSummary`, `parse_args(argv: list[str] | None) -> Path`, `main(argv: list[str] | None = None) -> int`, and console script `netpulse-tableau-export`.
- `ExportSummary` is a frozen dataclass containing `output_dir: Path` and `row_counts: Mapping[str, int]`.

- [ ] **Step 1: Write failing service and CLI tests**

Add tests named:

- `test_export_service_loads_transforms_and_publishes_once`
- `test_cli_defaults_to_tableau_exports_and_accepts_output_dir`
- `test_cli_reports_successful_row_counts_without_sensitive_configuration`
- `test_missing_database_configuration_returns_nonzero_without_touching_output`
- `test_database_failure_returns_nonzero_preserves_prior_export_and_redacts_url`
- `test_filesystem_failure_returns_nonzero_and_preserves_prior_export`

Capture stdout/stderr and assert that a sentinel password embedded in a test database URL never appears. Test service behavior with an injected fake repository; test CLI behavior by monkeypatching the service boundary, not Psycopg internals.

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest services/analytics/tests/test_tableau_cli.py -v`

Expected: import failure because the service and CLI do not exist.

- [ ] **Step 3: Implement service orchestration and CLI**

`export_tableau` must call `load_snapshot`, `build_export_bundle`, and `publish_export` exactly once in that order. `main` must return `0` on success and `1` for configuration, Psycopg, transformation, or filesystem errors; print a concise generic failure message plus the exception type, not the exception string or database URL.

- [ ] **Step 4: Register the console script**

Add `netpulse-tableau-export = "netpulse_analytics.tableau.cli:main"` under `[project.scripts]` without changing the existing `netpulse-analytics` entrypoint.

- [ ] **Step 5: Run CLI and complete analytics tests**

Run: `python -m pytest services/analytics/tests -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/analytics/src/netpulse_analytics/tableau/service.py services/analytics/src/netpulse_analytics/tableau/cli.py services/analytics/pyproject.toml services/analytics/tests/test_tableau_cli.py
git commit -m "feat(analytics): expose Tableau export CLI"
```

### Task 6: Cross-Platform Operator Commands and Compose Output Mount

**Files:**
- Modify: `.gitignore`
- Modify: `docker-compose.yml`
- Modify: `Makefile`
- Modify: `scripts/netpulse.sh`
- Modify: `scripts/netpulse.ps1`
- Create: `tests/test_tableau_deployment.py`

**Interfaces:**
- Consumes: Task 5 `netpulse-tableau-export --output-dir /exports`.
- Produces: `make tableau-export`, `./scripts/netpulse.sh tableau-export`, and `./scripts/netpulse.ps1 tableau-export`.

- [ ] **Step 1: Write failing static deployment tests**

Add tests named:

- `test_tableau_export_is_available_in_make_bash_and_powershell`
- `test_analytics_service_mounts_only_generated_tableau_output_for_writing`
- `test_tableau_exports_are_gitignored`
- `test_tableau_command_runs_migrations_then_read_only_export`
- `test_posix_command_uses_host_uid_gid_without_changing_image_user`

Assert `tableau-export` appears in `.PHONY`, the Make forwarding list, Bash case, and PowerShell `ValidateSet`/switch; Compose maps `./tableau_exports:/exports`; the command does not expose a port; the scripts invoke migrations before export; and Dockerfile `USER netpulse` remains unchanged.

- [ ] **Step 2: Run deployment tests and verify RED**

Run: `python -m pytest tests/test_tableau_deployment.py -v`

Expected: FAIL because no operator wiring exists.

- [ ] **Step 3: Add the generated-output mount and ignore rule**

Ignore `/tableau_exports/`. Add `./tableau_exports:/exports` only to the optional `analytics` service; do not add ports or a new service.

- [ ] **Step 4: Add Make, Bash, and PowerShell commands**

Each wrapper must create the host output directory, start/wait for PostgreSQL, build `migrate` and `analytics`, run migrations, and invoke the new console script with `/exports`. Bash must pass `--user "$(id -u):$(id -g)"` and `HOME=/tmp`; PowerShell must rely on Docker Desktop bind-mount handling and retain the image's non-root user.

- [ ] **Step 5: Run deployment tests and Compose validation**

Run: `python -m pytest tests/test_tableau_deployment.py -v`

Expected: PASS.

Run: `docker compose -f docker-compose.yml config --quiet`

Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add .gitignore docker-compose.yml Makefile scripts/netpulse.sh scripts/netpulse.ps1 tests/test_tableau_deployment.py
git commit -m "feat: add cross-platform Tableau export command"
```

### Task 7: Tableau Workbook, Privacy, README, and Architecture Documentation

**Files:**
- Create: `docs/tableau-dashboard.md`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `tests/test_tableau_deployment.py`

**Interfaces:**
- Consumes: Tasks 1-6 dataset names, columns, commands, limitations, and demo workflow.
- Produces: the complete manual Tableau Public workbook specification and concise project entrypoints.

- [ ] **Step 1: Add failing documentation-contract tests**

Add tests named:

- `test_tableau_documentation_names_all_datasets_dashboards_and_commands`
- `test_tableau_documentation_warns_that_published_data_is_public`
- `test_tableau_documentation_forbids_sensitive_network_identifiers`
- `test_readme_has_optional_tableau_section_document_link_and_url_placeholder`
- `test_architecture_places_tableau_after_postgres_export_and_preserves_grafana`
- `test_documentation_labels_demo_data_and_objectives_accurately`

Assert the four dashboard names, four CSV filenames, eight manual Tableau steps, synthetic/demo label, public-data warning, sensitive-field list, and supported limitations are present. Assert the architecture text/diagram contains both Grafana and the PostgreSQL-to-export-to-Tableau path and does not contain a Kafka-to-Tableau edge.

- [ ] **Step 2: Run documentation tests and verify RED**

Run: `python -m pytest tests/test_tableau_deployment.py -k documentation -v`

Expected: FAIL because `docs/tableau-dashboard.md` and README/architecture sections are absent.

- [ ] **Step 3: Write `docs/tableau-dashboard.md`**

Document dataset dictionaries, valid/invalid Tableau relationships, calculated fields using 0-to-100 percentages, the four dashboards, filters, scorecard caveats, deterministic demo workflow, the eight publication steps, privacy inspection, and exact limitations from the spec. State that Tableau Public workbooks and data are public.

- [ ] **Step 4: Update README and architecture documentation**

Add a concise `Tableau BI Dashboard` README section with architecture flow, `make tableau-export` and PowerShell command, documentation link, `Tableau Public workbook: <add URL after publication>`, and optionality statement. Extend the existing architecture diagram downstream of PostgreSQL reporting views while retaining Grafana.

- [ ] **Step 5: Run documentation and deployment tests**

Run: `python -m pytest tests/test_tableau_deployment.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/tableau-dashboard.md README.md docs/architecture.md tests/test_tableau_deployment.py
git commit -m "docs: specify Tableau Public dashboard workflow"
```

### Task 8: Full Verification and Live Demo Export

**Files:**
- Modify only if a verification command reveals a defect; every defect fix must start with a failing regression test in the owning task's test file.

**Interfaces:**
- Consumes: the complete branch.
- Produces: fresh verification evidence and a concise completion report; no new feature behavior.

- [ ] **Step 1: Run targeted Tableau tests**

Run: `python -m pytest services/analytics/tests/test_tableau_config.py services/analytics/tests/test_tableau_repository.py services/analytics/tests/test_tableau_transform.py services/analytics/tests/test_tableau_exporter.py services/analytics/tests/test_tableau_cli.py tests/test_tableau_deployment.py -q`

Expected: all selected tests pass.

- [ ] **Step 2: Run lint and type checking**

Run: `./scripts/netpulse.ps1 lint`

Expected: exit 0.

Run: `./scripts/netpulse.ps1 typecheck`

Expected: exit 0.

- [ ] **Step 3: Run the complete non-integration suite**

Run: `python -m pytest -p no:cacheprovider -m "not integration" --basetemp=".pytest_cache/final" -q`

Expected: all non-integration tests pass; record the exact count and warnings.

- [ ] **Step 4: Validate Compose**

Run: `docker compose -f docker-compose.yml config --quiet`

Expected: exit 0 with no validation errors.

- [ ] **Step 5: Run a deterministic live-stack export when Docker is available**

Run these in order:

```powershell
./scripts/netpulse.ps1 up
./scripts/netpulse.ps1 demo
./scripts/netpulse.ps1 classifier-once
./scripts/netpulse.ps1 analytics-all
./scripts/netpulse.ps1 tableau-export
```

Expected: `tableau_exports` contains exactly four readable CSV files; no CSV header or value contains a forbidden privacy field or a known raw simulator agent ID. If Docker or sufficient resources are unavailable, record the exact skipped commands and environmental limitation rather than claiming integration success.

- [ ] **Step 6: Inspect the final diff and generated-file boundary**

Run: `git status --short && git diff origin/master...HEAD --check && git ls-files tableau_exports`

Expected: no generated CSV is tracked, no whitespace errors, and only intended source/test/documentation changes remain.

- [ ] **Step 7: Request independent whole-branch review**

Provide the reviewer the spec, this plan, `origin/master` base SHA, branch HEAD SHA, and verification results. Resolve every Critical or Important finding with a regression test and rerun the affected plus full feasible checks.

- [ ] **Step 8: Prepare completion report**

Report files added/modified, exact dataset schemas, generation commands, executed test results, limitations, skipped checks, and the remaining manual Tableau Public steps. Do not claim the workbook itself was published.
