import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest


def _load_split_imports():
    for parent in Path(__file__).resolve().parents:
        helper_path = parent / "_support" / "_split_imports.py"
        if helper_path.exists():
            spec = importlib.util.spec_from_file_location(
                "_split_imports_for_nondim_thermal_field_case",
                helper_path,
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise ImportError("Could not locate tests/_support/_split_imports.py")


split_imports = _load_split_imports()


@pytest.fixture(scope="module")
def case():
    try:
        return split_imports.import_validation_run_module(
            "nondim_thermal_field_case"
        )
    except ModuleNotFoundError as exc:
        pytest.skip(
            "external VALIDATION snapshot still imports the removed ALB 0.1 namespace"
        )


def test_validation_import_ignores_param_scan_run_first_on_sys_path(case):
    workspace_root = split_imports.find_split_workspace_root(Path(__file__))
    param_scan_root = str(workspace_root / "PARAM_SCAN")
    original_path = list(sys.path)
    try:
        sys.path.insert(0, param_scan_root)
        imported = split_imports.import_validation_run_module(
            "nondim_thermal_field_case"
        )
    finally:
        sys.path[:] = original_path

    assert Path(imported.__file__).resolve().is_relative_to(
        (workspace_root / "VALIDATION" / "run").resolve()
    )


def test_nondim_thermal_field_case_uses_thermal_config_input(case):
    result = case.solve_nondim_thermal_field_case(
        {
            "args_nodim": True,
            "delta_t_scale": 25.0,
            "heat_partition": 0.8,
            "supg": True,
        }
    )

    assert result["thermal_config"].args_nodim is True
    assert result["thermal_config"].delta_t_scale == 25.0
    assert "thermal_config_readonly" in result
    assert "temperature_nondim" in result
    assert "temperature_nondim_field" in result
    assert "pressure_nondim_field" in result
    assert "beta_nondim" in result
    assert "viscosity_ratio_field" in result
    assert "temperature_film_nondim" in result
    assert (
        result["temperature_nondim_field"].shape
        == result["pressure_nondim_field"].shape
    )
    np.testing.assert_allclose(
        result["thermal_config_readonly"]["beta_nondim"], 0.03 * 25.0
    )
    np.testing.assert_allclose(
        result["beta_nondim"], result["thermal_config_readonly"]["beta_nondim"]
    )
    assert np.all(np.isfinite(result["temperature_nondim"]))
    assert np.all(np.isfinite(result["temperature_nondim_field"]))
    assert np.all(np.isfinite(result["temperature_film_nondim"]))
    assert np.all(np.isfinite(result["pressure_nondim_field"]))
    assert np.all(np.isfinite(result["viscosity_ratio_field"]))
    np.testing.assert_allclose(
        result["viscosity_ratio_field"],
        result["viscosity_field_grid"] / result["thermal_config_readonly"]["miu0"],
    )


def test_nondim_pressure_field_matches_dimensional_scaling(case):
    result = case.solve_nondim_thermal_field_case({"delta_t_scale": 30.0})

    np.testing.assert_allclose(
        result["pressure_field"],
        result["pressure_nondim_field"] * result["ps"],
        rtol=1e-12,
        atol=1e-12,
    )


def test_zero_heat_partition_gives_zero_nondim_temperature_rise(case):
    result = case.solve_nondim_thermal_field_case({"heat_partition": 0.0})

    np.testing.assert_allclose(result["temperature_nondim"], 0.0, atol=1e-8)
    np.testing.assert_allclose(result["t_eff_nondim"], 0.0, atol=1e-8)


def test_dimensional_and_nondim_parameter_sets_match_viscosity_field_evolution(case):
    dimensional_thermal = {
        "delta_t_scale": 25.0,
        "heat_partition": 0.8,
        "beta": 0.03,
        "t_in": 40.0,
        "t_supply": 40.0,
        "t_ref": 45.0,
        "args_nodim": True,
    }
    nondim_thermal = {
        "delta_t_scale": 25.0,
        "heat_partition": 0.8,
        "beta_nondim": 0.03 * 25.0,
        "t_in": 40.0,
        "t_supply": 40.0,
        "t_ref_nondim": (45.0 - 40.0) / 25.0,
        "args_nodim": True,
    }

    dimensional_result = case.solve_nondim_thermal_field_case(
        dimensional_thermal,
        input_nodim=True,
        config_input_nondim=False,
    )
    nondim_result = case.solve_nondim_thermal_field_case(
        nondim_thermal,
        input_nodim=True,
        config_input_nondim=True,
    )

    np.testing.assert_allclose(
        dimensional_result["thermal_config_readonly"]["beta_nondim"],
        nondim_result["thermal_config_readonly"]["beta_nondim"],
        rtol=1e-12,
        atol=1e-12,
    )
    np.testing.assert_allclose(
        dimensional_result["temperature_nondim_field"],
        nondim_result["temperature_nondim_field"],
        rtol=1e-12,
        atol=1e-12,
    )
    np.testing.assert_allclose(
        dimensional_result["pressure_nondim_field"],
        nondim_result["pressure_nondim_field"],
        rtol=1e-12,
        atol=1e-12,
    )
    np.testing.assert_allclose(
        dimensional_result["viscosity_ratio_field"],
        nondim_result["viscosity_ratio_field"],
        rtol=1e-12,
        atol=1e-12,
    )
