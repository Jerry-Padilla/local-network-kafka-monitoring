from datetime import UTC, datetime

from netpulse_simulator.scenarios import ScenarioGenerator

from scripts.seed_airflow_verification import seed_records


class Repository:
    def __init__(self) -> None:
        self.sources: list[object] = []

    def persist_event(self, _event: object, source: object) -> bool:
        self.sources.append(source)
        return True


def test_seed_records_uses_reserved_stable_source_positions() -> None:
    started = datetime(2035, 1, 15, 12, tzinfo=UTC)
    records = ScenarioGenerator(seed=4209).generate_round("healthy", started)
    repository = Repository()

    inserted = seed_records(repository, records, started)  # type: ignore[arg-type]

    assert inserted == len(records)
    assert {source.partition for source in repository.sources} == {99}  # type: ignore[attr-defined]
    offsets = [source.offset for source in repository.sources]  # type: ignore[attr-defined]
    first_offset = int(started.timestamp()) * 100
    assert offsets == list(range(first_offset, first_offset + len(records)))
