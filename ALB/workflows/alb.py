# coding: utf-8
import copy
import os
import pickle
from pathlib import Path

import numpy as np

from ALB.systems.alb import alb2, alb2_fuzzy, alb2_static
from ALB.systems.alb.assembly import nn_agent
from ALB.physics.bearing import MultiPad, StaticPosition, four_pads_bearing
from ALB.config import (
    ALBConfig,
    ALBNetConfig,
    FPBConfig,
    ResolvedTimeGrid,
    ThermalConfig,
    TimeGridConfig,
)
from ALB.dynamics.coupling import RsRotorBearingCouple
from ALB.dynamics.orbit import EllipseTrack, orbitime, test_bearing_orbit
from ALB.dynamics.rotor import rotor0
from ALB.physics.thermal import wrap_pad_collection_with_thermal
from ALB.infrastructure.config_io import (
    read_json5,
    read_json5_with_shared as read_json5_with_share,
)
from ALB.infrastructure.persistence import DirectoryArtifactWriter


class TaskConfigFactory:
    """Load one task directory and inject a single resolved physical time grid.

    The factory reads ``share.json5`` and ``time_iter.json5`` once during
    construction.  Child JSON5 files are merged against the resulting in-memory
    shared dictionary, so derived ``dt`` values never need to be persisted.
    """

    def __init__(self, config_dir):
        self.config_dir = Path(config_dir)
        self.share_path = self.config_dir / "share.json5"
        self.time_path = self.config_dir / "time_iter.json5"
        self._raw_share = read_json5(str(self.share_path))
        if self.time_path.is_file():
            self._raw_time = read_json5(str(self.time_path))
            time_payload = self._merge_time_share(self._raw_time, self._raw_share)
        else:
            self._raw_time = None
            time_payload = dict(self._raw_share)
        self.resolved_time_grid = TimeGridConfig.from_dict(time_payload).resolve()
        self._share = self._build_resolved_share(
            self._raw_share, self.resolved_time_grid
        )

    @staticmethod
    def _merge_time_share(time_data: dict, share_data: dict) -> dict:
        """Merge only the values requested by a time config's share contract."""

        payload = dict(time_data)
        share_keys = payload.pop("share_name", [])
        if not isinstance(share_keys, list):
            share_keys = [share_keys]
        for key in share_keys:
            if key not in share_data:
                raise KeyError(
                    f"Parameter '{key}' requested by 'time_iter.json5' not found "
                    "in share data."
                )
            payload[key] = share_data[key]
        return payload

    @staticmethod
    def _build_resolved_share(
        share_data: dict, resolved: ResolvedTimeGrid
    ) -> dict:
        """Return a private shared dictionary containing canonical time values."""

        shared = dict(share_data)
        shared.update(
            {
                "mode": resolved.mode,
                "freq": resolved.freq,
                "dt": resolved.dt,
                "steps": resolved.steps,
                "cycles": resolved.cycles,
                "points_per_cycle": resolved.points_per_cycle,
                "pt": resolved.points_per_cycle,
            }
        )
        if resolved.mode == "cycle_points":
            shared["n"] = int(resolved.cycles)
        else:
            shared.pop("n", None)
        return shared

    @property
    def share_config(self) -> dict:
        """Return a detached copy of the resolved in-memory shared values."""

        return copy.deepcopy(self._share)

    def read_config(self, file_name) -> dict:
        """Read one child config and merge the factory's resolved shared values."""

        path = Path(file_name)
        if not path.is_absolute():
            path = self.config_dir / path
        data = read_json5_with_share(str(path), shared=copy.deepcopy(self._share))
        if "freq" in data:
            data["freq"] = self.resolved_time_grid.freq
        if "dt" in data:
            data["dt"] = self.resolved_time_grid.dt
        thermal = data.get("thermal")
        if isinstance(thermal, dict):
            thermal["dt"] = self.resolved_time_grid.dt
        thermal_config = data.get("thermal_config")
        if isinstance(thermal_config, dict):
            thermal_config["dt"] = self.resolved_time_grid.dt
        standalone_thermal_keys = {"t_in", "cp_lub", "transient_enabled"}
        if standalone_thermal_keys.issubset(data):
            data["dt"] = self.resolved_time_grid.dt
        return data

    def time_iter(self):
        """Build a time iterator that preserves the resolved ``dt`` exactly."""

        return orbitime(**self.resolved_time_grid.to_time_config())


