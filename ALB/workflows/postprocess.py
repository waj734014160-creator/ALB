# coding: utf-8
import os
import pickle
from tkinter import filedialog

import numpy as np
import pandas as pd
import tqdm

from ALB.infrastructure.config_io import list_directories as listdir
from ALB.infrastructure.config_io import read_json5
from ALB.workflows.naming import parse_parameter_name as namevalue


def read_pickles(save_path=None):
    """
    read alb pickle dynamic data for task_alb2.py
    """
    if save_path is None:
        f_path = filedialog.askdirectory()
    else:
        f_path = save_path
    data = pd.DataFrame(dtype=np.float64)
    file_names = os.listdir(f_path)
    kname = ['kxx', 'kxy', 'kyx', 'kyy']
    cname = ['cxx', 'cxy', 'cyx', 'cyy']
    for i_d, fn in tqdm.tqdm(enumerate(file_names)):
        if fn.endswith('.pkl'):
            nv = namevalue(fn)
            keys = list(nv.keys())
            values = list(nv.values())
            data.loc[i_d, keys] = np.array(values, dtype=np.float64)
            tol_fn = os.path.join(f_path, fn)
            with open(tol_fn, 'rb') as f:
                dat = pickle.load(f)
            data.loc[i_d, kname] = dat['hkc']['k'].reshape(-1)
            data.loc[i_d, cname] = dat['hkc']['c'].reshape(-1)
    if save_path is None:
        save_path = os.path.join(f_path, 'data.csv')
    data.to_csv(save_path)
    return data


def static(f_path, save_path):
    """Execute static."""
    dirs = listdir(f_path, full=False)
    tags = ['kp', 'freq']
    data = pd.DataFrame(columns=[*tags, 'data'])
    qtag = ['q{}'.format(i) for i in range(4)]
    for dr in tqdm.tqdm(dirs):
        share_path = os.path.join(f_path, dr, 'share.json5')
        share = read_json5(share_path)
        values = share
        datapath = os.path.join(f_path, dr, 'result', 'track_output.csv')
        if not os.path.exists(datapath):
            print('No data in {}'.format(dr))
            continue
        dt = pd.read_csv(datapath, index_col=0)
        angle = np.arctan2(dt['ey'], dt['ex']) + np.pi / 2
        e = np.sqrt(dt['ex'] ** 2 + dt['ey'] ** 2)
        f = np.linspace(0.1, 1, 10)
        h_min = 1 - e

        temp = pd.DataFrame(columns=['f', 'h_min', 'ex', 'ey', 'angel', 'e'] + qtag + ['fs'])
        temp['f'] = f
        temp['h_min'] = h_min
        temp['ex'] = dt.ex
        temp['ey'] = dt.ey
        temp['angel'] = np.arctan2(dt['ey'], dt['ex'])
        temp['e'] = np.sqrt(dt['ex'] ** 2 + dt['ey'] ** 2)
        pad0_flow_path = os.path.join(f_path, dr, 'result')
        pad0_flow_paths = listdir(pad0_flow_path, full=True)
        qs = np.zeros((dt.shape[0], 4))
        for n, plp in enumerate(pad0_flow_paths):
            pads = [os.path.join(plp, 'pad{}'.format(i), 'orifice_results', 'CSOrifice0', 'CSOrifice0_q.csv')
                    for i in range(4)]
            qtp = [pd.read_csv(p, index_col=0).iloc[-1]['q'] for p in pads]
            qs[n] = qtp
        temp[qtag] = qs

        fs = np.zeros((dt.shape[0], 1))
        for n, plp in enumerate(pad0_flow_paths):
            pads = [os.path.join(plp, 'pad{}'.format(i), 'pad_res.csv')
                    for i in range(4)]
            ftp = [pd.read_csv(p, index_col=0).iloc[-1]['friction'] for p in pads]
            fs[n] = np.sum(ftp)
        temp['fs'] = fs
        ipt = list(map(lambda x: float(values[x]), ['freq']))
        ipt = [values['kp']] + ipt
        data.loc[data.shape[0]] = [*ipt, temp]
    data.to_pickle(save_path)


def dynamic(f_path, save_path):
    """Execute dynamic."""
    data = pd.DataFrame(dtype=np.float64, columns=['freq', 'kp', 'kd', 'a', 'b', 'kxx', 'kxy', 'kyx', 'kyy',
                                                   'cxx', 'cxy', 'cyx', 'cyy'])
    file_names = listdir(f_path)
    for fn in tqdm.tqdm(file_names):
        data_path = os.path.join(fn, 'result', 'data.pkl')
        share_path = os.path.join(fn, 'share.json5')
        share = read_json5(share_path)
        freq = share['freq']
        kp = share['kp']
        kd = share['kd']
        a = share['a']
        b = share['b']
        with open(data_path, 'rb') as f:
            dat = pickle.load(f)
        temp = [freq, kp, kd, a, b] + list(dat['hkc']['k'].reshape(-1)) + list(dat['hkc']['c'].reshape(-1))
        data.loc[data.shape[0]] = temp
    data.to_csv(save_path, index=False)


def rotor_response(f_path, save_path):
    """Collect rotor-response outputs from a task directory."""
    data = pd.DataFrame(columns=['freq', 'kp', 'kd', 'uxy'])
    file_names = listdir(f_path)
    for fn in tqdm.tqdm(file_names, total=len(file_names)):
        try:
            data_path = os.path.join(fn, 'result', 'rotor_result', 'rotor_yout.csv')
            t_path = os.path.join(fn, 'result', 'rotor_result', 'rotor_t.csv')
            share_path = os.path.join(fn, 'share.json5')
            share = read_json5(share_path)
            freq = share['freq']
            kp = share['kp']
            kd = share['kd']
            columns = ['t', 'uxb0', 'uyb0', 'uxf1', 'uyf1', 'uxb2', 'uyb2']
            uxy = pd.DataFrame(columns=columns)
            dat = pd.read_csv(data_path, index_col=0)
            t = pd.read_csv(t_path, index_col=0)
            uxy['t'] = t['0']
            uxy['uxb0'] = dat[str(4 * 12 + 0)]
            uxy['uyb0'] = dat[str(4 * 12 + 1)]
            uxy['uxf1'] = dat[str(4 * 28 + 0)]
            uxy['uyf1'] = dat[str(4 * 28 + 1)]
            uxy['uxb2'] = dat[str(4 * 34 + 0)]
            uxy['uyb2'] = dat[str(4 * 34 + 1)]
            data.loc[data.shape[0]] = [freq, kp, kd, uxy]
        except:
            print("Error processing file:", fn)
            continue
    data.to_pickle(save_path)


if __name__ == '__main__':
    read_pickles()

