from uuid import UUID

import numpy as np
import pytest
from app.schemas.simulation import SimulationGenerateRequest
from app.services.simulation_service import generate_simulation, load_simulation_by_version


@pytest.mark.parametrize("scenario", ["S1", "S2", "S3", "S4", "S5"])
def test_every_phase_two_scenario_persists_csv_and_truth(tmp_path, scenario: str) -> None:  # type: ignore[no-untyped-def]
    generated = generate_simulation(
        SimulationGenerateRequest(scenario=scenario, num_samples=600, seed=37),
        artifact_root=tmp_path,
    )

    assert (tmp_path / generated.file_path).is_file()
    assert (tmp_path / generated.ground_truth_path).is_file()
    assert generated.num_rows == 600
    assert generated.columns[0] == "timestamp"
    assert generated.columns[-1] == "y"
    assert generated.ground_truth.true_na == 2
    assert len(generated.ground_truth.true_nb) == len(generated.ground_truth.true_delays)


def test_fixed_seed_reproduces_saved_simulation_values(tmp_path) -> None:  # type: ignore[no-untyped-def]
    request = SimulationGenerateRequest(scenario="S2", num_samples=700, noise_level=0.03, seed=101)
    first = generate_simulation(request, artifact_root=tmp_path / "first")
    second = generate_simulation(request, artifact_root=tmp_path / "second")
    first_dataset = load_simulation_by_version(first.version_id, artifact_root=tmp_path / "first")
    second_dataset = load_simulation_by_version(
        second.version_id, artifact_root=tmp_path / "second"
    )

    assert first.ground_truth.model_dump() == second.ground_truth.model_dump()
    assert first_dataset.values.keys() == second_dataset.values.keys()
    for column in first_dataset.values:
        np.testing.assert_allclose(
            first_dataset.values[column],
            second_dataset.values[column],
            equal_nan=True,
        )


def test_s4_records_contamination_and_s5_is_highly_collinear(tmp_path) -> None:  # type: ignore[no-untyped-def]
    contaminated = generate_simulation(
        SimulationGenerateRequest(scenario="S4", num_samples=1_000, seed=7),
        artifact_root=tmp_path / "s4",
    )
    collinear = generate_simulation(
        SimulationGenerateRequest(scenario="S5", num_samples=1_000, seed=7),
        artifact_root=tmp_path / "s5",
    )
    s4 = load_simulation_by_version(contaminated.version_id, artifact_root=tmp_path / "s4")
    s5 = load_simulation_by_version(collinear.version_id, artifact_root=tmp_path / "s5")

    assert contaminated.ground_truth.anomaly_indices["y"]
    assert contaminated.ground_truth.missing_indices["y"]
    assert contaminated.ground_truth.freeze_segments
    assert contaminated.ground_truth.drift_segments
    assert contaminated.ground_truth.irregular_timestamp_indices
    assert contaminated.ground_truth.duplicate_timestamp_indices
    assert np.isnan(s4.values["y"]).any()
    assert collinear.ground_truth.redundant_variables == ["u2"]
    assert "u2" in collinear.ground_truth.variable_dependencies
    assert np.corrcoef(s5.values["u1"], s5.values["u2"])[0, 1] > 0.95


def test_simulation_identifiers_are_uuids(tmp_path) -> None:  # type: ignore[no-untyped-def]
    generated = generate_simulation(
        SimulationGenerateRequest(scenario="S1", num_samples=500, seed=2),
        artifact_root=tmp_path,
    )

    assert UUID(str(generated.dataset_id)).version == 4
    assert UUID(str(generated.version_id)).version == 4