def task_alb_capacity(config_dir, save_dir=None, save_name="result"):
    # calculate the static equilibrium trajectory under different static loads
    print(config_dir)

    config_factory = TaskConfigFactory(config_dir)

    if save_dir is None:
        save_dir = os.path.join(config_dir, save_name)

    alb_config = config_factory.read_config("alb12.json5")
    alb_config = ALBConfig.from_dict(alb_config)

    alb = alb2_static(alb_config)
    sp_config = config_factory.read_config("static_position.json5")

    sp = StaticPosition(alb, **sp_config)
    wys = np.linspace(-0.1, -1, 10)
    wxs = np.zeros_like(wys)
    sp.run_track(wxs, wys)
    sp.save(path=save_dir)


def task_albf_capacity(config_dir, save_dir=None, save_name="result"):
    # calculate the static equilibrium trajectory under different static loads, fuzzy control
    print(config_dir)

    config_factory = TaskConfigFactory(config_dir)

    if save_dir is None:
        save_dir = os.path.join(config_dir, save_name)
    alb_config = config_factory.read_config("albfuzzy12.json5")
    alb_config["servo"] = "static"
    alb_config = ALBConfig.from_dict(alb_config, "FuzzyPID")

    alb = alb2_fuzzy(alb_config)
    sp_config = config_factory.read_config("static_position.json5")

    sp = StaticPosition(alb, **sp_config)
    wys = np.linspace(-0.1, -1, 10)
    wxs = np.zeros_like(wys)
    sp.run_track(wxs, wys)
    sp.save(path=save_dir)


def task_albnn_capacity(config_dir, save_dir=None, save_name="result"):
    # calculate the static equilibrium trajectory under different static loads, neural network control
    print(config_dir)

    config_factory = TaskConfigFactory(config_dir)

    if save_dir is None:
        save_dir = os.path.join(config_dir, save_name)

    alb_config = config_factory.read_config("alb12.json5")
    alb_config = ALBConfig.from_dict(alb_config)

    alb = alb2_static(alb_config)
    nn_config = config_factory.read_config("nn_agent.json5")
    nn_config = ALBNetConfig.from_dict(nn_config)
    alb = nn_agent(alb, nn_config)

    sp_config = config_factory.read_config("static_position.json5")

    sp = StaticPosition(alb, **sp_config)
    wys = np.linspace(-0.1, -1, 10)
    wxs = np.zeros_like(wys)
    sp.run_track(wxs, wys)
    sp.save(path=save_dir)


def task_alb_dynamic(config_dir, save_dir=None, save_name="result", save_alb=False):
    # calculate the dynamic response under a certain orbit, and save the bearing forces and the trajectory of the rotor center; if save_alb is True, also save the ALB model
    print(config_dir)
    config_factory = TaskConfigFactory(config_dir)

    if save_dir is None:
        save_dir = config_dir
    et_config = config_factory.read_config("et.json5")
    ti = config_factory.time_iter()

    alb_config = config_factory.read_config("alb12.json5")
    alb_config = ALBConfig.from_dict(alb_config)
    alb = alb2(alb_config)

    et = EllipseTrack(**et_config)

    tbo_config = config_factory.read_config("tbo.json5")
    tbo = test_bearing_orbit(ti, alb, et, **tbo_config)
    save_data = {
        "bft": tbo["bft"].bearing_forces,
        "ibft": tbo["ibft"].bearing_forces,
        "hkc": tbo["hkc"],
    }
    root_path = os.path.join(save_dir, save_name)
    if root_path is None:
        root_path = os.path.join(os.getcwd(), "data")
    if not os.path.exists(root_path):
        os.makedirs(root_path)
    file_path = os.path.join(root_path, "data.pkl")
    with open(file_path, "wb") as f:
        pickle.dump(save_data, f)
    if save_alb:
        alb.save(
            tofile=True,
            path=os.path.join(root_path, "alb"),
            name="alb",
            writer=DirectoryArtifactWriter(overwrite=True),
        )


