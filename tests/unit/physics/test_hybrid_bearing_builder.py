"""Topology-driven mixed-bearing construction tests."""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from ALB.config import HydConfig, HybridOrificeConfig, NodimPadConfig
from ALB.contracts import (
    BearingInput,
    BearingRuntimeProtocol,
    LifecycleState,
)
from ALB.physics.bearing import (
    HybridBearing,
    NodimHybridBearing,
    build_hybrid_bearing,
)


def _dimensional_config() -> HydConfig:
    """Return a compact dimensional film configuration."""

    return HydConfig(
        nx=5,
        nz=3,
        max_iter=5,
        error_set=1.0e-5,
        save_p=False,
        save_h=False,
    )


def _nondimensional_config() -> NodimPadConfig:
    """Return a compact nondimensional film configuration."""

    return NodimPadConfig(
        lambda_value=1.2,
        lr=1.0,
        lx=360.0,
        lz=2.0,
        nx=5,
        nz=3,
        max_iter=5,
        error_set=1.0e-5,
        scale_w=3000.0,
    )


def test_hybrid_builder_returns_initialized_hydrodynamic_runtime():
    runtime = build_hybrid_bearing(_dimensional_config())

    assert isinstance(runtime, HybridBearing)
    assert isinstance(runtime, BearingRuntimeProtocol)
    assert runtime.lifecycle_state is LifecycleState.READY
    assert runtime.simple_models == []

    output = runtime.step(
        BearingInput(
            [0.0, 0.0],
            [0.0, 0.0],
            0.0,
            "dimensional",
        )
    )

    assert runtime.output() is output
    assert runtime.result_snapshot().metadata["orifice_count"] == 0
    assert np.all(np.isfinite(output.force))


@pytest.mark.parametrize(
    "flow_definition",
    [
        {"radius": 0.5e-3},
        {"cq": 0.1},
    ],
)
def test_constructor_supplied_orifices_enable_coupled_calculation(
    flow_definition,
):
    config = _dimensional_config()
    orifices = HybridOrificeConfig(
        positions=[[0.5, 0.5]],
        pressure=config.ps,
        **flow_definition,
    )

    runtime = build_hybrid_bearing(config, orifices=orifices)

    assert runtime.lifecycle_state is LifecycleState.READY
    assert len(runtime.simple_models) == 1
    output = runtime.step(
        BearingInput(
            [0.0, 0.0],
            [0.0, 0.0],
            0.0,
            "dimensional",
        )
    )
    assert np.all(np.isfinite(output.force))
    assert runtime.result_snapshot().metadata["orifice_count"] == 1


def test_hybrid_builder_dispatches_nondimensional_config_without_mode_flag():
    runtime = build_hybrid_bearing(_nondimensional_config(), x0=10.0)

    assert "mode" not in inspect.signature(build_hybrid_bearing).parameters
    assert isinstance(runtime, NodimHybridBearing)
    assert isinstance(runtime, BearingRuntimeProtocol)
    assert runtime.lifecycle_state is LifecycleState.READY
    assert runtime.diagnostic_snapshot().metadata["orifice_count"] == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"radius": 1.0e-4, "cq": 0.1},
        {"cq": 0.0},
    ],
)
def test_hybrid_orifice_config_requires_one_positive_flow_definition(kwargs):
    with pytest.raises(ValueError):
        HybridOrificeConfig(positions=[[0.5, 0.5]], **kwargs)
