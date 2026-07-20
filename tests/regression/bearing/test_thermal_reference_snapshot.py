import json
from pathlib import Path

import numpy as np

from ALB.physics.bearing import HydrostaticBearing
from ALB.config import HydConfig
from ALB.config import ThermalConfig
from ALB.physics.thermal import ThermalHydroBearing


ROOT = Path(__file__).resolve().parents[3]
REF_DIR = ROOT / "refs"
REF_NPZ = REF_DIR / "thermal_small_model_reference_v1.npz"
REF_JSON = REF_DIR / "thermal_small_model_reference_v1.json"


def _run_reference_case():
    metadata = json.loads(REF_JSON.read_text(encoding="utf-8"))
    cfg = HydConfig(**metadata["hyd_config"])
    pad = HydrostaticBearing(cfg)
    tcfg = ThermalConfig(**metadata["thermal_config"])
    model = ThermalHydroBearing(pad, tcfg)
    model.init()

    uxy = np.asarray(metadata["input"]["uxy"], dtype=np.float64)
    uxyt = np.asarray(metadata["input"]["uxyt"], dtype=np.float64)
    model.input(uxy, uxyt)
    out = model.output(calc=True, nodim=True)

    return {
        "input_uxy": uxy,
        "input_uxyt": uxyt,
        "force": np.asarray(out["force"], dtype=np.float64),
        "friction": np.asarray([out["friction"]], dtype=np.float64),
        "q_orifice_total": np.asarray([out["q_orifice_total"]], dtype=np.float64),
        "t_eff": np.asarray([out["t_eff"]], dtype=np.float64),
        "thermal_iterations": np.asarray([out["thermal_iterations"]], dtype=np.int64),
        "thermal_converged": np.asarray([bool(out["thermal_converged"])], dtype=np.bool_),
        "thermal_transient": np.asarray([bool(out["thermal_transient"])], dtype=np.bool_),
        "viscosity": np.asarray([out["viscosity"]], dtype=np.float64),
        "w": np.asarray([out["w"]], dtype=np.float64),
        "field_x": np.asarray(out["field_x"], dtype=np.float64),
        "field_z": np.asarray(out["field_z"], dtype=np.float64),
        "pressure_field": np.asarray(out["pressure_field"], dtype=np.float64),
        "temperature": np.asarray(out["temperature"], dtype=np.float64),
        "temperature_field": np.asarray(out["temperature_field"], dtype=np.float64),
        "temperature_film": np.asarray(out["temperature_film"], dtype=np.float64),
        "temperature_x": np.asarray(out["temperature_x"], dtype=np.float64),
        "temperature_z": np.asarray(out["temperature_z"], dtype=np.float64),
        "viscosity_field": np.asarray(out["viscosity_field"], dtype=np.float64),
        "viscosity_field_grid": np.asarray(out["viscosity_field_grid"], dtype=np.float64),
    }


def test_thermal_small_model_matches_reference_snapshot():
    with np.load(REF_NPZ) as reference:
        actual = _run_reference_case()
        assert set(actual) == set(reference.files)

        for key in reference.files:
            if np.issubdtype(reference[key].dtype, np.floating):
                # The dimensional thermal wrapper now delegates to the equivalent
                # nondimensional backend, which can shift final rounding bits.
                np.testing.assert_allclose(
                    actual[key],
                    reference[key],
                    rtol=1e-7,
                    atol=1e-9,
                    err_msg=key,
                )
            else:
                np.testing.assert_array_equal(actual[key], reference[key], err_msg=key)
