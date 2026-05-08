# -- coding: utf-8 --
import os
from typing import Dict, List, Union

import numpy as np
import pandas as pd
import plotly
from ross import Rotor, TimeResponseResults


class BaseResult:
    def save(self, path=None):
        raise NotImplementedError


class DataFrameResult(BaseResult):
    """
    Translated documentation.
    """

    def __init__(self, result: Dict[str, pd.DataFrame]):
        """
        Translated documentation.
        """
        self.result = result
        self._check_result_valve()

    def __getitem__(self, item):
        return self.result[item]

    def save(self, path=None):
        """
        Translated documentation.
        Translated documentation.
        """
        if path is None:
            path = "Results"
        if not os.path.exists(path):
            os.makedirs(path)
        for key, value in self.result.items():
            value.to_csv(os.path.join(path, key + ".csv"))

    def _check_result_valve(self):
        """
        Translated documentation.
        """
        for key, value in self.result.items():
            if not isinstance(value, pd.DataFrame):
                print("error valve key:{}".format(key))
                raise Exception("鏁版嵁鏍煎紡閿欒锛屽簲涓簆d.DataFrame鏍煎紡")


class NpyResult(BaseResult):
    """
    Translated documentation.
    """

    def __init__(self, result: Dict[str, np.ndarray]):
        """
        Translated documentation.
        """
        self.result = result
        self._check_result_valve()

    def __getitem__(self, item):
        return self.result[item]

    def save(self, path=None):
        """
        Translated documentation.
        Translated documentation.
        """
        if path is None:
            path = "Results"
        if not os.path.exists(path):
            os.makedirs(path)
        for key, value in self.result.items():
            save_path = os.path.join(path, key + ".npy")
            np.save(save_path, value)

    def _check_result_valve(self):
        """
        Translated documentation.
        """
        for key, value in self.result.items():
            if not isinstance(value, np.ndarray):
                print("error valve key:{}".format(key))
                raise Exception("鏁版嵁鏍煎紡閿欒锛屽簲涓簄p.ndarray鏍煎紡")


class RossRotorResult(BaseResult):
    def __init__(
        self,
        t: Union[List, np.ndarray],
        xout: Union[List, np.ndarray],
        yout: Union[List, np.ndarray],
        rotor_result: TimeResponseResults,
        rotor: Rotor,
        name: str,
    ):
        self.t = t
        self.xout = xout
        self.yout = yout
        self.rotor_result = rotor_result
        self.rotor = rotor
        self.name = name

    def save(self, path=None):
        if path is None:
            path = "Results"
        if not os.path.exists(path):
            os.makedirs(path)
        if self.name is None:
            self.name = "rotor"
        t = pd.DataFrame(self.t)
        xout = pd.DataFrame(self.xout)
        yout = pd.DataFrame(self.yout)
        plotly.offline.plot(
            self.rotor_result.plot_3d(),
            filename=os.path.join(path, self.name + "_plot_3d.html"),
            auto_open=False,
        )
        plotly.offline.plot(
            self.rotor.plot_rotor(),
            filename=os.path.join(path, self.name + ".html"),
            auto_open=False,
        )
        self.rotor_result.save(os.path.join(path, "rotor_time_respone.toml"))
        res = DataFrameResult(
            {self.name + "_t": t, self.name + "_xout": xout, self.name + "_yout": yout}
        )
        res.save(path)


class SaveTreeNode:
    """
    Translated documentation.
    """

    def __init__(self, path, data, children: list = None):
        if children is None:
            children = []
        self.path = path
        self.data = data
        self.children = []
        self.add_children(children)
        self.parent = None

    def add_child(self, child):
        child.parent = self
        self.children.append(child)

    def add_children(self, children):
        for child in children:
            self.add_child(child)

    def save_to_file(self, parent_path=None, **kwargs):
        """
        Translated documentation.
        """
        root_path = kwargs.get("root_path", None)
        if root_path is not None:
            self.path = root_path
        # Translated comment.
        if parent_path is None:
            parent_path = self.path
        if parent_path is None or self.path is None:
            raise Exception("未给定保存路径")
        else:
            if self.path is None:
                parent_path = os.path.join(parent_path)
            else:
                parent_path = os.path.join(parent_path, self.path)
        if not os.path.exists(parent_path):
            os.makedirs(parent_path)
        if hasattr(self.data, "save"):
            (self.data.save(parent_path),)
        if isinstance(self.data, list):
            for dt in self.data:
                (dt.save(parent_path),)
        # Translated comment.
        if isinstance(self.children, list):
            for child in self.children:
                child.save_to_file(parent_path)

    def get_dir(self):
        """
        Translated documentation.
        """
        # Translated comment.
        if len(self.children) == 0:
            return {self.path: None}
        else:
            # Translated comment.
            dir = {}
            for child in self.children:
                dir.update(child.get_dir())
            return {self.path: dir}

    def return_root(self):
        """
        Translated documentation.
        """
        if self.parent is None:
            return self
        else:
            return self.parent.return_root()

    def load_file(self, root_path):
        """
        Translated documentation.
        """
        root_path = os.path.normpath(root_path)
        if not os.path.exists(root_path):
            raise Exception("路径不存在")
        if not os.path.isdir(root_path):
            raise Exception("输入的路径不是文件夹")
        # Translated comment.
        file_list = os.listdir(root_path)
        # Translated comment.
        datas = {}
        children = []
        node_path = root_path.split(os.sep)[-1]
        for file in file_list:
            file_path = os.path.join(root_path, file)
            if os.path.isdir(file_path):
                children.append(self.load_file(file_path))
            elif file_path.endswith(".csv"):
                # Translated comment.
                data = pd.read_csv(file_path, index_col=0)
                datas[file[:-4]] = data
        datas = DataFrameResult(datas)
        parent_node = SaveTreeNode(node_path, datas, children)
        return parent_node

    def save_to_pickle(self, path, name):
        """
        Translated documentation.
        """
        import pickle

        path = os.path.normpath(path)
        if not os.path.exists(path):
            os.makedirs(path)
        path = os.path.join(path, name)
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load_pickle(path):
        """
        Translated documentation.
        """
        import pickle

        path = os.path.normpath(path)
        if not os.path.exists(path):
            raise Exception("路径不存在")
        if not os.path.isfile(path):
            raise Exception("输入的路径不是文件夹")
        with open(path, "rb") as f:
            node = pickle.load(f)
        return node
