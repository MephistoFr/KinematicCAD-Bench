"""Independent B-Rep, interference, clearance and collision coverage validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cadquery as cq
import numpy as np
from OCP.BOPAlgo import BOPAlgo_ArgumentAnalyzer
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

from .io import confined_file, read_json
from .schema import Submission, Task
from .sdk import boolean, convex_shape


class Rejected(ValueError):
    def __init__(self, code: str, detail: str):
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}")


@dataclass
class Geometry:
    manifest: Submission
    shapes: dict
    properties: dict
    meshes: dict
    report: dict


def volume_properties(shape):
    properties = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, properties)
    centre = properties.CentreOfMass()
    matrix = properties.MatrixOfInertia()
    return (
        properties.Mass(),
        [centre.X(), centre.Y(), centre.Z()],
        [[matrix.Value(i + 1, j + 1) for j in range(3)] for i in range(3)],
    )


def validate_solid(shape, name):
    # A compound can contain a solid and dangling zero-volume faces. Reject that
    # topology even though a volume-only coverage check would miss the extra faces.
    top = shape
    while top.ShapeType() == "Compound":
        children = list(top)
        if len(children) != 1:
            raise Rejected("invalid_brep", f"{name}: extra or disconnected top-level geometry")
        top = children[0]
    if top.ShapeType() != "Solid":
        raise Rejected("invalid_brep", f"{name}: expected a solid, found {top.ShapeType()}")
    if len(shape.Solids()) != 1 or not BRepCheck_Analyzer(shape.wrapped, True, False).IsValid():
        raise Rejected("invalid_brep", f"{name}: expected one valid manifold solid")
    if any(not shell.Closed() for shell in shape.Shells()):
        raise Rejected("open_shell", name)
    if volume_properties(shape)[0] <= 1e-6:
        raise Rejected("nonpositive_volume", name)
    analyzer = BOPAlgo_ArgumentAnalyzer()
    analyzer.SetShape1(shape.wrapped)
    analyzer.SelfInterMode = True
    analyzer.SetRunParallel(False)
    analyzer.Perform()
    if analyzer.HasFaulty():
        raise Rejected("self_intersection", name)


def world_positions(task: Task) -> dict[str, np.ndarray]:
    positions = {"world": np.zeros(3)}
    for body in task.bodies:
        positions[body.name] = positions[body.parent] + np.asarray(body.pos)
    return positions


def mesh_of(shape):
    vertices, triangles = shape.tessellate(0.03, 0.12)
    return {"vertices": [list(v.toTuple()) for v in vertices], "triangles": [list(t) for t in triangles]}


def inspect_geometry(task: Task, root: Path, progress=None) -> Geometry:
    manifest = Submission.model_validate(read_json(root / "submission.json"))
    if {p.name for p in manifest.parts} != {b.name for b in task.bodies}:
        raise Rejected("part_set", "Part names must exactly match the task")
    shapes, properties, meshes = {}, {}, {}
    report = {"parts": {}, "pairs": [], "clearances": []}
    assets = {p.name: p for p in manifest.parts}
    for body in task.bodies:
        asset = assets[body.name]
        imported = cq.importers.importStep(str(confined_file(root, asset.step))).vals()
        if len(imported) != 1:
            raise Rejected("invalid_brep", f"{body.name}: multiple STEP roots")
        shape = imported[0]
        shapes[body.name] = shape
        # Keep an early mesh for diagnosis even when subsequent checks reject it.
        meshes[body.name] = mesh_of(shape)
        if progress:
            progress(meshes)
        validate_solid(shape, body.name)
        volume, centre, inertia = volume_properties(shape)
        if not body.min_volume <= volume <= body.max_volume:
            raise Rejected("volume_budget", body.name)
        bbox = shape.BoundingBox()
        for lo, hi, bound in zip(
            [bbox.xmin, bbox.ymin, bbox.zmin], [bbox.xmax, bbox.ymax, bbox.zmax], body.envelope
        ):
            if lo < -bound - 1e-5 or hi > bound + 1e-5:
                raise Rejected("envelope", body.name)
        for point in body.mounts:
            if shape.distance(cq.Vertex.makeVertex(*point)) > 1.0:
                raise Rejected("unsupported_mount", f"{body.name}: {point}")
        cells = []
        for cell in asset.cells:
            v = np.asarray(cell.vertices)
            if not np.isfinite(v).all() or np.max(np.abs(v)) > 500:
                raise Rejected("collision_coordinates", body.name)
            cells.append(convex_shape(v))
        union = boolean("fuse", cells[0], *cells[1:]).clean() if len(cells) > 1 else cells[0]
        validate_solid(union, body.name + " collision union")
        # Check both directions separately: a signed volume difference could cancel out.
        missing = abs(boolean("cut", shape, union).Volume())
        extra = abs(boolean("cut", union, shape).Volume())
        allowed = max(1e-5, volume * 1e-7)
        if missing > allowed or extra > allowed:
            raise Rejected(
                "collision_coverage", f"{body.name}: missing={missing:.8g}, extra={extra:.8g} mm^3"
            )
        properties[body.name] = {
            "mass": volume * 1e-9 * body.density,
            "com": (np.array(centre) * 1e-3).tolist(),
            "inertia": (np.array(inertia) * body.density * 1e-15).tolist(),
        }
        report["parts"][body.name] = dict(
            volume_mm3=volume,
            missing_mm3=missing,
            extra_mm3=extra,
            cells=len(cells),
            mass_kg=properties[body.name]["mass"],
        )
    positions = world_positions(task)
    world = {name: s.translate(tuple(positions[name])) for name, s in shapes.items()}
    names = sorted(world)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            overlap = abs(boolean("common", world[a], world[b]).Volume())
            gap = world[a].distance(world[b])
            report["pairs"].append(dict(a=a, b=b, overlap_mm3=overlap, gap_mm=gap))
            if overlap > 1e-5:
                raise Rejected("static_interference", f"{a}/{b}: {overlap:.8g} mm^3")
    for clearance in task.clearances:
        gap = world[clearance.a].distance(world[clearance.b])
        passed = clearance.minimum_mm - 1e-6 <= gap <= clearance.maximum_mm + 1e-6
        report["clearances"].append(dict(a=clearance.a, b=clearance.b, gap_mm=gap, passed=passed))
        if not passed:
            raise Rejected("clearance", f"{clearance.a}/{clearance.b}: {gap:.8g} mm")
    # Closing pins cannot act remotely on unrelated sculptures.
    for link in task.connections:
        for name, point in [(link.a, link.anchor_a), (link.b, link.anchor_b)]:
            if shapes[name].distance(cq.Vertex.makeVertex(*point)) > 1.0:
                raise Rejected("unsupported_closure", name)
        a = positions[link.a] + link.anchor_a
        b = positions[link.b] + link.anchor_b
        if np.linalg.norm(a - b) > 1e-6:
            raise Rejected("initial_closure", "Task anchors are not coincident")
    return Geometry(manifest, shapes, properties, meshes, report)
