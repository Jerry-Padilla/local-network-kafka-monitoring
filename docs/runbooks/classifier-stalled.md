# Classifier stalled
## Symptoms
The enabled classifier has not completed a successful evaluation for more than two minutes.
## Safety
Do not manually edit incident lifecycle rows while the classifier may resume.
## Diagnosis
Inspect classifier logs, PostgreSQL health, evaluation failures, and its last-success metric.
## Remediation
Restore PostgreSQL access or correct the classifier configuration, then restart the classifier service.
## Recovery verification
Confirm evaluation successes advance and expected incident transitions are stored once.
## Escalation
Escalate if evaluation failures persist with a healthy database.
