# coding: utf-8
import os
import pickle

import numpy as np

from ALB.alb import alb2, alb2_fuzzy, alb2_static, nn_agent
from ALB.bearing import MultiPad, StaticPosition, four_pads_bearing
from ALB.config import ALBConfig, ALBNetConfig, FPBConfig, ThermalConfig
from ALB.couple import RsRotorBearingCouple
from ALB.orbit import EllipseTrack, orbitime, test_bearing_orbit
from ALB.rotor import rotor0
from ALB.thermal import wrap_pad_collection_with_thermal
from ALB.tool import read_json5_with_share, read_share


def task_alb_capacity(config_dir, save_dir=None, save_name="result"):
    # calculate the static equilibrium trajectory under different static loads
    print(config_dir)

    share_config = os.path.join(config_dir, "share.json5")
    read_share(share_config, recover=True)

    if save_dir is None:
        save_dir = os.path.join(config_dir, save_name)

    alb_config = os.path.join(config_dir, "alb12.json5")
    alb_config = read_json5_with_share(alb_config)
    alb_config = ALBConfig.from_dict(alb_config)

    alb = alb2_static(alb_config)
    sp_config = os.path.join(config_dir, "static_position.json5")
    sp_config = read_json5_with_share(sp_config)

    sp = StaticPosition(alb, **sp_config)
    wys = np.linspace(-0.1, -1, 10)
    wxs = np.zeros_like(wys)
    sp.run_track(wxs, wys)
    sp.save(path=save_dir)


def task_albf_capacity(config_dir, save_dir=None, save_name="result"):
    # calculate the static equilibrium trajectory under different static loads, fuzzy control
    print(config_dir)

    share_config = os.path.join(config_dir, "share.json5")
    read_share(share_config, recover=True)

    if save_dir is None:
        save_dir = os.path.join(config_dir, save_name)
    alb_config = os.path.join(config_dir, "albfuzzy12.json5")
    alb_config = read_json5_with_share(alb_config)
    alb_config["servo"] = "static"
    alb_config = ALBConfig.from_dict(alb_config, "FuzzyPID")

    alb = alb2_fuzzy(alb_config)
    sp_config = os.path.join(config_dir, "static_position.json5")
    sp_config = read_json5_with_share(sp_config)

    sp = StaticPosition(alb, **sp_config)
    wys = np.linspace(-0.1, -1, 10)
    wxs = np.zeros_like(wys)
    sp.run_track(wxs, wys)
    sp.save(path=save_dir)


def task_albnn_capacity(config_dir, save_dir=None, save_name="result"):
    # calculate the static equilibrium trajectory under different static loads, neural network control
    print(config_dir)

    share_config = os.path.join(config_dir, "share.json5")
    read_share(share_config, recover=True)

    if save_dir is None:
        save_dir = os.path.join(config_dir, save_name)

    alb_config = os.path.join(config_dir, "alb12.json5")
    alb_config = read_json5_with_share(alb_config)
    alb_config = ALBConfig.from_dict(alb_config)

    alb = alb2_static(alb_config)
    nn_config = os.path.join(config_dir, "nn_agent.json5")
    nn_config = read_json5_with_share(nn_config)
    nn_config = ALBNetConfig.from_dict(nn_config)
    alb = nn_agent(alb, nn_config)

    sp_config = os.path.join(config_dir, "static_position.json5")
    sp_config = read_json5_with_share(sp_config)

    sp = StaticPosition(alb, **sp_config)
    wys = np.linspace(-0.1, -1, 10)
    wxs = np.zeros_like(wys)
    sp.run_track(wxs, wys)
    sp.save(path=save_dir)


