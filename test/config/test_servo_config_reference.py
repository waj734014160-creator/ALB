import json
from pathlib import Path

import numpy as np

from ALB.alb import alb2, nodim_alb
from ALB.config import ALBConfig, Moog2ndServoConfig, NodimALBConfig, ServoConfig
from ALB.control.valve import (
    MOOG_2ND_NATURAL_FREQ_HZ,
    MOOG_2ND_TW,
    MOOG_2ND_ZETA,
    moog_2nd_servovalve,
)


ROOT = Path(__file__).resolve().parents[2]
REF_JSON = ROOT / "refs" / "servo_config_reference_v1.json"
REF_NPZ = ROOT / "refs" / "servo_config_reference_v1.npz"


def _servo_payload(cfg):
    return {
        "class": type(cfg).__name__,
        "dt": float(cfg.dt),
        "tw": float(cfg.tw),
        "zeta": float(cfg.zeta),
        "tp3": float(cfg.tp3),
        "delay": float(cfg.delay),
    }


def _alb_config_payload(cfg):
    return {
        "class": type(cfg).__name__,
        "servo": cfg.servo,
        "dt": float(cfg.dt),
        "servo_config": _servo_payload(cfg.servo_config),
    }


def _system_payload(model):
    return {
        "class": type(model).__name__,
        "servo_state_dims": [int(sv.main_model.A.shape[0]) for sv in model.servovalves],
        "servo_input_dims": [int(sv.main_model.B.shape[1]) for sv in model.servovalves],
        "servo_output_dims": [int(sv.main_model.C.shape[0]) for sv in model.servovalves],
    }


def _actual_cases():
    legacy_servo = ServoConfig()
    legacy_override = {
        "servo": "moog",
        "tw": legacy_servo.tw,
        "zeta": legacy_servo.zeta,
        "tp3": legacy_servo.tp3,
        "delay": legacy_servo.delay,
    }

    return {
        "ServoConfig": _servo_payload(legacy_servo),
        "Moog2ndServoConfig": _servo_payload(Moog2ndServoConfig()),
        "ALBConfig_default": _alb_config_payload(ALBConfig()),
        "ALBConfig_from_empty": _alb_config_payload(ALBConfig.from_dict({})),
        "ALBConfig_from_servo_moog_no_override": _alb_config_payload(
            ALBConfig.from_dict({"servo": "moog"})
        ),
        "ALBConfig_from_servo_moog_with_legacy_override": _alb_config_payload(
            ALBConfig.from_dict(legacy_override)
        ),
        "ALBConfig_from_flat_override": _alb_config_payload(
            ALBConfig.from_dict({"tw": 0.001, "zeta": 0.55, "delay": 0.002})
        ),
        "NodimALBConfig_default": _alb_config_payload(NodimALBConfig()),
        "NodimALBConfig_from_empty": _alb_config_payload(
            NodimALBConfig.from_dict({})
        ),
        "NodimALBConfig_from_servo_moog_no_override": _alb_config_payload(
            NodimALBConfig.from_dict({"servo": "moog"})
        ),
        "NodimALBConfig_from_flat_override": _alb_config_payload(
            NodimALBConfig.from_dict({"tw": 0.001, "zeta": 0.55, "delay": 0.002})
        ),
    }


def _actual_arrays():
    cfg = Moog2ndServoConfig()
    sv = moog_2nd_servovalve(cfg.dt, cfg.delay, cfg.tw, cfg.zeta)
    lti = sv.main_model
    return {
        "moog_2nd_continuous_A": np.asarray(lti.A, dtype=float),
        "moog_2nd_continuous_B": np.asarray(lti.B, dtype=float),
        "moog_2nd_continuous_C": np.asarray(lti.C, dtype=float),
        "moog_2nd_continuous_D": np.asarray(lti.D, dtype=float),
        "moog_2nd_discrete_A": np.asarray(lti._a, dtype=float),
        "moog_2nd_discrete_Bd0": np.asarray(lti._Bd0, dtype=float),
        "moog_2nd_discrete_Bd1": np.asarray(lti._Bd1, dtype=float),
        "moog_2nd_discrete_C": np.asarray(lti._c, dtype=float),
        "moog_2nd_discrete_D": np.asarray(lti._d, dtype=float),
    }


def test_servo_config_contract_matches_reference():
    reference = json.loads(REF_JSON.read_text(encoding="utf-8"))

    assert {
        "MOOG_2ND_NATURAL_FREQ_HZ": float(MOOG_2ND_NATURAL_FREQ_HZ),
        "MOOG_2ND_TW": float(MOOG_2ND_TW),
        "MOOG_2ND_ZETA": float(MOOG_2ND_ZETA),
    } == reference["constants"]
    assert _actual_cases() == reference["cases"]

    actual_systems = {
        "alb2_default": _system_payload(alb2(ALBConfig())),
        "nodim_alb_default": _system_payload(nodim_alb(alb_config=NodimALBConfig())),
    }
    assert actual_systems == reference["system_cases"]


def test_moog_2nd_state_space_matches_reference():
    reference_metadata = json.loads(REF_JSON.read_text(encoding="utf-8"))
    reference_arrays = np.load(REF_NPZ)
    actual_arrays = _actual_arrays()

    assert set(actual_arrays) == set(reference_arrays.files)
    for key, actual in actual_arrays.items():
        assert list(actual.shape) == reference_metadata["arrays"][key]["shape"]
        np.testing.assert_array_equal(actual, reference_arrays[key], err_msg=key)
