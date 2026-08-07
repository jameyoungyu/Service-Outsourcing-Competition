"""Tests for identifiability-driven selection and control-relevant validation."""

from __future__ import annotations

import numpy as np
import pytest
from algorithms.identifiability import (
    ArxStructure,
    build_regressor,
    build_window_grid,
    fisher_information,
    free_run_simulate,
    log_det_information,
    persistent_excitation_order,
    profile_excitation,
    select_informative_windows,
    steady_state_gains,
    validate_model,
)
from algorithms.identifiability.excitation import marginal_log_det_gain
from algorithms.identifiability.regressor import IdentifiabilityError
from algorithms.identifiability.selection import select_by_energy
from algorithms.identifiability.validation import is_stable, unpack_parameters

AR = [-1.2, 0.35]
B = {"u1": [0.4, 0.15], "u2": [0.25, 0.1]}
NK = {"u1": 2, "u2": 5}


def make_structure() -> ArxStructure:
    return ArxStructure.create(
        na=len(AR),
        nb={column: len(values) for column, values in B.items()},
        nk=NK,
        input_columns=tuple(B),
    )


def true_theta() -> np.ndarray:
    return np.concatenate([np.asarray(AR, dtype=float)] + [np.asarray(B[c]) for c in B])


def simulate(
    inputs: dict[str, np.ndarray],
    *,
    noise: float = 0.0,
    seed: int = 7,
) -> np.ndarray:
    generator = np.random.default_rng(seed)
    n_samples = len(next(iter(inputs.values())))
    output = np.zeros(n_samples, dtype=float)
    history = max(len(AR), max(NK[c] + len(B[c]) - 1 for c in inputs))
    for index in range(history, n_samples):
        value = -sum(AR[lag - 1] * output[index - lag] for lag in range(1, len(AR) + 1))
        for column, signal in inputs.items():
            for lag, coefficient in enumerate(B[column]):
                value += coefficient * signal[index - NK[column] - lag]
        output[index] = value + (generator.normal(0.0, noise) if noise else 0.0)
    return output


def random_inputs(n_samples: int, *, seed: int = 3) -> dict[str, np.ndarray]:
    generator = np.random.default_rng(seed)
    signals = {}
    for offset, column in enumerate(B):
        values = np.empty(n_samples, dtype=float)
        block = 13 + offset * 5
        for start in range(0, n_samples, block):
            values[start : start + block] = generator.uniform(-1.5, 1.5)
        signals[column] = values
    return signals


class TestRegressor:
    def test_recovers_parameters_without_noise(self) -> None:
        structure = make_structure()
        inputs = random_inputs(800)
        output = simulate(inputs)
        regressor = build_regressor(inputs=inputs, output=output, structure=structure)
        estimate, _, _, _ = np.linalg.lstsq(regressor.features, regressor.targets, rcond=None)
        assert np.allclose(estimate, true_theta(), atol=1e-8)

    def test_row_layout_matches_declared_feature_names(self) -> None:
        structure = make_structure()
        assert structure.feature_names() == ["a1", "a2", "b_u1_0", "b_u1_1", "b_u2_0", "b_u2_1"]
        assert structure.parameter_count == 6
        assert structure.max_history == max(NK["u2"] + len(B["u2"]) - 1, len(AR))

    def test_drops_non_finite_rows_instead_of_imputing(self) -> None:
        structure = make_structure()
        inputs = random_inputs(400)
        output = simulate(inputs)
        output[200] = np.nan
        regressor = build_regressor(inputs=inputs, output=output, structure=structure)
        assert np.all(np.isfinite(regressor.features))
        assert 200 not in regressor.time_indices.tolist()

    def test_rejects_length_mismatch(self) -> None:
        structure = make_structure()
        inputs = random_inputs(300)
        inputs["u2"] = inputs["u2"][:-5]
        with pytest.raises(IdentifiabilityError) as error:
            build_regressor(inputs=inputs, output=simulate(random_inputs(300)), structure=structure)
        assert error.value.code == "INVALID_DATASET_SCHEMA"

    def test_rejects_interval_shorter_than_history(self) -> None:
        structure = make_structure()
        inputs = random_inputs(300)
        with pytest.raises(IdentifiabilityError) as error:
            build_regressor(
                inputs=inputs,
                output=simulate(inputs),
                structure=structure,
                start=0,
                stop=3,
            )
        assert error.value.code == "INSUFFICIENT_ROWS"