def task_alb_dynamic(config_dir, save_dir=None, save_name="result", save_alb=False):
    # calculate the dynamic response under a certain orbit, and save the bearing forces and the trajectory of the rotor center; if save_alb is True, also save the ALB model
    print(config_dir)
    share_config = os.path.join(config_dir, "share.json5")
    read_share(share_config, recover=True)

    if save_dir is None:
        save_dir = config_dir
    et_config = os.path.join(config_dir, "et.json5")
    et_config = read_json5_with_share(et_config)

    time_config = os.path.join(config_dir, "time_iter.json5")
    time_config = read_json5_with_share(time_config)
    ti = orbitime(**time_config)

    alb_config = os.path.join(config_dir, "alb12.json5")
    alb_config = read_json5_with_share(alb_config)
    alb_config = ALBConfig.from_dict(alb_config)
    alb = alb2(alb_config)

    et = EllipseTrack(**et_config)

    tbo_config = os.path.join(config_dir, "tbo.json5")
    tbo_config = read_json5_with_share(tbo_config)
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
        alb.save(tofile=True, path=os.path.join(root_path, "alb"), name="alb")


def task_albnn_dynamic(config_dir, save_dir=None, save_name="result", save_alb=False):
    # calculate the dynamic response under a certain orbit, and save the bearing forces and the trajectory of the rotor center;
    # if save_alb is True, also save the ALB model, neural network control
    print(config_dir)
    share_config = os.path.join(config_dir, "share.json5")
    read_share(share_config, recover=True)

    if save_dir is None:
        save_dir = config_dir
    et_config = os.path.join(config_dir, "et.json5")
    et_config = read_json5_with_share(et_config)

    time_config = os.path.join(config_dir, "time_iter.json5")
    time_config = read_json5_with_share(time_config)
    ti = orbitime(**time_config)

    alb_config = os.path.join(config_dir, "alb12.json5")
    alb_config = read_json5_with_share(alb_config)
    alb_config = ALBConfig.from_dict(alb_config)
    alb = alb2(alb_config)

    nn_config = os.path.join(config_dir, "nn_agent.json5")
    nn_config = read_json5_with_share(nn_config)
    nn_config = ALBNetConfig.from_dict(nn_config)
    alb = nn_agent(alb, nn_config)

    et = EllipseTrack(**et_config)

    tbo_config = os.path.join(config_dir, "tbo.json5")
    tbo_config = read_json5_with_share(tbo_config)
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
        alb.save(tofile=True, path=os.path.join(root_path, "albnn"), name="albnn")


def task_albf_dynamic(config_dir, save_dir=None, save_name="result"):
    # calculate the dynamic response under a certain orbit, and save the bearing forces and the trajectory of the rotor center; fuzzy control
    print(config_dir)
    if save_dir is None:
        save_dir = config_dir
    share_config = os.path.join(config_dir, "share.json5")
    read_share(share_config, recover=True)

    et_config = os.path.join(config_dir, "et.json5")
    et_config = read_json5_with_share(et_config)

    time_config = os.path.join(config_dir, "time_iter.json5")
    time_config = read_json5_with_share(time_config)
    ti = orbitime(**time_config)

    alb_config = os.path.join(config_dir, "albfuzzy12.json5")
    alb_config = read_json5_with_share(alb_config)
    alb_config = ALBConfig.from_dict(alb_config, "FuzzyPID")
    alb = alb2_fuzzy(alb_config)

    et = EllipseTrack(**et_config)

    tbo_config = os.path.join(config_dir, "tbo.json5")
    tbo_config = read_json5_with_share(tbo_config)
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
    share_config = os.path.join(config_dir, "share.json5")
    read_share(share_config, recover=True)

    time_config = os.path.join(config_dir, "time_iter.json5")
    time_config = read_json5_with_share(time_config)
    ti = orbitime(**time_config)

    alb_config = os.path.join(config_dir, "alb12.json5")
    alb_config = read_json5_with_share(alb_config)
    if bearing == "alb":
        alb_config = ALBConfig.from_dict(alb_config)
        alb = alb2(alb_config)
    elif bearing == "albf":
        alb_config = ALBConfig.from_dict(alb_config, "FuzzyPID")
        alb = alb2_fuzzy(alb_config)
    else:
        raise ValueError("bearing must be alb or albf")

    hb_config = os.path.join(config_dir, "hb34.json5")
    hb_config = read_json5_with_share(hb_config)
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

    rotor_config = os.path.join(config_dir, "rotor.json5")
    rotor_config = read_json5_with_share(rotor_config)
    rotor = rotor0(**rotor_config)

    rbc = RsRotorBearingCouple(rotor, ti, alb, hb)

    ubf_config = os.path.join(config_dir, "unbalance_force.json5")
    ubf_config = read_json5_with_share(ubf_config)
    rbc.add_unbalance(**ubf_config)
    rbc.add_gravity()
    rbc.solve()
    root_path = os.path.join(save_dir, save_name)
    rbc.save(tofile=True, path=root_path)


