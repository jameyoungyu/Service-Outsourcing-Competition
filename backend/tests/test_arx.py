import numpy as np
from app.schemas.modeling import ArxFitRequest
from app.schemas.simulation import SimulationGenerateRequest
from app.services.identification_service import fit_arx
from app.services.simulation_service import generate_simulation


def test_noiseless_s1_recovers_known_arx_parameters_within_one_percent(tmp_path) -> None:  # type: ignore[no-untyped-def]
    generated = generate_simulation(
        SimulationGenerateRequest(scenario="S1", num_samples=2_000, noise_level=0.0, seed=11),
        artifact_root=tmp_path,
    )
    result = fit_arx(
        ArxFitRequest(
            dataset_id=generated.dataset_id,
            version_id=generated.version_id,
            input_columns=["u1"],
            output_column="y",
            na=2,
            nb={"u1": 2},
            delays={"u1": 3},
        ),
        artifact_root=tmp_path,
    )

    truth = generated.ground_truth.true_parameters
    errors = [
        abs(result.coefficients[name] - truth[name]) / abs(truth[name])
        for name in ("a1", "a2", "b_u1_0", "b_u1_1")
    ]
    assert max(errors) < 0.01
    assert result.metrics.test_fit is not None and result.metrics.test_fit > 99.99
    assert (tmp_path / result.artifact_uri).is_file()


def test_arx_uses_chronological_splits_and_accepts_frontend_array_parameters(tmp_path) -> None:  # type: ignore[no-untyped-def]
    generated = generate_simulation(
        SimulationGenerateRequest(scenario="S2", num_samples=1_200, noise_level=0.01, seed=23),
        artifact_root=tmp_path,
    )
    result = fit_arx(
        ArxFitRequest(
            dataset_id=generated.dataset_id,
            version_id=generated.version_id,
            na=2,
            nb=[2, 2],
            delays=[3, 8],
            estimation_method="ols",
        ),
        artifact_root=tmp_path,
    )

    splits = result.plot_data.splits
    assert splits.train_end == 720
    assert splits.val_end == 960
    assert splits.test_end == 1_200
    assert result.plot_data.indices == sorted(result.plot_data.indices)
    assert result.plot_data.split_indices == splits
    assert result.metrics.train_fit is not None and result.metrics.train_fit > 90
    assert np.isfinite(result.plot_data.y_pred).all()
