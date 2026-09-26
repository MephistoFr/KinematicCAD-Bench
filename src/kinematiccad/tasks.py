"""Versioned procedural contracts. Public tasks are calibration data, not a secret test set."""

from __future__ import annotations

import hashlib
from .schema import Body, Clearance, Connection, Task, Trial

FAMILIES = ("linear", "spur", "slider_crank", "cam", "planetary")


def make_task(family: str, seed: int = 0) -> Task:
    # Stable integer sampling, independent of Python RNG implementation.
    variant = int.from_bytes(hashlib.sha256(f"kcb-1:{family}:{seed}".encode()).digest()[:4], "big")
    common = dict(id=f"{family}-{seed:06d}", family=family, seed=seed)
    trials = [Trial(name="forward", speed=3.0), Trial(name="reverse_loaded", speed=-2.7, load=0.0004)]
    if family == "spur":
        n = (16, 18, 20)[variant % 3]
        ratio = 2 + (variant // 3) % 2
        module = 2.0
        r1, r2 = n * module / 2, n * ratio * module / 2
        return Task(
            **common,
            description=f"Design two external spur gears with {n} and {n * ratio} teeth, "
            f"module {module} mm, pressure angle 20 degrees, face width 6 mm. "
            "Transmit rotation by tooth contact, including reverse motion under load.",
            parameters=dict(
                teeth_in=n, teeth_out=n * ratio, module=module, ratio=-1 / ratio, width=6, backlash=0.12
            ),
            bodies=[
                Body(name="input", envelope=(r1 + 4, r1 + 4, 4)),
                Body(name="output", pos=(r1 + r2, 0, 0), envelope=(r2 + 4, r2 + 4, 4)),
            ],
            clearances=[Clearance(a="input", b="output", minimum_mm=0.005, maximum_mm=0.3)],
            driver="input",
            output="output",
            trials=trials,
            duration=3.0 * ratio + 0.2,
            minimum_travel=6.283185307179586 * ratio + 0.1,
        )
    if family == "slider_crank":
        r, length = 12.0 + 2 * (variant % 3), 48.0 + 4 * (variant % 2)
        return Task(
            **common,
            description=f"Design a slider-crank with crank radius {r} mm and rod "
            f"length {length} mm. Supplied ideal bearings connect the stacked links; "
            "maintain axial material clearance and transmit rotation into reciprocating translation.",
            parameters=dict(radius=r, length=length),
            bodies=[
                Body(name="crank", envelope=(r + 5, r + 5, 3), mounts=[(0, 0, 0), (r, 0, 0)]),
                Body(
                    name="rod",
                    parent="crank",
                    pos=(r, 0, 5),
                    envelope=(length + 4, 5, 2.1),
                    mounts=[(0, 0, 0), (length, 0, 0)],
                ),
                Body(
                    name="slider",
                    pos=(r + length, 0, 10),
                    joint="slide",
                    axis=(1, 0, 0),
                    envelope=(7, 7, 2.1),
                    damping=0,
                ),
            ],
            connections=[Connection(a="rod", b="slider", anchor_a=(length, 0, 2.5), anchor_b=(0, 0, -2.5))],
            clearances=[
                Clearance(a="crank", b="rod", minimum_mm=0.5, maximum_mm=1.5),
                Clearance(a="rod", b="slider", minimum_mm=0.5, maximum_mm=1.5),
            ],
            driver="crank",
            output="slider",
            trials=trials,
            position_tolerance=0.00035,
            speed_tolerance=0.12,
        )
    if family == "cam":
        radius, eccentricity = 16.0, 3.0 + variant % 3
        return Task(
            **common,
            description=f"Design an eccentric circular cam, radius {radius} mm and "
            f"eccentricity {eccentricity} mm along local +Y, driving a flat follower along +Y. "
            "A downward preload maintains unilateral contact. Follower height must follow R+e*cos(theta).",
            parameters=dict(radius=radius, eccentricity=eccentricity, gap=0.06),
            bodies=[
                Body(name="cam", envelope=(radius + eccentricity + 1, radius + eccentricity + 1, 4)),
                Body(
                    name="follower",
                    pos=(0, radius + eccentricity + 2 + 0.06, 0),
                    joint="slide",
                    axis=(0, 1, 0),
                    envelope=(radius + 2, 3, 4),
                    damping=0.001,
                ),
            ],
            clearances=[Clearance(a="cam", b="follower", minimum_mm=0.02, maximum_mm=0.15)],
            driver="cam",
            output="follower",
            trials=[
                Trial(name="forward", speed=3, load=0.08),
                Trial(name="reverse_loaded", speed=-2.7, load=0.12),
            ],
            position_tolerance=0.0002,
            speed_tolerance=0.15,
        )
    if family == "planetary":
        ns, np_ = 16, 12 + 2 * (variant % 2)
        nr = ns + 2 * np_
        module = 2.0
        rs, rp, rr = ns * module / 2, np_ * module / 2, nr * module / 2
        return Task(
            **common,
            description=f"Design a one-planet epicyclic train: sun {ns}, planet {np_}, "
            f"fixed internal ring {nr} teeth, module {module} mm, pressure angle 20 degrees. "
            "Drive the sun; the carrier output must obey Willis' relation through tooth contacts.",
            parameters=dict(
                teeth_sun=ns,
                teeth_planet=np_,
                teeth_ring=nr,
                module=module,
                ratio=ns / (ns + nr),
                width=6,
                backlash=0.14,
                ring_backlash=0.30,
            ),
            bodies=[
                Body(name="sun", envelope=(rs + 4, rs + 4, 4)),
                Body(
                    name="carrier",
                    pos=(0, 0, 7),
                    envelope=(rs + rp + 5, 6, 2),
                    mounts=[(0, 0, 0), (rs + rp, 0, 0)],
                ),
                Body(name="planet", parent="carrier", pos=(rs + rp, 0, -7), envelope=(rp + 4, rp + 4, 4)),
                Body(name="ring", joint="fixed", envelope=(rr + 7, rr + 7, 4), mounts=[(rr + 4, 0, 0)]),
            ],
            clearances=[
                Clearance(a="sun", b="planet", minimum_mm=0.003, maximum_mm=0.35),
                Clearance(a="planet", b="ring", minimum_mm=0.003, maximum_mm=0.35),
                Clearance(a="carrier", b="planet", minimum_mm=1, maximum_mm=3),
            ],
            driver="sun",
            output="carrier",
            trials=trials,
            position_tolerance=0.07,
            speed_tolerance=0.20,
            duration=3.0 * (ns + nr) / ns + 0.2,
            minimum_travel=6.283185307179586 * (ns + nr) / ns + 0.1,
        )
    if family == "linear":
        return Task(
            **common,
            description="Design a 12 x 8 x 6 mm carriage moving along +X within a "
            "U-channel guide. Maintain 0.10 to 0.30 mm minimum clearance over a 30 mm stroke. "
            "Under constant applied force, verify x(t)=F*t^2/(2*m), with B-Rep-derived mass. "
            "The carriage has six free degrees of freedom: frictionless guide contacts must "
            "support gravity and a 0.001 N lateral load without escape or excessive tilt.",
            parameters=dict(clearance=0.2, lateral_force=0.001),
            bodies=[
                Body(
                    name="carriage",
                    joint="free",
                    axis=(1, 0, 0),
                    envelope=(6.1, 4.1, 3.1),
                    min_volume=500,
                    max_volume=650,
                    damping=0,
                ),
                Body(name="guide", joint="fixed", envelope=(50, 7, 6), mounts=[(0, 0, -4.5)]),
            ],
            clearances=[Clearance(a="carriage", b="guide", minimum_mm=0.10, maximum_mm=0.30)],
            driver="carriage",
            output="carriage",
            trials=[
                Trial(name="forward", force=0.0003, load=0),
                Trial(name="reverse", force=-0.0003, load=0),
            ],
            duration=0.3,
            warmup=0.02,
            position_tolerance=0.00008,
            speed_tolerance=0.02,
            minimum_travel=0.012,
        )
    raise ValueError(f"Unknown family {family!r}; choose {FAMILIES}")
