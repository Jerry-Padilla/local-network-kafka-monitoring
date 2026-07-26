.PHONY: setup lint format typecheck test test-unit test-integration up down reset logs demo verify kafka-topics db-shell config agent-build agent-validate agent-test stream-build stream-run stream-once stream-verify

setup lint format typecheck test test-unit test-integration up down reset logs demo verify kafka-topics db-shell config agent-build agent-validate agent-test stream-build stream-run stream-once stream-verify:
	./scripts/netpulse.sh $@
