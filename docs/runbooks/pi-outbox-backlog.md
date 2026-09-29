# Raspberry Pi outbox backlog
## Symptoms
The Pi SQLite outbox remains non-empty for more than five minutes.
## Safety
Do not delete or replace the SQLite outbox; it protects measurements during Kafka outages.
## Diagnosis
Check Kafka reachability from the Pi, agent logs, outbox depth, and oldest-pending age.
## Remediation
Restore the permitted Kafka listener and LAN route, then let the agent publisher drain records.
## Recovery verification
Confirm depth reaches zero, publication success advances, and queued event IDs appear once in PostgreSQL.
## Escalation
Escalate if the queue grows near its configured bound or cannot drain after connectivity returns.