def task_albf_rotor_couple(config_dir, save_dir=None, save_name="result"):
    print(config_dir)
    if save_dir is None:
        save_dir = config_dir
    share_config = os.path.join(config_dir, "share.json5")
    read_share(share_config, recover=True)

    time_config = os.path.join(config_dir, "time_iter.json5")
    time_config = read_json5_with_share(time_config)
    ti = orbitime(**time_config)

    alb_config = os.path.join(config_dir, "albfuzzy12.json5")
    alb_config = read_json5_with_share(alb_config)
    alb_config = ALBConfig.from_dict(alb_config, "FuzzyPID")
    alb = alb2_fuzzy(alb_config)

    hb_config = os.path.join(config_dir, "hb34.json5")
    hb_config = read_json5_with_share(hb_config)
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

    rotor_config = os.path.join(config_dir, "rotor.json5")
    rotor_config = read_json5_with_share(rotor_config)
    rotor = rotor0(**rotor_config)

    rbc = RsRotorBearingCouple(rotor, ti, alb, hb)

    ubf_config = os.path.join(config_dir, "unbalance_force.json5")
    ubf_config = read_json5_with_share(ubf_config)
    rbc.add_unbalance(**ubf_config)
    rbc.add_gravity()
    rbc.solve()
    root_path = os.path.join(save_dir, save_name)
    rbc.save(tofile=True, path=root_path)


def task_albnn_rotor_couple(config_dir, save_dir=None, save_name="result"):
    print(config_dir)
    if save_dir is None:
        save_dir = config_dir
    share_config = os.path.join(config_dir, "share.json5")
    read_share(share_config, recover=True)

    time_config = os.path.join(config_dir, "time_iter.json5")
    time_config = read_json5_with_share(time_config)
    ti = orbitime(**time_config)

    alb_config = os.path.join(config_dir, "alb12.json5")
    alb_config = read_json5_with_share(alb_config)
    alb_config = ALBConfig.from_dict(alb_config)
    alb = alb2(alb_config)
    nn_config = os.path.join(config_dir, "nn_agent.json5")
    nn_config = read_json5_with_share(nn_config)
    nn_config = ALBNetConfig.from_dict(nn_config)
    alb = nn_agent(alb, nn_config)

    # hb_config = os.path.join(config_dir, 'hb34.json5')
    # hb_config = read_json5_with_share(hb_config)
    # hb = four_pads_bearing(**hb_config)
    nn_config["agent"] = "HydroNNAgent"
    hb = nn_agent(alb, nn_config)
    hb.node_link = 34

    rotor_config = os.path.join(config_dir, "rotor.json5")
    rotor_config = read_json5_with_share(rotor_config)
    rotor = rotor0(**rotor_config)

    rbc = RsRotorBearingCouple(rotor, ti, alb, hb)

    ubf_config = os.path.join(config_dir, "unbalance_force.json5")
    ubf_config = read_json5_with_share(ubf_config)
    rbc.add_unbalance(**ubf_config)
    rbc.add_gravity()
    rbc.solve()
    root_path = os.path.join(save_dir, save_name)
    rbc.save(tofile=True, path=root_path)


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
