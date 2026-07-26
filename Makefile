.PHONY: setup lint format typecheck test test-unit test-integration up down reset logs demo verify kafka-topics db-shell config agent-build agent-validate agent-test

setup lint format typecheck test test-unit test-integration up down reset logs demo verify kafka-topics db-shell config agent-build agent-validate agent-test:
	./scripts/netpulse.sh $@