def task_albnn_dynamic(config_dir, save_dir=None, save_name="result", save_alb=False):
    # calculate the dynamic response under a certain orbit, and save the bearing forces and the trajectory of the rotor center;
    # if save_alb is True, also save the ALB model, neural network control
    print(config_dir)
    config_factory = TaskConfigFactory(config_dir)

    if save_dir is None:
        save_dir = config_dir
    et_config = config_factory.read_config("et.json5")
    ti = config_factory.time_iter()

    alb_config = config_factory.read_config("alb12.json5")
    alb_config = ALBConfig.from_dict(alb_config)
    alb = alb2(alb_config)

    nn_config = config_factory.read_config("nn_agent.json5")
    nn_config = ALBNetConfig.from_dict(nn_config)
    alb = nn_agent(alb, nn_config)

    et = EllipseTrack(**et_config)

    tbo_config = config_factory.read_config("tbo.json5")
    tbo = test_bearing_orbit(ti, alb, et, **tbo_config)
    save_data = {
        "bft": tbo["bft"].bearing_forces,
        "ibft": tbo["ibft"].bearing_forces,
        "hkc": tbo["hkc"],
    }
    root_path = os.path.join(save_dir, save_name)
    if root_path is None:
        root_path = os.path.join(os.getcwd(), "data")
    if not os.path.exists(root_path):
        os.makedirs(root_path)
    file_path = os.path.join(root_path, "data.pkl")
    with open(file_path, "wb") as f:
        pickle.dump(save_data, f)
    if save_alb:
        alb.save(
            tofile=True,
            path=os.path.join(root_path, "albnn"),
            name="albnn",
            writer=DirectoryArtifactWriter(overwrite=True),
        )


def task_albf_dynamic(config_dir, save_dir=None, save_name="result"):
    # calculate the dynamic response under a certain orbit, and save the bearing forces and the trajectory of the rotor center; fuzzy control
    print(config_dir)
    if save_dir is None:
        save_dir = config_dir
    config_factory = TaskConfigFactory(config_dir)

    et_config = config_factory.read_config("et.json5")
    ti = config_factory.time_iter()

    alb_config = config_factory.read_config("albfuzzy12.json5")
    alb_config = ALBConfig.from_dict(alb_config, "FuzzyPID")
    alb = alb2_fuzzy(alb_config)

    et = EllipseTrack(**et_config)

    tbo_config = config_factory.read_config("tbo.json5")
    tbo = test_bearing_orbit(ti, alb, et, **tbo_config)
    save_data = {
        "bft": tbo["bft"].bearing_forces,
        "ibft": tbo["ibft"].bearing_forces,
        "hkc": tbo["hkc"],
    }
    root_path = os.path.join(save_dir, save_name)
    if root_path is None:
        root_path = os.path.join(os.getcwd(), "data")
    if not os.path.exists(root_path):
        os.makedirs(root_path)
    file_path = os.path.join(root_path, "data.pkl")
    with open(file_path, "wb") as f:
        pickle.dump(save_data, f)


def task_alb_rotor_couple(config_dir, save_dir=None, bearing="alb", save_name="result"):
    print(config_dir)
    if save_dir is None:
        save_dir = config_dir
    config_factory = TaskConfigFactory(config_dir)
    ti = config_factory.time_iter()

    alb_config = config_factory.read_config("alb12.json5")
    if bearing == "alb":
        alb_config = ALBConfig.from_dict(alb_config)
        alb = alb2(alb_config)
    elif bearing == "albf":
        alb_config = ALBConfig.from_dict(alb_config, "FuzzyPID")
        alb = alb2_fuzzy(alb_config)
    else:
        raise ValueError("bearing must be alb or albf")

    hb_config = config_factory.read_config("hb34.json5")
    hb_config = FPBConfig.from_dict(hb_config)
    hb = four_pads_bearing(hb_config)
    hb_thermal_config = hb_config.thermal_config
    if hb_thermal_config is not None:
        thermal_args = vars(hb_thermal_config).copy()
        if thermal_args.get("dt") is None:
            thermal_args["dt"] = ti.dt
        if not thermal_args.get("transient_enabled"):
            thermal_args["transient_enabled"] = True
        hb_thermal_config = ThermalConfig.from_dict(thermal_args)
    if hb_thermal_config is not None:
        hb = MultiPad(
            *wrap_pad_collection_with_thermal(list(hb.bearings), hb_thermal_config)
        )

    rotor_config = config_factory.read_config("rotor.json5")
    rotor = rotor0(**rotor_config)

    rbc = RsRotorBearingCouple(rotor, ti)
    rbc.add_bearing(alb, alb.node_link)
    rbc.add_bearing(hb, hb.node_link)

    ubf_config = config_factory.read_config("unbalance_force.json5")
    rbc.add_unbalance(**ubf_config)
    rbc.add_gravity()
    rbc.solve()
    root_path = os.path.join(save_dir, save_name)
    rbc.save(
        tofile=True,
        path=root_path,
        writer=DirectoryArtifactWriter(overwrite=True),
    )


