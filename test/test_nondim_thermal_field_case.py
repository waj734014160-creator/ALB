import numpy as np

from run import nondim_thermal_field_case as case


def test_nondim_thermal_field_case_uses_thermal_config_input():
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


def test_nondim_pressure_field_matches_dimensional_scaling():
    result = case.solve_nondim_thermal_field_case({"delta_t_scale": 30.0})

    np.testing.assert_allclose(
        result["pressure_field"],
        result["pressure_nondim_field"] * result["ps"],
        rtol=1e-12,
        atol=1e-12,
    )


def test_zero_heat_partition_gives_zero_nondim_temperature_rise():
    result = case.solve_nondim_thermal_field_case({"heat_partition": 0.0})

    np.testing.assert_allclose(result["temperature_nondim"], 0.0, atol=1e-8)
    np.testing.assert_allclose(result["t_eff_nondim"], 0.0, atol=1e-8)


def test_dimensional_and_nondim_parameter_sets_match_viscosity_field_evolution():
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