class TestExcitation:
    def test_constant_signal_is_pe_order_one_at_most(self) -> None:
        assert persistent_excitation_order(np.full(500, 2.0), max_order=6) <= 1

    def test_zero_signal_has_no_excitation(self) -> None:
        assert persistent_excitation_order(np.zeros(500), max_order=6) == 0

    def test_white_noise_is_persistently_exciting_of_high_order(self) -> None:
        generator = np.random.default_rng(11)
        order = persistent_excitation_order(generator.normal(size=4000), max_order=8)
        assert order == 8

    def test_step_count_sets_the_excitation_order(self) -> None:
        """Textbook result: m distinct level changes excite exactly m parameter directions."""

        one_step = np.zeros(2000)
        one_step[1000:] = 1.0
        assert persistent_excitation_order(one_step, max_order=8) == 1

        two_steps = np.zeros(2000)
        two_steps[500:1000] = 1.0
        two_steps[1400:1700] = -0.7
        assert persistent_excitation_order(two_steps, max_order=8) == 2

    def test_excitation_order_is_monotone_in_the_tolerance(self) -> None:
        signal = np.zeros(2000)
        signal[1000:] = 1.0
        orders = [
            persistent_excitation_order(signal, max_order=8, tolerance=tolerance)
            for tolerance in (1e-6, 1e-4, 1e-3, 1e-2)
        ]
        assert orders == sorted(orders, reverse=True)

    def test_log_det_is_negative_infinity_for_singular_information(self) -> None:
        assert log_det_information(np.zeros((3, 3))) == float("-inf")

    def test_ridge_makes_empty_information_well_defined(self) -> None:
        information = fisher_information(np.zeros((0, 4)), ridge=1e-3)
        assert information.shape == (4, 4)
        assert np.isfinite(log_det_information(information))

    def test_marginal_gain_matches_direct_log_det_difference(self) -> None:
        generator = np.random.default_rng(5)
        block = generator.normal(size=(40, 6))
        root = generator.normal(size=(6, 6))
        base = np.eye(6) * 0.5 + root @ root.T
        factor = np.linalg.cholesky(base)
        addition = block.T @ block
        expected = log_det_information(base + addition) - log_det_information(base)
        assert marginal_log_det_gain(factor, addition) == pytest.approx(expected, rel=1e-9)

    def test_profile_flags_rank_deficiency(self) -> None:
        structure = make_structure()
        inputs = random_inputs(600)
        inputs["u2"] = np.zeros(600)
        output = simulate(inputs)
        regressor = build_regressor(inputs=inputs, output=output, structure=structure)
        report = profile_excitation(regressor, inputs=inputs, ridge=0.0)
        assert report.rank_deficient
        assert not report.excitation_satisfied


