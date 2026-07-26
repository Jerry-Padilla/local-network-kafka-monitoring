.PHONY: setup lint format typecheck test test-unit test-integration up down reset logs demo verify kafka-topics db-shell config

setup lint format typecheck test test-unit test-integration up down reset logs demo verify kafka-topics db-shell config:
	./scripts/netpulse.sh $@
