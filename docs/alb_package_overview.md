# ALB Package Overview

## Document Role

- Role: Stable package orientation.
- Purpose: Describe the ALB package module map, public interface groups, and
  package ownership boundaries.
- Allowed updates: public API/module ownership changes, package-boundary notes,
  and first-read package orientation.
- Forbidden updates: experiment runtime state, daily maintenance history,
  training progress, and raw evidence.
- Update cadence: when public APIs, module ownership, or package boundaries
  change.
- Source of truth / Related docs:
  `docs/daily_maintenance/daily_doc_update_index.md`.

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
| ALBNN surrogate support | `ALBNN`, `ALB.nn.ALBNNForceExpert`, `ALB.nn.ALBNet`, `albnn`, `ALB.nn.thermal_albnet`, `ALB.alb.ALBNNAgent`, `ALB.alb.FakeOf` | Packaged neural force models and ALB shell replacements for local validation and downstream simulation. |
| Remote operation helpers | `ALB.remote.job`, `ALB.remote.albnn_start`, `ALB.remote.albnn_status`, `ALB.remote.albnn_queue`, `ALB.remote.monitor`, `ALB.remote.transport` | Stable SSH, PowerShell, Task Scheduler, launch, queue, and monitor helpers used by `SURROGATE_TRAIN/run/remote` wrappers. |
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
- Polar ALBNN experiments may use derived input columns
  `sin_theta, cos_theta, r` in place of `ex, ey`, and may train the target
  contract `sin_f_theta, cos_f_theta, force_norm`; packaged inference decodes
  that target contract back to `fx, fy`. In this polar contract, the angular
  sine/cosine columns may be passed through the minmax scaler unchanged while
  radius, force norm, and physical parameters continue to be scaled.
- Full-polar ALBNN experiments may also represent the velocity and servovalve
  vectors as `sin_v_theta, cos_v_theta, v_norm` and
  `sin_s_theta, cos_s_theta, s_norm`. These angle columns can be passed through
  minmax unchanged for 15-input experiments that use no additional feature
  augmentation.
- Force-polar ALBNN targets may optionally apply a reversible signed `log1p`
  transform only to `force_norm` before minmax scaling, while keeping
  `sin_f_theta, cos_f_theta` as angular pass-through target columns.
- Cartesian ALBNN force targets may use `IdentityTargetScaler` under an `asinh`
  target transform when the transformed force is already in a suitable
  numerical range and should not be minmax- or standard-scaled.
- Force-expert ALBNN packages use `ALB.nn.ALBNNForceExpert` through
  `ALB.nn.albnn` metadata dispatch. Each expert emits two force-code channels
  and a raw router logit; deployed inference uses hard or confidence-gated
  adjacent expert blending and returns ordinary `fx, fy`.
- Hybrid ALBNN scaler experiments may standardize `ex, ey, vx, vy, sx, sy`
  while standardizing then minmax-scaling the remaining input columns; matching
  force-target experiments may standardize then minmax-scale `fx, fy` while
  keeping expert router logits unscaled.
- Direct-parameter hybrid scaler experiments may standardize
  `ex, ey, vx, vy, sx, sy`, directly minmax-scale scalar parameter and ratio
  columns such as `lambda_over_lr`, and standardize cartesian `fx, fy` targets.
- Scaled-EVS MLP experiments may first minmax-scale the 12 base inputs to
  `[0, 1]`, then append `evs_geom`, `edotv`, `edots`, and `sdotv` computed from
  that scaled input space. Those appended interaction features are not scaled a
  second time.
- ALBNN MLP checkpoints may enable hidden-layer LayerNorm. The checkpoint field
  `use_layer_norm` controls whether `ALB.nn.Net` inserts `LayerNorm` between
  each hidden `Linear` layer and its activation during packaged inference.
- Polar force-expert experiments may replace `ex/ey`, `vx/vy`, and `sx/sy`
  with each vector's sine, cosine, and norm, then add `e_dot_v`, `e_dot_s`,
  and `s_dot_v` interaction features. In this contract, angle columns pass
  through scaling unchanged, norms and dot products are standardized, scalar
  parameters are standardized then minmax-scaled, and each expert may emit
  `sin_f_theta, cos_f_theta, force_norm, router_logit` before packaged
  inference decodes the final blended output back to `fx, fy`.
- `ALB.nn.albnn_augment_frame(..., feature_set="sqrt_abs")` keeps the selected
  base input contract and appends only `sqrt_abs_<column>` features, without
  adding norm, ratio, dot, cross, or log-combination features.
- `ALB.nn.albnn_augment_frame(..., feature_set="polar37")` is for the
  full-polar 15-input contract. It appends `sqrt_abs_*` for each base input and
  seven targeted interaction features:
  `lambda_over_lr`, `sqrt_lambda_over_lr`, `log_lr`, `v_radial`,
  `v_tangential`, `s_radial`, and `s_tangential`.
- `ALB.nn.albnn_augment_frame(..., feature_set="sqrt28")` keeps the 12 base
  inputs and adds 12 `sqrt_abs_*` features plus four norm/ratio features for
  the current 28-input thermal ALBNN experiment.
- `ALB.nn.albnn_augment_frame(..., feature_set="sqrt34")` keeps the 12 base
  inputs and adds 12 `sqrt_abs_*` features, `e_norm`, `v_norm`, `s_norm`,
  their square-root companions, and four `lambda_value / lr` or `lr`
  ratio/log companions for 34-input thermal ALBNN experiments.
- `ALBNNAgent` and `FakeOf` live in `ALB.alb` because they replace only the pad
  force core inside an ALB shell; use `ALB.nn.albnn` to load packaged models.
- `ALB/remote` is library code. Use `ALB.remote.job` for new generic remote
  launch, monitor, and conditional queue workflows. Keep user-facing queue
  configs and compatibility command wrappers in `../SURROGATE_TRAIN/run/remote`.
- Run registration is repository workflow tooling, not ALB numerical package
  code. Keep the reusable registration script in `scripts/run_registry.py`, the
  human-facing run-number and placement rules in `docs/run_index.md`, and
  per-project registration facts in each owning project's `docs/run_registry.jsonl`.
- Do not rename `ALB/matrix/dynmaic.py` without a compatibility plan; the
  misspelling is part of existing imports.
