"""Shared validation helpers. Exit codes: PASS/N/A=0, FAIL=1, INCOMPLETE=2."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


class Incomplete(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise Incomplete(message)


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Incomplete(f"{path}: {exc}") from exc


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def number(value, name, minimum=None, maximum=None):
    require(isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value), f"{name} must be a finite number")
    require(minimum is None or value >= minimum, f"{name} must be >= {minimum}")
    require(maximum is None or value <= maximum, f"{name} must be <= {maximum}")
    return float(value)


def within(root, name):
    root = Path(root).resolve()
    require(isinstance(name, str) and bool(name), "file path is required")
    path = (root / name).resolve()
    require(path.is_relative_to(root), f"path outside project: {name}")
    return path


def artifact(root, record):
    require(isinstance(record, dict), "artifact must be an object")
    path = within(root, record.get("file"))
    require(path.is_file(), f"missing artifact: {path}")
    require(record.get("sha256") == sha256(path), f"hash mismatch: {path}")
    return path


def finish(status, message):
    print(f"[{status}] {message}")
    return {"PASS": 0, "FAIL": 1, "INCOMPLETE": 2, "NOT_APPLICABLE": 0}[status]


def run(check):
    try:
        return check()
    except (Incomplete, OSError, ValueError, KeyError, TypeError, IndexError, AttributeError, SyntaxError) as exc:
        return finish("INCOMPLETE", str(exc))


def project(root):
    doc = read_json(Path(root) / "spec/project.json")
    require(isinstance(doc, dict) and doc.get("schema_version") == 1, "project schema_version must be 1")
    require(doc.get("level") in ("quick", "standard", "strict"), "invalid verification level")
    require(isinstance(doc.get("official_code"), bool), "official_code must be boolean")
    require(doc.get("reproduction_mode") in ("paper", "independent", "author"), "reproduction_mode must be paper/independent/author")
    require(doc["reproduction_mode"] != "author" or doc["official_code"], "author mode requires official_code=true")
    require(doc.get("stage") in ("planning", "calibrated", "final"), "invalid Spec stage")
    for key in ("title", "source", "domain", "environment", "independence"):
        require(bool(doc.get(key)), f"project.{key} is required")
    targets = doc.get("targets")
    require(isinstance(targets, list) and targets, "targets must be nonempty")
    ids = set()
    for target in targets:
        require(isinstance(target, dict), "target must be an object")
        tid = target.get("id")
        require(isinstance(tid, str) and tid and tid not in ids, "target id must be nonempty and unique")
        ids.add(tid)
        require(target.get("type") in ("curve", "scalar", "table", "map"), f"{tid}: invalid target type")
        require(target.get("mode") in ("quantitative", "qualitative"), f"{tid}: invalid mode")
        require(target.get("validation_subject") in ("paper_result", "author_implementation", "benchmark"), f"{tid}: invalid validation_subject")
        require(bool(target.get("criterion")), f"{tid}: criterion is required")
        checks = target.get("checks")
        require(isinstance(checks, dict), f"{tid}: checks must be an object")
        for name in ("loss", "visual", "effect"):
            entry = checks.get(name)
            require(isinstance(entry, dict) and isinstance(entry.get("enabled"), bool), f"{tid}: invalid {name} check")
            if entry["enabled"]:
                within(root, entry.get("config"))
            else:
                require(bool(entry.get("reason")), f"{tid}: disabled {name} needs reason")
        require(checks["loss"]["enabled"], f"{tid}: a numerical validation protocol is required")
    return doc


def target(root, tid):
    for item in project(root)["targets"]:
        if item["id"] == tid:
            return item
    raise Incomplete(f"unknown target: {tid}")


def config_for(root, tid, name):
    entry = target(root, tid)["checks"][name]
    if not entry["enabled"]:
        return None
    return read_json(within(root, entry["config"]))
