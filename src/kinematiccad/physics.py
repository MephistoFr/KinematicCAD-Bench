"""Evaluator-owned MJCF: only the input is actuated; transmission emerges from physics."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path

import mujoco
import numpy as np

from .geometry import Geometry
from .schema import Task, Trial


def numbers(values) -> str:
    return " ".join(format(float(v), ".17g") for v in values)


def compile_model(task: Task, geometry: Geometry, timestep=None):
    root = ET.Element("mujoco", model=task.id)
    ET.SubElement(root, "compiler", angle="radian", inertiafromgeom="false", autolimits="true")
    option = ET.SubElement(
        root,
        "option",
        timestep=str(timestep or task.timestep),
        gravity="0 0 -9.81" if task.family == "linear" else "0 0 0",
        integrator="implicitfast",
        solver="PGS",
        iterations="100",
        tolerance="1e-10",
        cone="pyramidal",
        impratio="1",
        ccd_iterations="100",
        ccd_tolerance="1e-9",
    )
    ET.SubElement(
        option,
        "flag",
        filterparent="disable",
        multiccd="enable" if task.family == "linear" else "disable",
        nativeccd="enable",
    )
    ET.SubElement(root, "size", memory="128M")
    default = ET.SubElement(root, "default")
    ET.SubElement(
        default,
        "geom",
        friction="0 0 0" if task.family == "linear" else "0.02 0.0001 0.0001",
        condim="1" if task.family == "linear" else "3",
        margin="0",
        gap="0",
        solref="0.002 1",
        solimp="0.99 0.999 0.0001",
        density="0",
    )
    asset = ET.SubElement(root, "asset")
    world = ET.SubElement(root, "worldbody")
    elements = {"world": world}
    parts = {p.name: p for p in geometry.manifest.parts}
    for spec in task.bodies:
        body = ET.SubElement(
            elements[spec.parent], "body", name=spec.name, pos=numbers(np.array(spec.pos) * 0.001)
        )
        elements[spec.name] = body
        properties = geometry.properties[spec.name]
        inertia = np.asarray(properties["inertia"])
        ET.SubElement(
            body,
            "inertial",
            pos=numbers(properties["com"]),
            mass=str(properties["mass"]),
            fullinertia=numbers(
                [inertia[0, 0], inertia[1, 1], inertia[2, 2], inertia[0, 1], inertia[0, 2], inertia[1, 2]]
            ),
        )
        if spec.joint == "free":
            ET.SubElement(body, "freejoint", name=spec.name)
        elif spec.joint != "fixed":
            ET.SubElement(
                body,
                "joint",
                name=spec.name,
                type=spec.joint,
                axis=numbers(spec.axis),
                damping=str(spec.damping),
                armature="0",
            )
        for i, cell in enumerate(parts[spec.name].cells):
            meshname = f"{spec.name}_{i}"
            vertices = np.asarray(cell.vertices, dtype=float) * 0.001
            ET.SubElement(asset, "mesh", name=meshname, vertex=numbers(vertices.flatten()))
            ET.SubElement(body, "geom", name=meshname, type="mesh", mesh=meshname)
    if task.connections:
        equality = ET.SubElement(root, "equality")
        for i, link in enumerate(task.connections):
            for suffix, name, point in [("a", link.a, link.anchor_a), ("b", link.b, link.anchor_b)]:
                ET.SubElement(
                    elements[name],
                    "site",
                    name=f"closure_{i}_{suffix}",
                    pos=numbers(np.array(point) * 0.001),
                    size="0.0005",
                )
            ET.SubElement(
                equality,
                "connect",
                site1=f"closure_{i}_a",
                site2=f"closure_{i}_b",
                solref="0.002 1",
                solimp="0.99 0.999 0.0001",
            )
    if task.family != "linear":
        actuator = ET.SubElement(root, "actuator")
        ET.SubElement(
            actuator,
            "velocity",
            name="input_motor",
            joint=task.driver,
            kv=str(task.motor_kv),
            forcelimited="true",
            forcerange=numbers([-task.motor_limit, task.motor_limit]),
        )
    xml = ET.tostring(root, encoding="unicode")
    return mujoco.MjModel.from_xml_string(xml), xml


def joint_addresses(model, name):
    joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
    return int(model.jnt_qposadr[joint]), int(model.jnt_dofadr[joint])


def simulate(task: Task, geometry: Geometry, trial: Trial, timestep=None) -> dict:
    model, xml = compile_model(task, geometry, timestep)
    data = mujoco.MjData(model)
    iq, iv = joint_addresses(model, task.driver)
    oq, ov = joint_addresses(model, task.output)
    body_ids = {b.name: mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, b.name) for b in task.bodies}
    dt = model.opt.timestep
    steps = round(task.duration / dt)
    frame_stride = max(1, round(1 / (25 * dt)))
    trace, frames = [], []
    maximum_penetration = maximum_closure = motor_work = load_work = 0.0
    maximum_guidance = maximum_tilt = 0.0
    worst_contact = None
    failure = None
    mujoco.mj_forward(model, data)

    def record(frame=False):
        trace.append(
            [
                float(data.time),
                float(data.qpos[iq]),
                float(data.qpos[oq]),
                float(data.qvel[iv]),
                float(data.qvel[ov]),
            ]
        )
        if frame:
            frames.append(
                {
                    "time": float(data.time),
                    "poses": {
                        name: {"pos": (data.xpos[idx] * 1000).tolist(), "rot": data.xmat[idx].tolist()}
                        for name, idx in body_ids.items()
                    },
                }
            )

    record(True)
    for step in range(steps):
        data.qfrc_applied[:] = 0
        if task.family == "linear":
            data.qfrc_applied[iv] = trial.force
            data.qfrc_applied[iv + 1] = math.copysign(task.parameters["lateral_force"], trial.force)
            applied_load = 0
        else:
            # A bounded torque controller acts exclusively on the designated input.
            ramp = min(1.0, float(data.time) / 0.2)
            data.ctrl[0] = trial.speed * ramp * ramp * (3 - 2 * ramp)
            if task.family == "cam":
                load_ramp = min(1.0, float(data.time) / 0.05)
                applied_load = -trial.load * load_ramp * load_ramp * (3 - 2 * load_ramp)
            elif task.family == "slider_crank":
                applied_load = -trial.load * math.tanh(float(data.qvel[ov]) * 1000)
            else:
                applied_load = -math.copysign(trial.load, trial.speed * task.parameters["ratio"])
            data.qfrc_applied[ov] = applied_load
        mujoco.mj_step(model, data)
        if (
            any(w.number for w in data.warning)
            or not np.isfinite(data.qpos).all()
            or not np.isfinite(data.qvel).all()
        ):
            failure = "solver_warning_or_nonfinite"
            break
        if np.max(np.abs(data.qvel)) > 1000 or np.max(np.abs(data.qpos)) > 100:
            failure = "structural_divergence"
            record(True)
            break
        # Refresh poses/contacts at the integrated state, not the previous step.
        mujoco.mj_forward(model, data)
        if task.family == "linear":
            maximum_guidance = max(maximum_guidance, float(np.max(np.abs(data.qpos[iq + 1 : iq + 3])) * 1000))
            maximum_tilt = max(maximum_tilt, 2 * math.acos(min(1.0, abs(float(data.qpos[iq + 3])))))
        for contact in data.contact:
            penetration = max(0.0, -float(contact.dist) * 1000)
            if penetration > maximum_penetration:
                maximum_penetration = penetration
                worst_contact = {
                    "time": float(data.time),
                    "depth_mm": penetration,
                    "geoms": [
                        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, int(g)) for g in contact.geom
                    ],
                }
        for i in range(len(task.connections)):
            a = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, f"closure_{i}_a")
            b = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, f"closure_{i}_b")
            maximum_closure = max(
                maximum_closure, float(np.linalg.norm(data.site_xpos[a] - data.site_xpos[b]) * 1000)
            )
        motor_force = trial.force if task.family == "linear" else float(data.actuator_force[0])
        motor_work += motor_force * float(data.qvel[iv]) * dt
        load_work += -applied_load * float(data.qvel[ov]) * dt
        record(step % frame_stride == 0 or step == steps - 1)
    return dict(
        trace=trace,
        frames=frames,
        xml=xml,
        failure=failure,
        max_penetration_mm=maximum_penetration,
        max_closure_mm=maximum_closure,
        max_guidance_error_mm=maximum_guidance,
        max_tilt_rad=maximum_tilt,
        motor_work_j=motor_work,
        load_work_j=load_work,
        worst_contact=worst_contact,
    )


def expected(task: Task, trace: np.ndarray, mass: float, trial: Trial):
    t, theta = trace[:, 0], trace[:, 1]
    p = task.parameters
    if task.family in ("spur", "planetary"):
        return theta * p["ratio"]
    if task.family == "slider_crank":
        r, length = p["radius"] * 0.001, p["length"] * 0.001
        return r * np.cos(theta) + np.sqrt(length * length - r * r * np.sin(theta) ** 2) - (r + length)
    if task.family == "cam":
        return (p["eccentricity"] * (np.cos(theta) - 1) - p["gap"]) * 0.001
    if task.family == "linear":
        return trial.force * t * t / (2 * mass)
    raise ValueError(task.family)


def metrics(task: Task, geometry: Geometry, trial: Trial, run: dict):
    trace = np.asarray(run["trace"])
    target = expected(task, trace, geometry.properties[task.output]["mass"], trial)
    mask = trace[:, 0] >= task.warmup
    if mask.sum() < 10:
        return dict(passed=False, score=0.0, reasons=[run["failure"] or "insufficient_samples"])
    residual = trace[mask, 2] - target[mask]
    rms = float(np.sqrt(np.mean(residual**2)))
    peak = float(np.max(np.abs(residual)))
    # Windowed velocities suppress tooth-contact impulses, without fitting away ratio errors.
    stride = max(1, round(0.03 / (trace[1, 0] - trace[0, 0])))
    indices = np.flatnonzero(mask)[::stride]
    if len(indices) < 3:
        return dict(passed=False, score=0.0, reasons=[run["failure"] or "insufficient_velocity_samples"])
    velocity = np.diff(trace[indices, 2]) / np.diff(trace[indices, 0])
    target_v = np.diff(target[indices]) / np.diff(trace[indices, 0])
    speed_error = float(
        np.sqrt(np.mean((velocity - target_v) ** 2)) / max(1e-8, np.sqrt(np.mean(target_v**2)))
    )
    travel = float(np.ptp(trace[:, 1]))
    reasons = []
    ratio_error = None
    measured_ratio = None
    if task.family in ("spur", "planetary"):
        x = trace[mask, 1] - np.mean(trace[mask, 1])
        y = trace[mask, 2] - np.mean(trace[mask, 2])
        measured_ratio = float(np.dot(x, y) / max(1e-15, np.dot(x, x)))
        ratio_error = abs(measured_ratio / task.parameters["ratio"] - 1)
        if ratio_error > task.ratio_tolerance:
            reasons.append("transmission_ratio")
    if run["failure"]:
        reasons.append(run["failure"])
    if trace[-1, 0] < task.duration - task.timestep:
        reasons.append("incomplete_duration")
    if rms > task.position_tolerance or peak > 3 * task.position_tolerance:
        reasons.append("motion_law")
    if speed_error > task.speed_tolerance:
        reasons.append("transmission_velocity")
    if travel < task.minimum_travel:
        reasons.append("jammed_or_insufficient_travel")
    if run["max_penetration_mm"] > task.max_penetration_mm:
        reasons.append("dynamic_interference")
    if run["max_closure_mm"] > task.max_closure_mm:
        reasons.append("closure_divergence")
    if run["max_guidance_error_mm"] > task.max_guidance_error_mm or run["max_tilt_rad"] > task.max_tilt_rad:
        reasons.append("guide_escape_or_tilt")
    if (
        task.family in ("spur", "planetary")
        and run["load_work_j"] < trial.load * task.minimum_travel * abs(task.parameters["ratio"]) * 0.5
    ):
        reasons.append("insufficient_useful_work")
    quality = max(0.0, 1 - rms / task.position_tolerance) * max(0.0, 1 - speed_error / task.speed_tolerance)
    return dict(
        passed=not reasons,
        score=quality if not reasons else 0.0,
        reasons=reasons,
        rms_position_error=rms,
        peak_position_error=peak,
        relative_velocity_rmse=speed_error,
        input_travel=travel,
        max_penetration_mm=run["max_penetration_mm"],
        measured_ratio=measured_ratio,
        relative_ratio_error=ratio_error,
        max_guidance_error_mm=run["max_guidance_error_mm"],
        max_tilt_rad=run["max_tilt_rad"],
        max_closure_mm=run["max_closure_mm"],
        motor_work_j=run["motor_work_j"],
        load_work_j=run["load_work_j"],
        worst_contact=run["worst_contact"],
    )


def evaluate_dynamics(task: Task, geometry: Geometry, output: Path):
    from .io import write_json, digest

    results = []
    visual_runs = []
    for trial in task.trials:
        coarse = simulate(task, geometry, trial)
        fine = simulate(task, geometry, trial, task.timestep / 2)
        coarse_metrics, fine_metrics = (
            metrics(task, geometry, trial, coarse),
            metrics(task, geometry, trial, fine),
        )
        a, b = np.asarray(coarse["trace"]), np.asarray(fine["trace"])
        interpolated = np.interp(a[:, 0], b[:, 0], b[:, 2])
        convergence = float(np.sqrt(np.mean((a[:, 2] - interpolated) ** 2)))
        converged = convergence <= task.position_tolerance / 2
        results.append(
            dict(
                name=trial.name,
                passed=coarse_metrics["passed"] and fine_metrics["passed"] and converged,
                coarse=coarse_metrics,
                fine=fine_metrics,
                convergence_rmse=convergence,
                converged=converged,
                trace_sha256=digest(coarse["trace"]),
                fine_trace_sha256=digest(fine["trace"]),
            )
        )
        for suffix, run in [("", coarse), ("-halfstep", fine)]:
            write_json(output / f"trace-{trial.name}{suffix}.json", run["trace"])
        (output / f"model-{trial.name}.xml").write_text(coarse["xml"], encoding="utf-8")
        visual_runs.append(dict(name=trial.name, frames=coarse["frames"]))
        if not fine_metrics["passed"] or not converged:
            visual_runs.append(dict(name=trial.name + "_halfstep", frames=fine["frames"]))
    return results, visual_runs
