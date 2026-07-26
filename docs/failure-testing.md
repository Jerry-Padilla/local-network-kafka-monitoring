# Phase 1 failure testing

Use fabricated data and a disposable local stack. Run `reset` first only when
deleting prior local volumes is acceptable.

## Kafka interruption

1. Start the stack and a longer simulator or physical-agent scenario.
2. Run `docker compose stop kafka`.
3. Observe bounded producer delivery failures and ingestor retry logs.
4. Run `docker compose start kafka` and wait for health.
5. Re-run the simulator and `verify`.

The Phase 1 simulator has no durable outbox, so events that it cannot publish
are reported as failures rather than silently discarded. The Raspberry Pi
agent instead retains its already-collected events in SQLite.

## Agent outbox recovery

1. Stop Kafka or point a disposable agent config at an unavailable broker.
2. Run `collect-once` without `--publish`.
3. Run `outbox-status` and record the nonzero pending count.
4. Restore Kafka and run `publish-once`.
5. Confirm pending reaches zero and query PostgreSQL by the emitted event IDs.
6. Confirm stored `event_time` values match the original SQLite payloads.

Do not delete the outbox database to make a recovery test pass. A Kafka
delivery callback, not a successful `produce()` call, is the acknowledgement
boundary.

To test the storage ceiling, use a disposable outbox and a deliberately small
`maximum_bytes`. Verify collection reports `OutboxFullError` and that existing
undelivered rows remain present. Never fill the Pi's root filesystem as a test.

## PostgreSQL interruption

1. Publish a scenario and stop PostgreSQL while the ingestor is active.
2. Confirm the ingestor retries the current source coordinate and does not log
   `record_processed`.
3. After the bounded attempt count, confirm the service exits without committing.
4. Restart PostgreSQL and the ingestor, then verify the record is processed.

## Consumer restart and replay

Stop the ingestor after a source record is received, restart it, and query:

```sql
SELECT event_id, count(*)
FROM raw_events
GROUP BY event_id
HAVING count(*) > 1;
```

The query must return no rows. Validated Kafka output can repeat across the
database/publication boundary; consumers must deduplicate `event_id`.

## Malformed and duplicate records

Run the `malformed-events` and `duplicate-events` simulator scenarios, then
confirm:

- one `raw_events` row per repeated `event_id`;
- a `processing_failures` row with original bytes and validation evidence;
- non-null `dead_letter_published_at`;
- a corresponding record on `network.dead-letter.v1`.

Record exact commands, timestamps, component versions, and observations. Do not
claim a recovery result that was not measured.
