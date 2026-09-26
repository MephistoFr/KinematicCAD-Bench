from __future__ import annotations

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

Vec3 = tuple[FiniteFloat, FiniteFloat, FiniteFloat]
Name = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Cell(Strict):
    """The convex hull of these vertices, in millimetres, in the part frame."""

    vertices: list[Vec3] = Field(min_length=4, max_length=256)


class PartAsset(Strict):
    name: Name
    step: str = Field(pattern=r"^[a-z][a-z0-9_]{0,47}\.step$")
    cells: list[Cell] = Field(min_length=1, max_length=512)


class Submission(Strict):
    format: Literal["kcb-submission-1"] = "kcb-submission-1"
    units: Literal["mm"] = "mm"
    parts: list[PartAsset] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def unique_parts(self):
        if len({p.name for p in self.parts}) != len(self.parts):
            raise ValueError("Duplicate part name")
        if sum(len(p.cells) for p in self.parts) > 1400:
            raise ValueError("Too many collision cells")
        return self


class Body(Strict):
    name: Name
    parent: str = "world"
    pos: Vec3 = (0, 0, 0)  # mm, relative to parent
    joint: Literal["hinge", "slide", "free", "fixed"] = "hinge"
    axis: Vec3 = (0, 0, 1)
    envelope: Vec3 = (100, 100, 20)  # absolute local coordinate bounds, mm
    min_volume: FiniteFloat = 10
    max_volume: FiniteFloat = 1e6
    density: FiniteFloat = 1200  # kg/m^3, evaluator-owned
    damping: FiniteFloat = 0.00001
    # Attachment points must lie near actual material. Bearings are supplied fixtures.
    mounts: list[Vec3] = Field(default_factory=lambda: [(0, 0, 0)])


class Clearance(Strict):
    a: Name
    b: Name
    minimum_mm: FiniteFloat
    maximum_mm: FiniteFloat


class Connection(Strict):
    a: Name
    b: Name
    anchor_a: Vec3
    anchor_b: Vec3


class Trial(Strict):
    name: Name
    speed: FiniteFloat = 3.0
    load: FiniteFloat = 0.0002  # Nm (hinge) or N (slide)
    force: FiniteFloat = 0.002  # linear calibration task


class Task(Strict):
    format: Literal["kcb-task-1"] = "kcb-task-1"
    id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,70}$")]
    family: Literal["spur", "slider_crank", "cam", "planetary", "linear"]
    seed: int
    description: str
    parameters: dict[str, FiniteFloat]
    bodies: list[Body] = Field(min_length=1, max_length=16)
    clearances: list[Clearance] = Field(default_factory=list)
    connections: list[Connection] = Field(default_factory=list)
    driver: Name
    output: Name
    trials: list[Trial] = Field(min_length=1, max_length=8)
    timestep: FiniteFloat = 0.0005
    duration: FiniteFloat = 2.8
    warmup: FiniteFloat = 0.3
    position_tolerance: FiniteFloat = 0.06  # radians, or metres for translation
    speed_tolerance: FiniteFloat = 0.15  # relative RMS error
    ratio_tolerance: FiniteFloat = 0.005
    max_penetration_mm: FiniteFloat = 0.08
    max_closure_mm: FiniteFloat = 0.12
    max_guidance_error_mm: FiniteFloat = 0.5
    max_tilt_rad: FiniteFloat = 0.03
    minimum_travel: FiniteFloat = 5.5
    motor_kv: FiniteFloat = 0.005
    motor_limit: FiniteFloat = 0.004

    @model_validator(mode="after")
    def graph(self):
        if len({trial.name for trial in self.trials}) != len(self.trials):
            raise ValueError("Trial names must be unique")
        names = set()
        for b in self.bodies:
            if b.name in names or (b.parent != "world" and b.parent not in names):
                raise ValueError("Bodies must be unique and topologically ordered")
            names.add(b.name)
        if self.driver not in names or self.output not in names:
            raise ValueError("Unknown driver/output")
        if self.timestep <= 0 or not 0 <= self.warmup < self.duration:
            raise ValueError("Invalid integration window")
        if self.duration / self.timestep > 100_000:
            raise ValueError("Too many integration steps")
        return self
