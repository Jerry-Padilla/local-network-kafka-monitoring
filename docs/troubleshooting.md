# Troubleshooting

## Docker command is missing

Install Docker Desktop/Engine and restart the terminal. Confirm `docker version`
and `docker compose version` before running NetPulse scripts.

## Docker Desktop reports that virtualization is unavailable

Open Windows Task Manager, select **Performance > CPU**, and check that
**Virtualization** says **Enabled**. If it is disabled, enable Intel VT-x/VT-d
or AMD-V/SVM in UEFI/BIOS, then reboot. Docker Desktop's WSL 2 backend also
requires the Windows **Virtual Machine Platform** and **Windows Subsystem for
Linux** features. Hyper-V is additionally required when using the Hyper-V
backend. On an organization-managed machine, firmware and Windows-feature
changes may require an administrator.

If virtualization is enabled but Docker still reports the error, fully restart
Windows rather than only restarting Docker Desktop, then recheck `docker info`.

## Image pulls repeatedly end with an EOF error

First retry after restarting Docker Desktop and confirm the machine has stable
access to Docker Hub and its CDN. A Docker Desktop image-store problem can
sometimes be isolated by disabling **Use containerd for pulling and storing
images** in Docker Desktop settings and restarting Docker. Back up Docker
Desktop settings before changing them. This changes local image storage and
should be treated as a workstation workaround, not a NetPulse requirement.

## Kafka stays unhealthy

Inspect `docker compose logs kafka`. Confirm port 29092 is unused and that the
Kafka volume is writable. A cluster-ID or storage-format mismatch in disposable
demo data can be cleared with `reset`.

## Migration fails because a role is missing

The application role is created only when PostgreSQL initializes an empty data
volume. If an old volume predates the initialization script, back up needed
data, run `reset`, and start again.

## Ingestor repeatedly stops on one offset

Read the structured `record_processing_failed` log. Dependency failures are
retried a bounded number of times, after which the service exits without
committing. Repair PostgreSQL/Kafka or the configuration and restart. Contract
failures should instead appear in `processing_failures` and the DLQ.

## Simulator cannot publish

Check the bootstrap address. Host commands use `localhost:29092`; Compose
services use `kafka:9092`. Producer delivery timeout is intentional and prevents
silent loss.

## PowerShell blocks script execution

Use an appropriately scoped PowerShell execution policy approved by your
organization, or run the equivalent explicit Docker Compose commands documented
in the scripts. Do not weaken machine-wide policy solely for this project.
