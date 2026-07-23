"""Public typed builder and transitional runtime contract tests."""

from __future__ import annotations

from dataclasses import fields

import numpy as np
import pytest

from ALB.config import (
    ControlMode,
    NodimALBConfig,
)
from ALB.contracts import (
    BearingInput,
    BearingRuntimeProtocol,
    DirectSpoolBearingInput,
    DirectSpoolBearingRuntimeProtocol,
    LifecycleState,
    ValveOutput,
)
from ALB.systems.alb import (
    BearingBuildDependencies,
    build_alb,
    build_direct_spool_alb,
    nodim_alb,
)


def _config(mode: ControlMode) -> NodimALBConfig:
    """Return one compact current config for public builder tests."""

    return NodimALBConfig.from_dict(
        {
            "alb": "ALBSV" if mode is ControlMode.DIRECT_SPOOL else "ALB",
            "controller": "none",
            "controller_config": None,
            "servo": "static",
            "switch": False,
            "node_link": 2,
            "nx": 15,
            "nz": 7,
            "lx": 80.0,
            "lz": 2.0,
            "lambda_value": 1.2,
            "lr": 1.0,
            "position": [[0.5, 0.25], [0.5, 0.5], [0.5, 0.75]],
            "cq0": 6.0557,
            "cq1": 0.02313,
            "cq2": 0.002173,
            "ps": 1.0,
            "p0": 0.0,
        }
    )


def test_standard_builder_hides_block_and_output_is_read_only():
    runtime = build_alb(_config(ControlMode.NONE))

    assert isinstance(runtime, BearingRuntimeProtocol)
    assert runtime.lifecycle_state is LifecycleState.READY
    assert not hasattr(runtime, "implementation")
    dto = BearingInput(
        [0.1, -0.2],
        [0.03, -0.04],
        0.0,
        "nondimensional",
    )
    output = runtime.step(dto)
    history_rows = len(runtime.results)

    assert runtime.output() is output
    assert runtime.output() is output
    assert len(runtime.results) == history_rows == 0
    assert runtime.result_snapshot().values["force"] is not output.force
    np.testing.assert_array_equal(
        runtime.result_snapshot().values["force"],
        output.force,
    )

    runtime.input(
        BearingInput(
            [0.08, -0.17],
            [0.01, -0.02],
            0.001,
            "nondimensional",
        )
    )
    with pytest.raises(RuntimeError, match="unavailable"):
        runtime.output()


def test_direct_spool_builder_requires_explicit_spool_dto():
    runtime = build_direct_spool_alb(_config(ControlMode.DIRECT_SPOOL))

    assert isinstance(runtime, DirectSpoolBearingRuntimeProtocol)
    assert runtime.lifecycle_state is LifecycleState.READY
    output = runtime.step(
        DirectSpoolBearingInput(
            BearingInput(
                [0.1, -0.2],
                [0.03, -0.04],
                0.0,
                "nondimensional",
            ),
            ValveOutput([0.2, -0.3], 0.0, "nondimensional"),
        )
    )

    assert output.unit_system.value == "nondimensional"
    assert output.force.shape == (2,)
    with pytest.raises(TypeError, match="direct spool"):
        runtime.input(
            BearingInput(
                [0.1, -0.2],
                [0.03, -0.04],
                0.001,
                "nondimensional",
            )
        )


def test_builders_reject_the_wrong_control_mode():
    standard = _config(ControlMode.NONE)
    direct = _config(ControlMode.DIRECT_SPOOL)

    with pytest.raises(ValueError, match="direct_spool"):
        build_alb(direct)
    with pytest.raises(ValueError, match="requires direct_spool"):
        build_direct_spool_alb(standard)


def test_build_dependencies_do_not_accept_runtime_or_output_dependencies():
    assert {item.name for item in fields(BearingBuildDependencies)} == {
        "component_factory",
        "controller_factory",
    }


def test_builder_rejects_a_custom_factory_runtime_that_is_not_ready():
    def running_factory(config, controller_factory):
        del controller_factory
        runtime = nodim_alb(config)
        runtime.input(
            BearingInput(
                [0.1, -0.2],
                [0.03, -0.04],
                0.0,
                "nondimensional",
            )
        )
        return runtime

    dependencies = BearingBuildDependencies(component_factory=running_factory)

    with pytest.raises(RuntimeError, match="READY"):
        build_alb(_config(ControlMode.NONE), dependencies=dependencies)
