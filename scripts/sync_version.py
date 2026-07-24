#!/usr/bin/env python3
"""Synchronize auvide's release version across package metadata files."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[a-zA-Z0-9.+-]*)$")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="fail when metadata differs from VERSION")
    action.add_argument("--set", metavar="VERSION", help="set VERSION and every metadata consumer")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def validate_version(value: str) -> str:
    version = value.strip()
    if not VERSION_RE.fullmatch(version):
        raise ValueError(f"invalid release version: {value!r}")
    return version


def version_path(root: Path) -> Path:
    return root / "VERSION"


def read_version(root: Path) -> str:
    try:
        return validate_version(version_path(root).read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"missing canonical version file: {version_path(root)}") from error


def read_toml_version(path: Path, table: str) -> str:
    with path.open("rb") as file:
        data = tomllib.load(file)
    try:
        return str(data[table]["version"])
    except KeyError as error:
        raise ValueError(f"missing [{table}].version in {path}") from error


def read_json_version(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    try:
        return str(data["version"])
    except KeyError as error:
        raise ValueError(f"missing version in {path}") from error


def consumers(root: Path) -> list[tuple[Path, str, str]]:
    return [
        (root / "engine" / "pyproject.toml", "toml", "project"),
        (root / "desktop" / "package.json", "json", ""),
        (root / "desktop" / "src-tauri" / "Cargo.toml", "toml", "package"),
        (root / "desktop" / "src-tauri" / "tauri.conf.json", "json", ""),
    ]


def observed_versions(root: Path) -> dict[Path, str]:
    observed: dict[Path, str] = {}
    for path, kind, table in consumers(root):
        observed[path] = read_json_version(path) if kind == "json" else read_toml_version(path, table)
    return observed


def atomic_write(path: Path, content: str) -> None:
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, newline="\n"
    ) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, path)


def rewrite_toml_version(path: Path, table: str, version: str) -> None:
    # tomllib validates the file before this narrowly scoped rewrite preserves
    # comments and formatting that a TOML serializer would otherwise discard.
    read_toml_version(path, table)
    lines = path.read_text(encoding="utf-8").splitlines()
    current_table = ""
    replacement_count = 0
    for index, line in enumerate(lines):
        table_match = re.match(r"^\s*\[([^]]+)]\s*$", line)
        if table_match:
            current_table = table_match.group(1)
            continue
        if current_table == table and re.match(r"^\s*version\s*=", line):
            lines[index] = f'version = "{version}"'
            replacement_count += 1
    if replacement_count != 1:
        raise ValueError(f"expected one [{table}].version in {path}, found {replacement_count}")
    atomic_write(path, "\n".join(lines) + "\n")


def rewrite_json_version(path: Path, version: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "version" not in data:
        raise ValueError(f"missing version in {path}")
    data["version"] = version
    atomic_write(path, json.dumps(data, indent=2) + "\n")


def set_version(root: Path, version: str) -> None:
    version = validate_version(version)
    # Validate every target before writing any file.
    observed_versions(root)
    for path, kind, table in consumers(root):
        if kind == "json":
            rewrite_json_version(path, version)
        else:
            rewrite_toml_version(path, table, version)
    atomic_write(version_path(root), version + "\n")


def check_version(root: Path, expected: str) -> list[str]:
    errors = []
    for path, actual in observed_versions(root).items():
        if actual != expected:
            errors.append(f"{path.relative_to(root).as_posix()}: {actual} (expected {expected})")
    return errors


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    try:
        if args.set:
            set_version(root, args.set)
        expected = read_version(root)
        errors = check_version(root, expected)
    except (OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        print(f"version sync error: {error}", file=sys.stderr)
        return 1

    if errors:
        print("version drift detected:", file=sys.stderr)
        print("\n".join(f"  {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"versions synchronized at {expected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
