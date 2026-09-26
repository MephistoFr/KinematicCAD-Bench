"""Candidate-facing parametric CAD helpers. All dimensions are in mm.

Cells are *actual* CAD construction solids, not unchecked collision proxies.
The evaluator independently reconstructs their convex hulls and checks B-Rep coverage.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cadquery as cq
import numpy as np
from scipy.spatial import ConvexHull
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.TopTools import TopTools_ListOfShape
from OCP.OSD import OSD_ThreadPool

from .io import write_json
from .schema import Cell, PartAsset, Submission

# CadQuery boolean helpers default to parallel execution. Use explicit serial builders instead.
OSD_ThreadPool.DefaultPool_s().Init(1)
OSD_ThreadPool.DefaultPool_s().SetNbDefaultThreadsToLaunch(1)


def boolean(kind: str, first: cq.Shape, *others: cq.Shape) -> cq.Shape:
    operation = {"fuse": BRepAlgoAPI_Fuse, "cut": BRepAlgoAPI_Cut, "common": BRepAlgoAPI_Common}[kind]()
    arguments, tools = TopTools_ListOfShape(), TopTools_ListOfShape()
    arguments.Append(first.wrapped)
    for shape in others:
        tools.Append(shape.wrapped)
    operation.SetArguments(arguments)
    operation.SetTools(tools)
    operation.SetRunParallel(False)
    operation.Build()
    if not operation.IsDone():
        raise ValueError(f"OpenCascade {kind} did not complete")
    return cq.Shape.cast(operation.Shape())


def convex_shape(vertices) -> cq.Shape:
    points = np.asarray(vertices, dtype=float)
    hull = ConvexHull(points)
    faces = []
    for triangle, equation in zip(hull.simplices, hull.equations):
        a, b, c = points[triangle]
        if np.dot(np.cross(b - a, c - a), equation[:3]) < 0:
            b, c = c, b
        wire = cq.Wire.makePolygon([cq.Vector(*v) for v in (a, b, c)], close=True)
        faces.append(cq.Face.makeFromWires(wire))
    return cq.Solid.makeSolid(cq.Shell.makeShell(faces)).clean()


def prism(points, thickness: float, z: float = 0) -> Cell:
    return Cell(
        vertices=[(float(x), float(y), z + dz) for dz in (-thickness / 2, thickness / 2) for x, y in points]
    )


def box(x: float, y: float, z: float, center=(0, 0, 0)) -> Cell:
    cx, cy, cz = center
    return prism(
        [
            (cx - x / 2, cy - y / 2),
            (cx + x / 2, cy - y / 2),
            (cx + x / 2, cy + y / 2),
            (cx - x / 2, cy + y / 2),
        ],
        z,
        cz,
    )


def cylinder(radius: float, thickness: float, center=(0, 0, 0), segments=96) -> Cell:
    x, y, z = center
    return prism(
        [
            (
                x + radius * math.cos(2 * math.pi * i / segments),
                y + radius * math.sin(2 * math.pi * i / segments),
            )
            for i in range(segments)
        ],
        thickness,
        z,
    )


def transform(cell: Cell, angle=0.0, offset=(0, 0, 0)) -> Cell:
    c, s = math.cos(angle), math.sin(angle)
    dx, dy, dz = offset
    return Cell(vertices=[(c * x - s * y + dx, s * x + c * y + dy, z + dz) for x, y, z in cell.vertices])


@dataclass
class Part:
    name: str
    shape: cq.Shape
    cells: list[Cell]

    @classmethod
    def from_cells(cls, name: str, cells: list[Cell]):
        shapes = [convex_shape(c.vertices) for c in cells]
        solid = boolean("fuse", shapes[0], *shapes[1:]).clean() if len(shapes) > 1 else shapes[0]
        return cls(name, solid, cells)


def export(parts: list[Part], directory: str | Path) -> None:
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    manifest = Submission(parts=[PartAsset(name=p.name, step=p.name + ".step", cells=p.cells) for p in parts])
    for part, asset in zip(parts, manifest.parts):
        cq.exporters.export(part.shape, str(root / asset.step), exportType="STEP")
    write_json(root / "submission.json", manifest)