def task_albf_rotor_couple(config_dir, save_dir=None, save_name="result"):
    print(config_dir)
    if save_dir is None:
        save_dir = config_dir
    config_factory = TaskConfigFactory(config_dir)
    ti = config_factory.time_iter()

    alb_config = config_factory.read_config("albfuzzy12.json5")
    alb_config = ALBConfig.from_dict(alb_config, "FuzzyPID")
    alb = alb2_fuzzy(alb_config)

    hb_config = config_factory.read_config("hb34.json5")
    hb_config = FPBConfig.from_dict(hb_config)
    hb = four_pads_bearing(hb_config)
    hb_thermal_config = hb_config.thermal_config
    if hb_thermal_config is not None:
        thermal_args = vars(hb_thermal_config).copy()
        if thermal_args.get("dt") is None:
            thermal_args["dt"] = ti.dt
        if not thermal_args.get("transient_enabled"):
            thermal_args["transient_enabled"] = True
        hb_thermal_config = ThermalConfig.from_dict(thermal_args)
    if hb_thermal_config is not None:
        hb = MultiPad(
            *wrap_pad_collection_with_thermal(list(hb.bearings), hb_thermal_config)
        )

    rotor_config = config_factory.read_config("rotor.json5")
    rotor = rotor0(**rotor_config)

    rbc = RsRotorBearingCouple(rotor, ti)
    rbc.add_bearing(alb, alb.node_link)
    rbc.add_bearing(hb, hb.node_link)

    ubf_config = config_factory.read_config("unbalance_force.json5")
    rbc.add_unbalance(**ubf_config)
    rbc.add_gravity()
    rbc.solve()
    root_path = os.path.join(save_dir, save_name)
    rbc.save(
        tofile=True,
        path=root_path,
        writer=DirectoryArtifactWriter(overwrite=True),
    )


def task_albnn_rotor_couple(config_dir, save_dir=None, save_name="result"):
    print(config_dir)
    if save_dir is None:
        save_dir = config_dir
    config_factory = TaskConfigFactory(config_dir)
    ti = config_factory.time_iter()

    alb_config = config_factory.read_config("alb12.json5")
    alb_config = ALBConfig.from_dict(alb_config)
    alb = alb2(alb_config)
    nn_config = config_factory.read_config("nn_agent.json5")
    nn_config = ALBNetConfig.from_dict(nn_config)
    alb = nn_agent(alb, nn_config)

    # hb_config = os.path.join(config_dir, 'hb34.json5')
    # hb_config = read_json5_with_share(hb_config)
    # hb = four_pads_bearing(**hb_config)
    nn_config["agent"] = "HydroNNAgent"
    hb = nn_agent(alb, nn_config)
    hb.node_link = 34

    rotor_config = config_factory.read_config("rotor.json5")
    rotor = rotor0(**rotor_config)

    rbc = RsRotorBearingCouple(rotor, ti)
    rbc.add_bearing(alb, alb.node_link)
    rbc.add_bearing(hb, hb.node_link)

    ubf_config = config_factory.read_config("unbalance_force.json5")
    rbc.add_unbalance(**ubf_config)
    rbc.add_gravity()
    rbc.solve()
    root_path = os.path.join(save_dir, save_name)
    rbc.save(
        tofile=True,
        path=root_path,
        writer=DirectoryArtifactWriter(overwrite=True),
    )


def couple_task(task_name):
    if task_name == "alb":
        return task_alb_rotor_couple
    elif task_name == "albf":
        return task_albf_rotor_couple
    elif task_name == "albnn":
        return task_albnn_rotor_couple
    else:
        raise ValueError("name must be alb or albf")


def static_task(task_name):
    if task_name == "alb":
        return task_alb_capacity
    elif task_name == "albf":
        return task_albf_capacity
    elif task_name == "albnn":
        return task_albnn_capacity
    else:
        raise ValueError("name must be alb or albf")


def dynamic_task(task_name):
    if task_name == "alb":
        return task_alb_dynamic
    elif task_name == "albf":
        return task_albf_dynamic
    elif task_name == "albnn":
        return task_albnn_dynamic
    else:
        raise ValueError("name must be alb or albf")
