import cadquery as cq
import pytest

from kinematiccad.geometry import Rejected, inspect_geometry, validate_solid
from kinematiccad.references import reference_parts
from kinematiccad.sdk import Part, box, export
from kinematiccad.tasks import make_task


@pytest.mark.integration
def test_valid_brep_clearance_and_mass(tmp_path):
    task = make_task("linear")
    export(reference_parts(task), tmp_path)
    geometry = inspect_geometry(task, tmp_path)
    assert geometry.properties["carriage"]["mass"] == pytest.approx(576e-9 * 1200)
    assert geometry.report["clearances"][0]["gap_mm"] == pytest.approx(0.2)


@pytest.mark.integration
def test_reject_open_disconnected_and_inside_out_solids():
    solid = cq.Workplane("XY").box(10, 10, 10).val()
    with pytest.raises(Rejected, match="invalid_brep"):
        validate_solid(solid.Faces()[0], "open")
    with pytest.raises(Rejected, match="invalid_brep"):
        validate_solid(cq.Compound.makeCompound([solid, solid.translate((20, 0, 0))]), "disconnected")
    with pytest.raises(Rejected, match="invalid_brep"):
        validate_solid(
            cq.Compound.makeCompound([solid, solid.Faces()[0].translate((15, 0, 0))]), "dangling_face"
        )
    solid.wrapped.Reverse()
    with pytest.raises(Rejected):
        validate_solid(solid, "inside_out")


@pytest.mark.integration
def test_reject_forged_collision_proxy(tmp_path):
    task = make_task("linear")
    parts = reference_parts(task)
    parts[0].cells = [box(10, 8, 6)]  # Simulated carriage is smaller than the displayed/checked part.
    export(parts, tmp_path)
    with pytest.raises(Rejected, match="collision_coverage"):
        inspect_geometry(task, tmp_path)


@pytest.mark.integration
def test_no_interference_exemption_for_joint_neighbours(tmp_path):
    task = make_task("linear")
    task.bodies[1].pos = (0, 0, 1)
    export(reference_parts(task), tmp_path)
    with pytest.raises(Rejected, match="static_interference"):
        inspect_geometry(task, tmp_path)


@pytest.mark.integration
def test_clearance_too_small_rejected(tmp_path):
    task = make_task("linear")
    task.bodies[0].envelope = (7, 5, 4)
    parts = reference_parts(task)
    parts[0] = Part.from_cells("carriage", [box(12, 8.3, 6)])
    export(parts, tmp_path)
    with pytest.raises(Rejected, match="clearance"):
        inspect_geometry(task, tmp_path)
