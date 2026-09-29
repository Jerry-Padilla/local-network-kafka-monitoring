# Raspberry Pi collector stale
## Symptoms
The configured Pi target is unreachable or has not collected successfully for more than two minutes.
## Safety
Keep the Pi wired; preserve `/var/lib/netpulse/outbox.db` and the device-specific privacy salt.
## Diagnosis
Check Ethernet and power, `systemctl status netpulse-agent`, `journalctl -u netpulse-agent`, and reachability of port 9102 from the host.
## Remediation
Restore the wired link or configuration and restart `netpulse-agent` only after confirming its backend endpoint.
## Recovery verification
Confirm the Prometheus Pi target is up, collection freshness advances, and new Pi events reach PostgreSQL.
## Escalation
Escalate on repeated power, storage, or network-interface failures.
