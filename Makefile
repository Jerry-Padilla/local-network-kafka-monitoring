.PHONY: setup lint format typecheck test test-unit test-integration up down reset logs demo verify kafka-topics db-shell config agent-build agent-validate agent-test stream-build stream-run stream-once stream-verify classifier-build classifier-run classifier-once classifier-verify analytics-build analytics-all analytics-verify api-build api-up api-integration api-provisioning-test api-verify api-down monitoring-render monitoring-up monitoring-verify monitoring-down failure-drill

setup lint format typecheck test test-unit test-integration up down reset logs demo verify kafka-topics db-shell config agent-build agent-validate agent-test stream-build stream-run stream-once stream-verify classifier-build classifier-run classifier-once classifier-verify analytics-build analytics-all analytics-verify api-build api-up api-integration api-provisioning-test api-verify api-down:
	./scripts/netpulse.sh $@

monitoring-render:
	./scripts/netpulse.sh $@ "$(PI_TARGET)"

monitoring-up monitoring-verify monitoring-down failure-drill:
	./scripts/netpulse.sh $@
