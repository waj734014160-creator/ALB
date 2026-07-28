# 安装与能力组件

ALB 的核心安装包含配置、公共 facade、基础数值依赖和 JSON5 读取。按实际任务增加 optional extra，不必为只做液膜计算的环境安装 PyTorch 或 ROSS。

=== "核心"

    ```powershell
    E:/Anaconda2023/envs/ALB/python.exe -m pip install re-alb
    ```

=== "液膜 / 气膜"

    ```powershell
    E:/Anaconda2023/envs/ALB/python.exe -m pip install "re-alb[film]"
    ```

=== "控制"

    ```powershell
    E:/Anaconda2023/envs/ALB/python.exe -m pip install "re-alb[control]"
    ```

=== "转子动力学"

    ```powershell
    E:/Anaconda2023/envs/ALB/python.exe -m pip install "re-alb[dynamics]"
    ```

=== "ALBNN 代理模型"

    ```powershell
    E:/Anaconda2023/envs/ALB/python.exe -m pip install "re-alb[surrogate]"
    ```

=== "全部能力"

    ```powershell
    E:/Anaconda2023/envs/ALB/python.exe -m pip install "re-alb[all]"
    ```

## 检查当前解释器

```powershell
E:/Anaconda2023/envs/ALB/python.exe -c "import ALB; print(ALB.__version__, ALB.__file__)"
```

输出中的版本应与当前项目版本一致，路径应指向预期环境。兄弟项目应安装 wheel 或 editable package，不要复制 `ALB/` 或临时修改 `sys.path`。

!!! warning "可选依赖"
    高级 namespace 会在缺少依赖时给出对应 extra。先按报错中的能力名称安装，不要一次性修改内部 import 路径。

下一步：[运行第一个轴承计算](first-bearing.md)。
