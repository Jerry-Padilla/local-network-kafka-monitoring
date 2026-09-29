# Pipeline stale or ingestion failures
## Symptoms
Active traffic is not completing within 60 seconds, or ingestion failures are increasing.
## Safety
Do not skip events, alter offsets, or truncate operational tables.
## Diagnosis
Compare ingestion freshness, throughput, Kafka lag, and PostgreSQL health; inspect event-ingestor logs for retry causes.
## Remediation
Restore the failed dependency or configuration and allow the at-least-once consumer to replay normally.
## Recovery verification
Confirm last-success freshness falls below 60 seconds, lag drains, and event-ID deduplication remains effective.
## Escalation
Escalate if valid events remain blocked after dependencies recover.
