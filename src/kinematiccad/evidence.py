"""Self-contained evidence: CPU rendering only, no display, browser, GPU or CDN required."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .geometry import world_positions
from .io import write_json

PALETTE = [(244, 173, 66), (82, 181, 224), (176, 134, 223), (110, 198, 155), (240, 122, 117)]


def static_frames(task, meshes):
    positions = world_positions(task)
    return [
        {
            "time": 0.0,
            "poses": {
                name: {"pos": positions[name].tolist(), "rot": np.eye(3).flatten().tolist()}
                for name in meshes
            },
        }
    ]


def render_frames(meshes, frames, status, label):
    # Oblique orthographic projection preserves scale; view is fixed across the entire trial.
    angle, pitch = -0.20, 0.60
    c, s = np.cos(angle), np.sin(angle)
    rot = np.array(
        [
            [c, -s, 0],
            [s * np.cos(pitch), c * np.cos(pitch), -np.sin(pitch)],
            [s * np.sin(pitch), c * np.sin(pitch), np.cos(pitch)],
        ]
    )
    all_points = []
    for frame in frames:
        for name, mesh in meshes.items():
            if name not in frame["poses"]:
                continue
            pose = frame["poses"][name]
            v = np.asarray(mesh["vertices"]) @ np.array(pose["rot"]).reshape(3, 3).T + pose["pos"]
            all_points.append(v @ rot.T)
    if all_points:
        points = np.concatenate(all_points)
        lo, hi = points.min(axis=0), points.max(axis=0)
        centre = (lo + hi) / 2
        scale = min(680 / max(1, hi[0] - lo[0]), 360 / max(1, hi[1] - lo[1]))
    else:
        centre, scale = np.zeros(3), 1
    images = []
    for frame in frames:
        image = Image.new("RGB", (800, 520), (17, 24, 39))
        draw = ImageDraw.Draw(image)
        polygons, depths, colors = [], [], []
        for i, (name, mesh) in enumerate(meshes.items()):
            if name not in frame["poses"]:
                continue
            pose = frame["poses"][name]
            vertices = np.asarray(mesh["vertices"]) @ np.asarray(pose["rot"]).reshape(3, 3).T + pose["pos"]
            triangles = (vertices @ rot.T)[np.asarray(mesh["triangles"])]
            normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
            normals /= np.maximum(1e-10, np.linalg.norm(normals, axis=1))[:, None]
            shades = 0.62 + 0.38 * np.abs(normals @ np.array([0.25, -0.4, 0.88]))
            depths.extend(triangles[:, :, 2].mean(axis=1).tolist())
            xy = (triangles[:, :, :2] - centre[:2]) * np.array([scale, -scale]) + [400, 275]
            polygons.extend(xy.tolist())
            colors.extend(
                np.minimum(255, np.array(PALETTE[i % len(PALETTE)])[None, :] * shades[:, None])
                .astype(int)
                .tolist()
            )
        for idx in np.argsort(depths, kind="stable"):
            draw.polygon([tuple(v) for v in polygons[idx]], fill=tuple(colors[idx]))
        draw.text((24, 20), "KINEMATICCAD-BENCH  /  PHYSICAL EVIDENCE", fill=(223, 230, 243))
        draw.text((24, 46), label[:105], fill=(150, 169, 195))
        draw.text((24, 482), f"{status.upper()}  |  t = {frame['time']:.3f} s", fill=(255, 198, 99))
        if not meshes:
            draw.text((24, 240), "No usable geometry. See the diagnostic report below.", fill=(245, 140, 140))
        images.append(image)
    return images


def write_evidence(output: Path, task, meshes, runs, report):
    output.mkdir(parents=True, exist_ok=True)
    if not runs:
        runs = [dict(name="initial_state", frames=static_frames(task, meshes))]
    payload = dict(task=task.model_dump(mode="json"), meshes=meshes, runs=runs, report=report)
    write_json(output / "evidence.json", payload)
    template = (Path(__file__).parent / "viewer.html").read_text(encoding="utf-8")
    encoded = json.dumps(payload, allow_nan=False, separators=(",", ":")).replace("<", "\\u003c")
    (output / "evidence.html").write_text(template.replace("__DATA__", encoded), encoding="utf-8")
    label = task.id + " / " + str(report.get("failure") or "measured rigid-body dynamics")
    for i, run in enumerate(runs):
        images = render_frames(meshes, run["frames"], report["status"], label + " / " + run["name"])
        if i == 0:
            images[0].save(output / "preview.png")
        if len(images) > 1:
            images[0].save(
                output / f"{run['name']}.gif",
                save_all=True,
                append_images=images[1:],
                duration=40,
                loop=0,
                optimize=False,
                disposal=2,
            )


def infrastructure_evidence(output: Path, task, code, detail):
    report = dict(status="error", failure=code, detail=str(detail)[:4000], passed=False, score=0.0)
    write_json(output / "result.json", report)
    write_evidence(output, task, {}, [], report)
    return report
