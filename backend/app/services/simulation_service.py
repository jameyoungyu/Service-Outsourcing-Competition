"""Deterministic S1-S5 MISO ARX benchmark generation and local artifact storage."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import numpy as np
from numpy.typing import NDArray

from app.schemas.simulation import (
    GroundTruthSegment,
    SimulationGenerateData,
    SimulationGenerateRequest,
    SimulationGroundTruth,
)

FloatArray = NDArray[np.float64]


class SimulationArtifactNotFoundError(Exception):
    """The requested immutable simulation version is not present in local storage."""


@dataclass(frozen=True)
class SimulationDataset:
    dataset_id: UUID
    version_id: UUID
    dataset_name: str
    scenario: str
    columns: list[str]
    values: dict[str, FloatArray]
    ground_truth: SimulationGroundTruth
    csv_path: Path
    manifest_path: Path


def generate_simulation(
    payload: SimulationGenerateRequest,
    *,
    artifact_root: Path,
    dataset_id: UUID | None = None,
    version_id: UUID | None = None,
) -> SimulationGenerateData:
    """Generate, persist and describe a deterministic S1-S5 benchmark dataset."""

    generator = np.random.default_rng(payload.seed)
    n_samples = _resolved_sample_count(payload)
    input_count = _resolved_input_count(payload)
    noise_level = _resolved_noise_level(payload)
    inputs, dynamic_segments = _scenario_inputs(
        payload.scenario,
        n_samples,
        input_count,
        generator,
    )
    ar_coefficients, input_coefficients, delays = _scenario_parameters(
        payload.scenario, input_count
    )
    output = _simulate_arx(
        inputs,
        ar_coefficients=ar_coefficients,
        input_coefficients=input_coefficients,
        delays=delays,
        noise_level=noise_level,
        generator=generator,
    )
    timestamps = _regular_timestamps(n_samples, payload.sample_period_seconds)
    anomaly_indices: dict[str, list[int]] = {}
    missing_indices: dict[str, list[int]] = {}
    freeze_segments: list[dict[str, int | str]] = []
    drift_segments: list[dict[str, int | str]] = []
    irregular_timestamp_indices: list[int] = []
    duplicate_timestamp_indices: list[int] = []
    redundant_variables: list[str] = []
    variable_dependencies: dict[str, str] = {}

    if payload.scenario == "S4":
        (
            inputs,
            output,
            timestamps,
            anomaly_indices,
            missing_indices,
            freeze_segments,
            drift_segments,
            irregular_timestamp_indices,
            duplicate_timestamp_indices,
        ) = _inject_contamination(
            inputs,
            output,
            timestamps,
            missing_rate=_resolved_missing_rate(payload),
            anomaly_rate=_resolved_anomaly_rate(payload),
            generator=generator,
        )
    if payload.scenario == "S5":
        redundant_variables = ["u2"]
        variable_dependencies = {"u2": "0.97 * u1 + Gaussian(0, 0.025 * std(u1))"}

    truth_segments = [
        GroundTruthSegment(
            start_index=start,
            end_index=end,
            start_idx=start,
            end_idx=end,
            segment_type=segment_type,
            snr_db=_estimate_snr_db(output, noise_level),
        )
        for start, end, segment_type in dynamic_segments
    ]
    parameters = _parameter_map(ar_coefficients, input_coefficients)
    ground_truth = SimulationGroundTruth(
        true_na=len(ar_coefficients),
        true_nb=[len(input_coefficients[column]) for column in sorted(input_coefficients)],
        true_delays=[delays[column] for column in sorted(delays)],
        true_delays_by_input=delays,
        true_parameters=parameters,
        ar_coefficients=ar_coefficients,
        input_coefficients=input_coefficients,
        dynamic_segments=truth_segments,
        anomaly_indices=anomaly_indices,
        missing_indices=missing_indices,
        freeze_segments=freeze_segments,
        drift_segments=drift_segments,
        irregular_timestamp_indices=irregular_timestamp_indices,
        duplicate_timestamp_indices=duplicate_timestamp_indices,
        redundant_variables=redundant_variables,
        variable_dependencies=variable_dependencies,
        noise_level=noise_level,
        seed=payload.seed,
    )
    assigned_dataset_id = dataset_id or uuid4()
    assigned_version_id = version_id or uuid4()
    dataset_name = (
        payload.dataset_name or payload.name or f"{payload.scenario}_simulation_{payload.seed}"
    )
    columns = ["timestamp", *sorted(inputs), "y"]
    storage = _simulation_directory(artifact_root)
    csv_path = storage / f"{assigned_dataset_id}.csv"
    ground_truth_path = storage / f"{assigned_dataset_id}_ground_truth.json"
    manifest_path = storage / f"{assigned_dataset_id}.manifest.json"
    _write_csv(csv_path, timestamps, inputs, output)
    _write_json(ground_truth_path, ground_truth.model_dump(mode="json"))
    manifest = {
        "dataset_id": str(assigned_dataset_id),
        "version_id": str(assigned_version_id),
        "dataset_name": dataset_name,
        "scenario": payload.scenario,
        "columns": columns,
        "created_at": datetime.now(UTC).isoformat(),
        "csv_path": csv_path.name,
        "ground_truth_path": ground_truth_path.name,
    }
    _write_json(manifest_path, manifest)
    return SimulationGenerateData(
        dataset_id=assigned_dataset_id,
        dataset_name=dataset_name,
        version_id=assigned_version_id,
        scenario=payload.scenario,
        file_path=_artifact_uri(csv_path, artifact_root),
        ground_truth_path=_artifact_uri(ground_truth_path, artifact_root),
        num_rows=n_samples,
        num_cols=len(columns),
        columns=columns,
        ground_truth=ground_truth,
    )


def load_simulation_by_version(version_id: UUID, *, artifact_root: Path) -> SimulationDataset:
    """Load the exact persisted input version without consulting ground truth for fitting."""

    storage = _simulation_directory(artifact_root)
    for manifest_path in storage.glob("*.manifest.json"):
        manifest = _read_json(manifest_path)
        if manifest.get("version_id") != str(version_id):
            continue
        csv_path = storage / str(manifest["csv_path"])
        truth_path = storage / str(manifest["ground_truth_path"])
        truth = SimulationGroundTruth.model_validate(_read_json(truth_path))
        columns = manifest.get("columns")
        if not isinstance(columns, list):
            continue
        return SimulationDataset(
            dataset_id=UUID(str(manifest["dataset_id"])),
            version_id=UUID(str(manifest["version_id"])),
            dataset_name=str(manifest["dataset_name"]),
            scenario=str(manifest["scenario"]),
            columns=[str(column) for column in columns],
            values=_read_csv(csv_path),
            ground_truth=truth,
            csv_path=csv_path,
            manifest_path=manifest_path,
        )
    raise SimulationArtifactNotFoundError(str(version_id))


def _resolved_sample_count(payload: SimulationGenerateRequest) -> int:
    return payload.num_samples or payload.n_steps or 1_000


def _resolved_input_count(payload: SimulationGenerateRequest) -> int:
    if payload.scenario == "S1":
        return 1
    if payload.scenario in {"S2", "S3", "S4", "S5"}:
        return min(4, max(2, payload.input_count))
    return payload.input_count


def _resolved_noise_level(payload: SimulationGenerateRequest) -> float:
    if payload.noise_level is not None:
        return payload.noise_level
    if payload.noise_sigma is not None:
        return payload.noise_sigma
    return {"S1": 0.01, "S2": 0.03, "S3": 0.03, "S4": 0.2, "S5": 0.02}[payload.scenario]


def _resolved_missing_rate(payload: SimulationGenerateRequest) -> float:
    return payload.missing_rate if payload.missing_rate > 0 else 0.03


def _resolved_anomaly_rate(payload: SimulationGenerateRequest) -> float:
    return payload.anomaly_rate if payload.anomaly_rate > 0 else 0.01


def _scenario_inputs(
    scenario: str,
    n_samples: int,
    input_count: int,
    generator: np.random.Generator,
) -> tuple[dict[str, FloatArray], list[tuple[int, int, str]]]:
    if scenario == "S3":
        return _long_steady_inputs(n_samples, input_count, generator)
    if scenario == "S5":
        base = _piecewise_input(n_samples, generator, change_every=17)
        inputs = {"u1": base}
        inputs["u2"] = 0.97 * base + generator.normal(0, 0.025 * np.std(base), n_samples)
        for position in range(3, input_count + 1):
            inputs[f"u{position}"] = _piecewise_input(n_samples, generator, change_every=13)
        return inputs, [(0, n_samples - 1, "persistent_excitation")]
    return (
        {
            f"u{position}": _piecewise_input(
                n_samples,
                generator,
                change_every=11 + position * 4,
            )
            for position in range(1, input_count + 1)
        },
        [(0, n_samples - 1, "persistent_excitation")],
    )


def _piecewise_input(
    n_samples: int,
    generator: np.random.Generator,
    *,
    change_every: int,
) -> FloatArray:
    values = np.empty(n_samples, dtype=float)
    level = 0.0
    for start in range(0, n_samples, change_every):
        level = float(generator.uniform(-1.5, 1.5))
        values[start : start + change_every] = level
    return values


def _long_steady_inputs(
    n_samples: int,
    input_count: int,
    generator: np.random.Generator,
) -> tuple[dict[str, FloatArray], list[tuple[int, int, str]]]:
    inputs = {
        f"u{position}": np.zeros(n_samples, dtype=float) for position in range(1, input_count + 1)
    }
    budget = max(30, int(n_samples * 0.2))
    widths = [max(10, budget // 3)] * 3
    positions = [int(n_samples * fraction) for fraction in (0.2, 0.5, 0.78)]
    segment_types = ["step", "ramp", "pulse"]
    segments: list[tuple[int, int, str]] = []
    for position, width, segment_type in zip(positions, widths, segment_types, strict=True):
        end = min(n_samples, position + width)
        segments.append((position, end - 1, segment_type))
        amplitude = float(generator.uniform(0.8, 1.6))
        if segment_type == "step":
            inputs["u1"][position:end] = amplitude
        elif segment_type == "ramp":
            inputs["u1"][position:end] = np.linspace(0, amplitude, end - position)
        else:
            inputs["u1"][position:end] = amplitude
            middle = position + (end - position) // 2
            inputs["u1"][middle:end] = 0
        for input_index in range(2, input_count + 1):
            input_amplitude = float(generator.uniform(-1.4, 1.4))
            signal = inputs[f"u{input_index}"]
            if segment_type == "step":
                signal[position:end] = input_amplitude
            elif segment_type == "ramp":
                signal[position:end] = np.linspace(0, input_amplitude, end - position)
            else:
                signal[position:end] = input_amplitude
                middle = position + (end - position) // 2
                signal[middle:end] = 0
    return inputs, segments


def _scenario_parameters(
    scenario: str,
    input_count: int,
) -> tuple[list[float], dict[str, list[float]], dict[str, int]]:
    ar_coefficients = [-1.4, 0.48]
    default_delays = [3, 8, 5, 11]
    input_coefficients: dict[str, list[float]] = {}
    delays: dict[str, int] = {}
    for position in range(1, input_count + 1):
        input_coefficients[f"u{position}"] = [round(0.36 / position, 4), round(0.12 / position, 4)]
        delays[f"u{position}"] = default_delays[position - 1]
    if scenario == "S5" and "u2" in input_coefficients:
        input_coefficients["u2"] = [0.08, 0.025]
    return ar_coefficients, input_coefficients, delays


def _simulate_arx(
    inputs: dict[str, FloatArray],
    *,
    ar_coefficients: list[float],
    input_coefficients: dict[str, list[float]],
    delays: dict[str, int],
    noise_level: float,
    generator: np.random.Generator,
) -> FloatArray:
    n_samples = len(next(iter(inputs.values())))
    output = np.zeros(n_samples, dtype=float)
    max_history = max(
        len(ar_coefficients),
        max(delays[column] + len(input_coefficients[column]) - 1 for column in inputs),
    )
    for time_index in range(max_history, n_samples):
        value = 0.0
        for lag, coefficient in enumerate(ar_coefficients, start=1):
            value -= coefficient * output[time_index - lag]
        for column, signal in inputs.items():
            for lag, coefficient in enumerate(input_coefficients[column]):
                value += coefficient * signal[time_index - delays[column] - lag]
        output[time_index] = value + generator.normal(0, noise_level)
    return output


def _regular_timestamps(n_samples: int, sample_period_seconds: float) -> list[datetime]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [start + timedelta(seconds=sample_period_seconds * index) for index in range(n_samples)]


def _inject_contamination(
    inputs: dict[str, FloatArray],
    output: FloatArray,
    timestamps: list[datetime],
    *,
    missing_rate: float,
    anomaly_rate: float,
    generator: np.random.Generator,
) -> tuple[
    dict[str, FloatArray],
    FloatArray,
    list[datetime],
    dict[str, list[int]],
    dict[str, list[int]],
    list[dict[str, int | str]],
    list[dict[str, int | str]],
    list[int],
    list[int],
]:
    contaminated_inputs = {column: values.copy() for column, values in inputs.items()}
    contaminated_output = output.copy()
    n_samples = len(output)
    anomaly_count = max(1, int(n_samples * anomaly_rate))
    missing_count = max(1, int(n_samples * missing_rate))
    anomaly_positions = np.sort(
        generator.choice(np.arange(20, n_samples), size=anomaly_count, replace=False)
    )
    missing_positions = np.sort(
        generator.choice(np.arange(20, n_samples), size=missing_count, replace=False)
    )
    amplitude = max(float(np.nanstd(output)) * 7, 1.0)
    contaminated_output[anomaly_positions] += (
        generator.choice((-1.0, 1.0), size=anomaly_count) * amplitude
    )
    contaminated_output[missing_positions] = np.nan
    missing_indices: dict[str, list[int]] = {"y": [int(value) for value in missing_positions]}
    anomaly_indices = {"y": [int(value) for value in anomaly_positions]}
    if contaminated_inputs:
        first_input = sorted(contaminated_inputs)[0]
        input_missing = np.sort(
            generator.choice(np.arange(20, n_samples), size=missing_count, replace=False)
        )
        contaminated_inputs[first_input][input_missing] = np.nan
        missing_indices[first_input] = [int(value) for value in input_missing]
        freeze_start = int(n_samples * 0.45)
        freeze_end = min(n_samples - 1, freeze_start + max(10, n_samples // 15))
        freeze_value = contaminated_inputs[first_input][freeze_start]
        contaminated_inputs[first_input][freeze_start : freeze_end + 1] = freeze_value
        freeze_segments: list[dict[str, int | str]] = [
            {"column": first_input, "start_idx": freeze_start, "end_idx": freeze_end}
        ]
    else:
        freeze_segments = []
    drift_start = int(n_samples * 0.72)
    contaminated_output[drift_start:] += np.linspace(0, amplitude * 0.8, n_samples - drift_start)
    drift_segments: list[dict[str, int | str]] = [
        {"column": "y", "start_idx": drift_start, "end_idx": n_samples - 1}
    ]
    irregular_timestamps = list(timestamps)
    irregular_indices = list(range(max(1, n_samples // 20), n_samples, max(1, n_samples // 20)))
    for index in irregular_indices:
        irregular_timestamps[index] = irregular_timestamps[index] + timedelta(milliseconds=350)
    duplicate_positions = np.sort(
        generator.choice(np.arange(1, n_samples), size=max(1, n_samples // 100), replace=False)
    )
    for index in duplicate_positions:
        irregular_timestamps[int(index)] = irregular_timestamps[int(index) - 1]
    return (
        contaminated_inputs,
        contaminated_output,
        irregular_timestamps,
        anomaly_indices,
        missing_indices,
        freeze_segments,
        drift_segments,
        irregular_indices,
        [int(index) for index in duplicate_positions],
    )


def _estimate_snr_db(output: FloatArray, noise_level: float) -> float | None:
    if noise_level <= 0:
        return None
    signal_standard_deviation = float(np.std(output))
    return round(float(20 * np.log10(max(signal_standard_deviation, 1e-12) / noise_level)), 3)


def _parameter_map(
    ar_coefficients: list[float], input_coefficients: dict[str, list[float]]
) -> dict[str, float]:
    parameters = {f"a{index}": value for index, value in enumerate(ar_coefficients, start=1)}
    for column, coefficients in input_coefficients.items():
        for lag, coefficient in enumerate(coefficients):
            parameters[f"b_{column}_{lag}"] = coefficient
    return parameters


def _simulation_directory(artifact_root: Path) -> Path:
    storage = artifact_root / "simulation"
    storage.mkdir(parents=True, exist_ok=True)
    return storage


def _artifact_uri(path: Path, artifact_root: Path) -> str:
    return path.relative_to(artifact_root).as_posix()


def _write_csv(
    path: Path,
    timestamps: list[datetime],
    inputs: dict[str, FloatArray],
    output: FloatArray,
) -> None:
    fieldnames = ["timestamp", *sorted(inputs), "y"]
    temporary_path = path.with_suffix(".csv.tmp")
    with temporary_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for index, timestamp in enumerate(timestamps):
            row: dict[str, str] = {"timestamp": timestamp.isoformat()}
            for column, values in inputs.items():
                row[column] = _csv_number(values[index])
            row["y"] = _csv_number(output[index])
            writer.writerow(row)
    temporary_path.replace(path)


def _csv_number(value: float) -> str:
    return "" if not np.isfinite(value) else format(float(value), ".12g")


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _read_json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _read_csv(path: Path) -> dict[str, FloatArray]:
    with path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        return {}
    columns = [column for column in rows[0] if column != "timestamp"]
    values: dict[str, FloatArray] = {}
    for column in columns:
        values[column] = np.asarray(
            [float(row[column]) if row[column] not in {None, ""} else np.nan for row in rows],
            dtype=float,
        )
    return values
