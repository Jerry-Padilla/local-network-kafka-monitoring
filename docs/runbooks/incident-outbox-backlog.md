# Incident outbox backlog
## Symptoms
Stored incident publications remain pending for more than five minutes.
## Safety
Do not delete outbox rows; they provide durable at-least-once delivery.
## Diagnosis
Check Kafka health, classifier publication failures, and `netpulse_classifier_pending_publications`.
## Remediation
Restore Kafka connectivity and keep the classifier running so its normal publisher drains the backlog.
## Recovery verification
Confirm the pending gauge returns to zero and incident events appear downstream without lost lifecycle rows.
## Escalation
Escalate if acknowledgements fail while Kafka is healthy.
