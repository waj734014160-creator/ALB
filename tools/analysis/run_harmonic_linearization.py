"""Compute ALB harmonic coefficients from an explicit configuration and point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import ALB


def main() -> None:
    """Compute one requested frequency and persist its immutable analysis result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="ALB bearing JSON5 configuration")
    parser.add_argument("--operating-point", type=float, nargs=2, required=True, metavar=("X_M", "Y_M"))
    parser.add_argument("--frequency-hz", type=float, required=True, help="Positive excitation frequency in Hz")
    parser.add_argument("--spool", type=float, nargs=2, metavar=("SX", "SY"), help="Normalized base spool for external_spool control")
    parser.add_argument("--output", type=Path, required=True, help="New result directory")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("--output must be a new directory")
    bearing = ALB.bearing_from_file(args.config)
    result = bearing.analysis.harmonic_linearize(
        operating_point=args.operating_point,
        excitation_frequency=args.frequency_hz,
        spool=args.spool,
    )
    manifest = result.write(args.output)
    print(json.dumps({
        "output": str(args.output.resolve()),
        "frequency_hz": args.frequency_hz,
        "stiffness_N_per_m": result.values["stiffness"].tolist(),
        "damping_N_s_per_m": result.values["damping"].tolist(),
        "residual": result.convergence.residual,
        "artifacts": len(manifest.artifacts),
    }, indent=2))


if __name__ == "__main__":
    main()
