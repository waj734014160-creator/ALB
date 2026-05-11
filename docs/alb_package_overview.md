# ALB Package Overview

This document is the first-read orientation for the `ALB/` Python package in
`ALB_MAIN`. It describes module responsibilities and the main public interfaces
without changing package layout or import paths.

## Package Boundary

`ALB/` is the stable numerical and system-simulation package. Sibling projects
such as `SURROGATE_TRAIN` should import this package from `../ALB_MAIN` and keep
sampling, training, and experiment records outside the package.

Top-level imports are lazy-exported through `ALB/__init__.py`. Some interfaces
listed below are module-level APIs and should be imported from the owning module.
If a public API is intended for broad top-level use, add it to the export map and
update this document. If an API is experimental or workflow-specific, prefer
importing it from its module path.

## Public Interface Groups

| Interface group | Main entry points | Purpose |
| --- | --- | --- |
| ALB systems | `ALB`, `NodimALB`, `alb2`, `alb2_static`, `alb2_fuzzy`, `nodim_alb` | Build dimensional or nondimensional active lubricated bearing systems from config objects. |
| Config contracts | `ALBConfig`, `NodimALBConfig`, `FPBConfig`, `NodimPadConfig`, `OrificeConfig`, `NodimOrificeConfig`, `PIDConfig`, `FuzzyPIDConfig`, `ThermalConfig`, `GasConfig`, `ALBNetConfig` | Dataclass-style configuration objects used by builders, tasks, and surrogate wrappers. |
| Bearing and film models | `HydrostaticBearing`, `NodimHydrostaticBearing`, `MultiPad`, `four_pads_bearing`, `four_pads_bearings`, `NodimNewtonFilm`, `GasBearing` | Core oil-film, gas-film, hydrostatic-pad, and multi-pad bearing models. |
| Thermal and nondimensional helpers | `ThermalHydroBearing`, `NodimThermalHydroBearing`, `SkfemThermalModel`, `SkfemThermalModelNondim`, `ThermalNondimScales`, `FilmNondimScales` | Thermal-hydrodynamic coupling and dimensional/nondimensional scale conversion. |
| Control and valves | `PID`, `FuzzyPID`, `ALB.orifice.CSOrifice`, `NodimCSOrifice`, `ALB.servovalve.moog_servovalve`, `ALB.servovalve.static_sv` | Controller, servovalve, and orifice components used inside ALB assemblies. |
| Rotor coupling | `ALB.rotor.RossRotor`, `ALB.couple.RotorBearingCouple`, `ALB.couple.RsRotorBearingCouple`, `ALB.orbit.EllipseTrack`, `ALB.orbit.BearingForceTrack` | Rotor-bearing coupling, orbit generation, and time-response workflows. |
| ALBNN surrogate support | `ALBNN`, `ALB.nn.ALBNet`, `albnn`, `ALB.nn.thermal_albnet`, `ALB.alb.ALBNNAgent`, `ALB.alb.FakeOf` | Packaged neural force models and ALB shell replacements for local validation and downstream simulation. |
| Remote operation helpers | `ALB.remote.albnn_start`, `ALB.remote.albnn_status`, `ALB.remote.albnn_queue`, `ALB.remote.monitor`, `ALB.remote.transport` | Stable SSH, PowerShell, Task Scheduler, launch, queue, and monitor helpers used by `SURROGATE_TRAIN/run/remote` wrappers. |
| Tasks and results | `ALB.task.*`, `DataFrameResult`, `SaveTreeNode`, `read_json5`, `recognize_kc` | Reusable batch entrypoints, result storage helpers, config readers, and signal-analysis utilities. |

## Module Map

| Area | Files | Notes |
| --- | --- | --- |
| Package exports | `__init__.py` | Lazy top-level exports. Update this when promoting a module API to public package API. |
| System assembly | `alb.py` | ALB/NodimALB classes, builders, linear and neural core-replacement agents. |
| Configuration | `config.py` | Dataclass config contracts for film, gas, thermal, ALB, servovalve, PID, and ALBNN workflows. |
| Numerical foundation | `base.py`, `mesh.py`, `boundary.py`, `gauss.py`, `matrix/` | Node/element abstractions, mesh generation, boundary assembly, and low-level matrix/iteration utilities. |
| Film and bearing solvers | `film.py`, `bearing.py`, `orifice.py`, `gas.py`, `damping.py` | Reynolds film solvers, hydrostatic/gas bearings, orifice flow, multi-pad assemblies, and adaptive damping. |
| Thermal and nondimensional code | `thermal.py`, `nondim.py` | Thermal grids, viscosity-coupled films, thermal solvers, and scale objects. |
| Control and dynamics | `controller.py`, `servovalve.py`, `lti.py`, `rotor.py`, `orbit.py`, `couple.py` | Controllers, servovalves, state-space utilities, rotor models, orbit definitions, and coupling systems. |
| Surrogate models | `nn.py` | ALBNN architectures, feature augmentation, target transforms, training helpers, and packaged inference loaders. |
| Remote helpers | `remote/` | Shared remote operation implementation. Keep wrapper compatibility scripts in `SURROGATE_TRAIN/run/remote`. |
| Outputs and utilities | `results.py`, `postprocess.py`, `plot.py`, `logger.py`, `tool.py`, `task.py` | Results, plotting, logging, broad utility functions, and legacy reusable task entrypoints. |

## Interface Notes

- Prefer config objects over ad hoc dictionaries when constructing ALB systems.
- Use `miu` for viscosity and `lambda_value` for the nondimensional bearing
  parameter in new code and documentation.
- `ALB.nn` expects the 12 base ALBNN inputs
  `ex, ey, vx, vy, sx, sy, lambda_value, beta_nondim, lr, cq0, cq1, cq2` and
  outputs `fx, fy` for the current thermal surrogate workflow.
- `ALB.nn.albnn_augment_frame(..., feature_set="sqrt28")` keeps the 12 base
  inputs and adds 12 `sqrt_abs_*` features plus four norm/ratio features for
  the current 28-input thermal ALBNN experiment.
- `ALBNNAgent` and `FakeOf` live in `ALB.alb` because they replace only the pad
  force core inside an ALB shell; use `ALB.nn.albnn` to load packaged models.
- `ALB/remote` is library code. User-facing queue configs and compatibility
  command wrappers belong in `../SURROGATE_TRAIN/run/remote`.
- Do not rename `ALB/matrix/dynmaic.py` without a compatibility plan; the
  misspelling is part of existing imports.