class TestSelection:
    def test_greedy_prefers_dynamic_windows_over_steady_ones(self) -> None:
        structure = make_structure()
        n_samples = 3000
        inputs = {column: np.zeros(n_samples) for column in B}
        generator = np.random.default_rng(19)
        for start in (300, 900, 1500, 2100):
            for column in B:
                inputs[column][start : start + 120] = generator.uniform(-1.5, 1.5, 120)
        output = simulate(inputs, noise=0.01)
        regressor = build_regressor(inputs=inputs, output=output, structure=structure)
        grid = build_window_grid(regressor, window_size=60, stride=30)
        result = select_informative_windows(regressor, grid, budget_windows=6, ridge=1e-6)

        dynamic = [(300, 420), (900, 1020), (1500, 1620), (2100, 2220)]
        for window in result.selected:
            centre = (window.start_index + window.end_index) / 2
            assert any(low <= centre <= high for low, high in dynamic), (
                f"selected steady window {window.start_index}-{window.end_index}"
            )

    def test_information_gain_is_non_increasing(self) -> None:
        structure = make_structure()
        inputs = random_inputs(2000)
        output = simulate(inputs, noise=0.02)
        regressor = build_regressor(inputs=inputs, output=output, structure=structure)
        grid = build_window_grid(regressor, window_size=50, stride=25)
        result = select_informative_windows(regressor, grid, budget_windows=8, ridge=1e-6)
        gains = [window.information_gain_nats for window in result.selected]
        assert gains == sorted(gains, reverse=True), "submodularity implies diminishing returns"

    def test_lazy_greedy_matches_exhaustive_greedy(self) -> None:
        structure = make_structure()
        inputs = random_inputs(1500, seed=23)
        output = simulate(inputs, noise=0.02)
        regressor = build_regressor(inputs=inputs, output=output, structure=structure)
        grid = build_window_grid(regressor, window_size=40, stride=40)
        result = select_informative_windows(regressor, grid, budget_windows=5, ridge=1e-6)

        # Reference implementation: recompute every candidate at every step.
        information = 1e-6 * np.eye(regressor.n_parameters)
        chosen: list[int] = []
        for _ in range(5):
            best, best_gain = -1, float("-inf")
            for index, positions in enumerate(grid.positions):
                if index in chosen:
                    continue
                block = regressor.features[positions]
                gain = log_det_information(information + block.T @ block) - log_det_information(
                    information
                )
                if gain > best_gain:
                    best, best_gain = index, gain
            chosen.append(best)
            block = regressor.features[grid.positions[best]]
            information = information + block.T @ block

        assert [window.window_index for window in result.selected] == chosen
        assert result.lazy_speedup > 1.0

    def test_grid_respects_row_range_so_validation_stays_unseen(self) -> None:
        structure = make_structure()
        inputs = random_inputs(1200)
        output = simulate(inputs, noise=0.01)
        regressor = build_regressor(inputs=inputs, output=output, structure=structure)
        grid = build_window_grid(regressor, window_size=50, stride=50, row_range=(0, 400))
        assert all(int(positions[-1]) < 400 for positions in grid.positions)

    def test_row_budget_limits_selection(self) -> None:
        structure = make_structure()
        inputs = random_inputs(2000)
        output = simulate(inputs, noise=0.02)
        regressor = build_regressor(inputs=inputs, output=output, structure=structure)
        grid = build_window_grid(regressor, window_size=50, stride=50)
        result = select_informative_windows(regressor, grid, budget_rows=220, ridge=1e-6)
        assert result.row_positions.size <= 220

    def test_requires_exactly_one_budget(self) -> None:
        structure = make_structure()
        inputs = random_inputs(800)
        regressor = build_regressor(inputs=inputs, output=simulate(inputs), structure=structure)
        grid = build_window_grid(regressor, window_size=50)
        with pytest.raises(IdentifiabilityError) as error:
            select_informative_windows(regressor, grid)
        assert error.value.code == "PARAMETER_OUT_OF_RANGE"

    def test_beats_energy_heuristic_under_heterogeneous_excitation(self) -> None:
        """Energy ranks by magnitude, so it repeats u1 and never learns u2."""

        structure = make_structure()
        n_samples = 4000
        inputs = {column: np.zeros(n_samples) for column in B}
        for start in (200, 700, 1200, 1700, 2200):
            inputs["u1"][start : start + 150] = 1.6
        for start in (2700, 3200):
            inputs["u2"][start : start + 150] = 0.5
        output = simulate(inputs, noise=0.01)
        regressor = build_regressor(inputs=inputs, output=output, structure=structure)
        grid = build_window_grid(regressor, window_size=80, stride=40)

        ids = select_informative_windows(regressor, grid, budget_windows=6, ridge=1e-6)
        energy_rows = select_by_energy(regressor, grid, budget_windows=6)
        energy_subset = regressor.take(energy_rows)

        truth = true_theta()
        ids_theta, _, _, _ = np.linalg.lstsq(
            ids.regressor.features, ids.regressor.targets, rcond=None
        )
        energy_theta, _, _, _ = np.linalg.lstsq(
            energy_subset.features, energy_subset.targets, rcond=None
        )
        ids_error = np.linalg.norm(ids_theta - truth) / np.linalg.norm(truth)
        energy_error = np.linalg.norm(energy_theta - truth) / np.linalg.norm(truth)
        assert ids_error < energy_error


class TestValidation:
    def test_free_run_reproduces_a_noise_free_system_exactly(self) -> None:
        structure = make_structure()
        inputs = random_inputs(900)
        output = simulate(inputs)
        measured, simulated = free_run_simulate(
            true_theta(), structure, inputs=inputs, output=output, start=0, stop=900
        )
        assert np.allclose(measured, simulated, atol=1e-6)

    def test_one_step_fit_hides_a_model_that_free_run_exposes(self) -> None:
        structure = make_structure()
        inputs = random_inputs(2500)
        output = simulate(inputs, noise=0.05, seed=31)
        theta = true_theta().copy()
        theta[2:] *= 0.55  # halve every input gain; the output dynamics still dominate
        report = validate_model(theta, structure, inputs=inputs, output=output, start=0, stop=2500)
        assert report.one_step_fit > report.free_run_fit
        assert report.fit_gap > 10.0

    def test_steady_state_gain_matches_analytic_value(self) -> None:
        structure = make_structure()
        gains = steady_state_gains(true_theta(), structure)
        denominator = 1.0 + sum(AR)
        for column, coefficients in B.items():
            assert gains[column] == pytest.approx(sum(coefficients) / denominator)

    def test_detects_an_unstable_polynomial(self) -> None:
        stable, modulus = is_stable(np.asarray(AR, dtype=float))
        assert stable and modulus < 1.0
        unstable, modulus = is_stable(np.asarray([-2.5, 1.4], dtype=float))
        assert not unstable and modulus > 1.0

    def test_whiteness_is_high_for_a_correct_model(self) -> None:
        structure = make_structure()
        inputs = random_inputs(3000, seed=41)
        output = simulate(inputs, noise=0.03, seed=43)
        report = validate_model(
            true_theta(), structure, inputs=inputs, output=output, start=0, stop=3000
        )
        assert report.residual_whiteness_ratio > 0.8
        assert report.stable

    def test_unpack_rejects_wrong_length(self) -> None:
        structure = make_structure()
        with pytest.raises(IdentifiabilityError) as error:
            unpack_parameters(np.zeros(3), structure)
        assert error.value.code == "INVALID_DATASET_SCHEMA"
