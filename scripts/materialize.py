"""scripts/materialize: the common spine e-jev runs on — the listed files of e-arkhetypo's `projects/python/common`, copied
with their imports rerooted `e_infra.<section>` → `e_jev.<section>` by libcst, every result re-parsed before it is written.

    uv run python scripts/materialize.py [--check] [--common PATH]

e-jev takes a closed list, not whole sections: its own ports, providers, engines and ops live beside the copies, and a
section copied whole would carry postgres, redis, auth and MCP drivers the service never opens. The copies are tracked;
`--check` rewrites into memory and fails on any drift, so `make common-check` and `make common` share one path.
`infra/config/infra.py` and `infra/settings.py` are e-jev's own (the shared homes): common's carry crypto it never signs with.
"""

import argparse
import ast
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import libcst as cst

ROOT: Final[Path] = Path(__file__).resolve().parents[1]
PACKAGE: Final[str] = "e_jev"
COMMON: Final[Path] = ROOT.parent / "e-arkhetypo" / "projects" / "python" / "common"
SECTIONS: Final[frozenset[str]] = frozenset({"infra", "ops", "ports", "providers", "engines", "processors"})
FILES: Final[tuple[str, ...]] = (
    "infra/config/base.py",
    "infra/errors.py",
    "infra/logger.py",
    "infra/proxy.py",
    "ports/provider.py",
)


##### REWRITE #####
def _parts(name: cst.BaseExpression) -> list[str] | None:
    """A dotted name as its segments; None when the node is not a plain dotted expression."""
    match name:
        case cst.Name(value=only):
            return [only]
        case cst.Attribute(value=inner, attr=cst.Name(value=tail)):
            return None if (prefix := _parts(inner)) is None else [*prefix, tail]
        case _:
            return None


def _dotted(parts: Sequence[str]) -> cst.BaseExpression:
    """The left-nested libcst attribute chain spelling `parts`."""
    match parts:
        case [only]:
            return cst.Name(only)
        case [*init, last]:
            return cst.Attribute(value=_dotted(init), attr=cst.Name(last))
        case _:
            msg = "empty dotted name"
            raise ValueError(msg)


def _reroot(name: cst.BaseExpression) -> cst.BaseExpression:
    """`e_infra.infra.x` → `e_jev.infra.x`; anything outside a section is returned untouched."""
    parts = _parts(name)
    hit = parts is not None and len(parts) > 1 and parts[0] == "e_infra" and parts[1] in SECTIONS
    return _dotted([PACKAGE, *parts[1:]]) if hit and parts else name


class _Reroot(cst.CSTTransformer):
    """Import statements only: docstrings and comments keep naming the source of truth verbatim."""

    def leave_Import(self, _original_node: cst.Import, updated_node: cst.Import) -> cst.Import:  # noqa: N802 — libcst dispatch
        match updated_node.names:
            case cst.ImportStar():
                return updated_node
            case aliases:
                return updated_node.with_changes(names=[alias.with_changes(name=_reroot(alias.name)) for alias in aliases])

    def leave_ImportFrom(self, _original_node: cst.ImportFrom, updated_node: cst.ImportFrom) -> cst.ImportFrom:  # noqa: N802
        match updated_node.module:
            case None:
                return updated_node
            case module:
                return updated_node.with_changes(module=_reroot(module))


def rewrite(text: str, path: str) -> str:
    """One file rewritten structurally, then validated: parseable, free of `e_infra` imports."""
    out = cst.parse_module(text).visit(_Reroot()).code
    leftovers = [
        node.lineno
        for node in ast.walk(ast.parse(out, filename=path))
        if isinstance(node, ast.ImportFrom | ast.Import)
        and any(
            name.split(".")[0] == "e_infra"
            for name in ([node.module or ""] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names])
        )
    ]
    match leftovers:
        case []:
            return out
        case lines:
            msg = f"{path}: e_infra imports survive the rewrite at lines {lines}"
            raise SystemExit(msg)


##### RUN #####
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail on drift, write nothing")
    parser.add_argument("--common", type=Path, default=COMMON, help="projects/python/common of an e-arkhetypo checkout")
    args = parser.parse_args()
    source = args.common / "src" / "e_infra"
    target = ROOT / "src" / PACKAGE
    fresh = {rel: rewrite((source / rel).read_text(), rel) for rel in FILES}
    drift = [rel for rel, text in fresh.items() if not (target / rel).is_file() or (target / rel).read_text() != text]
    match args.check, drift:
        case True, []:
            print("✓ common in sync")
        case True, files:
            sys.exit(f"common drifted: {files} — run `make common`")
        case False, files:
            for rel in files:
                (target / rel).parent.mkdir(parents=True, exist_ok=True)
                (target / rel).write_text(fresh[rel])
            print(f"materialized {len(files)} file(s) from {source}")


if __name__ == "__main__":
    main()
