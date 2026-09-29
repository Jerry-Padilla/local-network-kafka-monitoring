# Kafka consumer lag
## Symptoms
`NetPulseKafkaConsumerLag` fires when the ingestion consumer remains more than 100 records behind.
## Safety
Do not delete topics or change consumer-group offsets during diagnosis.
## Diagnosis
Check the Consumer Lag dashboard, `docker compose ps kafka event-ingestor`, and both services' recent logs.
## Remediation
Restore the event ingestor or its PostgreSQL dependency; let the existing consumer group drain naturally.
## Recovery verification
Confirm `netpulse:kafka_consumer_lag` trends to zero and fresh events appear in PostgreSQL.
## Escalation
Escalate if lag grows with healthy dependencies or processing exhausts retries.
