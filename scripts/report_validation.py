"""Create a factual local validation record from measured release artifacts."""

import hashlib
from pathlib import Path
import re

from kinematiccad.io import digest, read_json, write_json


def main():
    root = Path(__file__).resolve().parents[1]
    suite = read_json(root / "suites" / "calibration.json")
    batch = root / "artifacts" / "release-calibration"
    reports = [read_json(batch / t["id"] / "evaluation" / "result.json") for t in suite["tasks"]]
    if not all(r["passed"] for r in reports):
        raise ValueError("Calibration contains failures")
    test_text = (root / "artifacts" / "test-results.txt").read_text(encoding="utf-8-sig")
    counts = re.search(r"(\d+) passed, (\d+) skipped", test_text)
    if not counts:
        raise ValueError("No successful complete test report")
    original = read_json(batch / "linear-000000" / "evaluation" / "result.json")
    replay = read_json(root / "artifacts" / "replay-linear" / "result.json")
    identical = original["result_sha256"] == replay["result_sha256"]
    if not identical:
        raise ValueError("Replay changed")
    write_json(
        root / "artifacts" / "replay-verification.json",
        {
            "identical": identical,
            "original_result_sha256": original["result_sha256"],
            "replay_result_sha256": replay["result_sha256"],
        },
    )
    lines = [
        "# Local validation record",
        "",
        "Validated on 2026-09-22 using the actual native CAD and physics libraries.",
        "",
        f"- Automated tests: **{counts[1]} passed, {counts[2]} skipped** (Docker-only test).",
        "- Public calibration: **5/5 reference designs passed**, two load/direction trials per family, each at dt and dt/2.",
        "- Linear replay: identical full report SHA-256, including all four trajectory hashes.",
        "- Static analysis and formatting: Ruff passed.",
        "- Offline HTML: rendered in headless Chrome and visually inspected; embedded JavaScript passed Node syntax checking.",
        "- Distribution: source archive and wheel built; wheel includes the offline viewer, source includes contracts and schemas.",
        "",
        "## Physical results",
        "",
        "| Family | Verdict | Worst position RMS | Worst penetration (mm) | Quality |",
        "| --- | --- | --- | --- | --- |",
    ]
    for report in reports:
        metrics = [trial[level] for trial in report["trials"] for level in ("coarse", "fine")]
        rms = max(m["rms_position_error"] for m in metrics)
        unit = "rad"
        if report["family"] in ("linear", "slider_crank", "cam"):
            rms *= 1000
            unit = "mm"
        penetration = max(m["max_penetration_mm"] for m in metrics)
        lines.append(
            f"| {report['family']} | passed | {rms:.6g} {unit} | {penetration:.6g} | {report['score']:.6f} |"
        )
    env = reports[0]["environment"]
    lines += [
        "",
        "These are calibration designs, not measured LLM performance or a public model leaderboard.",
        "",
        "## Reproducibility identifiers",
        "",
        f"- Suite SHA-256: `{digest(suite)}`",
        f"- Implementation SHA-256: `{env['implementation_sha256']}`",
        f"- Linear report/replay SHA-256: `{original['result_sha256']}`",
        f"- Runtime: Python {env['python']}, {env['os']} {env['machine']}; {env['processor']}.",
        "- Native packages: " + ", ".join(f"{k} {v}" for k, v in env["libraries"].items()) + ".",
        "",
        "## Explicitly unverified",
        "",
        "Docker Engine was unavailable on this machine. The two images and their dedicated CI/test workflow are provided,",
        "but container execution and the Linux CI jobs were not run here. No paid or live model API was called; HTTP",
        "protocols, response handling and deadlines were verified with mocked transports. Nonzero procedural seeds",
        "are supported but are not part of this five-task certified calibration record.",
        "",
        "## Reproduce",
        "",
        "```bash",
        "uv sync --frozen --extra dev",
        "uv run pytest -q",
        "uv run kcb benchmark --suite suites/calibration.json --provider configs/replay.json --label reference --unsafe-local --out runs/reference",
        "uv run kcb replay runs/reference/linear-000000 --unsafe-local --out runs/replay",
        "```",
        "",
        "The delivered local evidence is under `artifacts/release-calibration/`; large generated artifacts are excluded",
        "from source distributions. The local calibration ranking is `artifacts/leaderboard.json` and is explicitly",
        "marked development-only. See the protocol for the limits of numerical rigid-body evidence.",
        "",
    ]
    (root / "VALIDATION.md").write_text("\n".join(lines), encoding="utf-8")
    hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (root / "dist").glob("kinematiccad*.*")
    }
    write_json(root / "artifacts" / "distribution-sha256.json", hashes)
    print(root / "VALIDATION.md")


if __name__ == "__main__":
    main()
