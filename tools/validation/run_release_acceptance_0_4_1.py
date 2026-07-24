"""Run detached, reproducible ALB 0.4.1 source and wheel acceptance."""

from __future__ import annotations

from tools.validation import run_release_acceptance_0_4 as _base


_base.VERSION = "0.4.1"
_base.FEATURE_MANIFEST = (
    _base.ROOT / "tools/validation/release_feature_manifest_0_4_1.json"
)
_base.FEATURE_ID_PREFIX = "V4P-"
_base.REPORT_SCHEMA = "alb.release-acceptance.v0.4.1"
_base.RUN_SLUG = "alb_0_4_1"
_base.FORBIDDEN_SOURCE_TOKENS = (
    *_base.FORBIDDEN_SOURCE_TOKENS,
    "TiltingPadHydrodynamicPad",
    "tilting_pads_bearing",
    "tilting_pads_bearings",
    "solve_tilting_pad_equilibrium",
)


run_acceptance = _base.run_acceptance


def main() -> int:
    """Execute the 0.4.1 acceptance runner."""

    return _base.main()


if __name__ == "__main__":
    raise SystemExit(main())
