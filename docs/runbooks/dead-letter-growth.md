# Dead-letter growth
## Symptoms
`NetPulseDeadLetterGrowth` detects one or more rejected records in ten minutes.
## Safety
Treat payloads as potentially sensitive; avoid copying raw identifiers into tickets or chat.
## Diagnosis
Inspect bounded ingestion error logs and compare the producer version with the current event contract.
## Remediation
Correct the producer schema or configuration. Replay only validated source records through the normal topic.
## Recovery verification
Confirm the dead-letter counter stops increasing and corrected records produce valid downstream events.
## Escalation
Escalate for contract incompatibility affecting multiple producers or sustained rejection volume.
