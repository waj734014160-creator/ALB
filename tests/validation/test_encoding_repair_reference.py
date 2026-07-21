"""Regression checks for the repository encoding repair."""

import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).parents[2]
REFERENCE_PATH = ROOT / "refs" / "encoding_repair_reference_v1.json"
SUPERSESSION_PATH = ROOT / "refs" / "encoding_repair_reference_v2.json"


class _NormalizeText(ast.NodeTransformer):
    """Remove text payloads while retaining executable AST structure."""

    def visit_JoinedStr(self, node: ast.JoinedStr) -> ast.Constant:
        return ast.copy_location(ast.Constant(value=""), node)

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        if isinstance(node.value, str):
            return ast.copy_location(ast.Constant(value=""), node)
        return node


def _normalized_ast_sha256(text: str, filename: str) -> str:
    tree = ast.parse(text, filename=filename)
    normalized = _NormalizeText().visit(tree)
    ast.fix_missing_locations(normalized)
    dumped = ast.dump(normalized, include_attributes=False)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


def test_encoding_repair_reference() -> None:
    reference = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    supersession = json.loads(SUPERSESSION_PATH.read_text(encoding="utf-8"))
    superseded_files = supersession["source_files"]
    assert set(superseded_files) == {"ALB/physics/hydraulics/orifice.py"}

    for relative_path, expected in reference["source_files"].items():
        expected = superseded_files.get(relative_path, expected)
        text = (ROOT / relative_path).read_text(encoding="utf-8-sig")
        text.encode("ascii")
        compile(text, relative_path, "exec")
        assert _normalized_ast_sha256(text, relative_path) == expected["normalized_ast_sha256"]

    for relative_path, expected in reference["legacy_config_files"].items():
        text = (ROOT / relative_path).read_bytes().decode("utf-8")
        assert hashlib.sha256(text.encode("utf-8")).hexdigest() == expected["decoded_text_sha256"]
