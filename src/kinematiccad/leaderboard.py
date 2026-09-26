"""Manifest-based denominators: missing, errored and invalid attempts score zero."""

from __future__ import annotations

import math
from pathlib import Path

from .io import digest, read_json


def wilson(successes: int, total: int):
    if total == 0:
        return [0.0, 1.0]
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [max(0, centre - radius), min(1, centre + radius)]


def rank(suite: dict, batches: list[Path], *, allow_local=False):
    expected = {t["id"]: digest(t) for t in suite["tasks"]}
    if len(expected) != len(suite["tasks"]) or not expected:
        raise ValueError("Suite must contain unique tasks")
    rows = []
    seen = set()
    cohort = None
    for batch in batches:
        manifest = read_json(batch / "batch.json")
        if manifest["suite_sha256"] != digest(suite):
            raise ValueError("Cannot rank different suites together")
        label = manifest["model_label"]
        if label in seen:
            raise ValueError("Duplicate model label: aggregate repeated samples explicitly")
        seen.add(label)
        successes = 0
        quality = 0.0
        failures = {}
        for task_id, task_hash in expected.items():
            root = batch / task_id
            try:
                run = read_json(root / "run.json")
                report = read_json(root / "evaluation" / "result.json")
                if run["task_sha256"] != task_hash:
                    raise ValueError("Task hash mismatch")
                if not run["sandbox"]["rankable"] and not allow_local:
                    raise ValueError("Unsafe local runs are excluded from official ranking")
                current = (run["sandbox"].get("image_id"), digest(report.get("environment", {})))
                if report.get("environment"):
                    if cohort is None:
                        cohort = current
                    elif current != cohort:
                        raise ValueError("Mixed runtime cohorts; produce separate leaderboards")
                # Verify saved result integrity (integrity, not authenticity).
                if "result_sha256" in report:
                    check = {k: v for k, v in report.items() if k != "result_sha256"}
                    if digest(check) != report["result_sha256"]:
                        raise ValueError("Result integrity mismatch")
                passed = report.get("passed") is True and report.get("status") == "passed"
                if passed and (
                    report.get("task_sha256") != task_hash
                    or not report.get("trials")
                    or not all(t.get("passed") is True for t in report["trials"])
                ):
                    raise ValueError("Inconsistent pass verdict")
                successes += int(passed)
                score = float(report.get("score", 0))
                if not math.isfinite(score) or not 0 <= score <= 1:
                    raise ValueError("Invalid physical score")
                quality += score if passed else 0
                if not passed:
                    reason = report.get("failure") or "failed"
                    failures[reason] = failures.get(reason, 0) + 1
            except FileNotFoundError:
                failures["missing"] = failures.get("missing", 0) + 1
            except ValueError as exc:
                # Missing paths are a scored failure; protocol violations reject the cohort.
                if not (root / "run.json").exists() or not (root / "evaluation" / "result.json").exists():
                    failures["missing"] = failures.get("missing", 0) + 1
                else:
                    raise exc
        total = len(expected)
        rows.append(
            dict(
                model=label,
                passed=successes,
                total=total,
                pass_at_1=successes / total,
                wilson_95=wilson(successes, total),
                physical_quality=quality / total,
                failures=failures,
            )
        )
    rows.sort(key=lambda r: (-r["pass_at_1"], -r["physical_quality"], r["model"]))
    return {
        "format": "kcb-leaderboard-1",
        "suite_sha256": digest(suite),
        "development_only": allow_local,
        "rows": rows,
    }
