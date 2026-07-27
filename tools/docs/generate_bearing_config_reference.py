"""Generate and validate the ALB bearing configuration reference."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from ALB.api._config_fields import (  # noqa: E402
    DIMENSIONAL_FILM_FIELDS,
    GAS_ONLY_FILM_FIELDS,
    NONDIMENSIONAL_FILM_FIELDS,
)

SOURCE_PATH = REPOSITORY_ROOT / "docs/api/bearing_config_reference_source.md"
OUTPUT_PATH = REPOSITORY_ROOT / "docs/api/bearing_config_reference.md"


_GROUPS = (
    ("量纲液膜", DIMENSIONAL_FILM_FIELDS),
    ("无量纲液膜", NONDIMENSIONAL_FILM_FIELDS),
    ("气膜附加", GAS_ONLY_FILM_FIELDS),
)


def _validate_metadata() -> None:
    """Reject incomplete or contradictory canonical field metadata."""

    allowed_selectors = {
        "liquid_film:dimensional",
        "liquid_film:nondimensional",
        "active_lubricated:dimensional",
        "active_lubricated:nondimensional",
        "gas_film:dimensional",
    }
    for group_name, fields in _GROUPS:
        if len(fields) != len(set(fields)):
            raise ValueError(f"duplicate public field in {group_name}")
        for name, field in fields.items():
            if not field.native_name or not field.unit or not field.description:
                raise ValueError(f"incomplete metadata for {group_name}.{name}")
            unknown = set(field.applicability) - allowed_selectors
            if unknown:
                raise ValueError(
                    f"invalid applicability for {group_name}.{name}: {sorted(unknown)}"
                )
    texture = GAS_ONLY_FILM_FIELDS["texture_type"]
    if texture.choices != (1, 2, 3):
        raise ValueError("gas texture_type choices must be exactly 1, 2, 3")
    for name in ("texture_start_theta_index", "texture_start_axial_index"):
        if GAS_ONLY_FILM_FIELDS[name].constraint != ">= 1":
            raise ValueError(f"{name} must document one-based indexing")


def build_reference() -> str:
    """Return the validated UTF-8 reference content."""

    _validate_metadata()
    content = SOURCE_PATH.read_text(encoding="utf-8")
    if not content.endswith("\n"):
        content += "\n"
    return content


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    reference = build_reference()
    if args.check:
        if not OUTPUT_PATH.is_file() or OUTPUT_PATH.read_text(encoding="utf-8") != reference:
            print(
                "bearing configuration reference is stale; run "
                "tools/docs/generate_bearing_config_reference.py"
            )
            return 1
        print("bearing configuration reference is current")
        return 0
    OUTPUT_PATH.write_text(reference, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
