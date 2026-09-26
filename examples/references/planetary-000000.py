import sys, json, math
from kinematiccad.schema import Task
from kinematiccad.sdk import Part, box, cylinder, prism, transform, export

def gear_cells(teeth, module, width=6, backlash=0.12, phase=0.0, internal=False):
    teeth = int(teeth)
    pitch = teeth * module / 2
    alpha = math.radians(20)
    base = pitch * math.cos(alpha)
    inv_pitch = math.tan(alpha) - alpha

    def inv(radius):
        phi = math.acos(min(1.0, base / radius))
        return math.tan(phi) - phi

    if internal:
        root, tip = pitch + 1.25 * module, pitch - module
        outer = root + 3.5
        count = teeth * 3
        # Overlapping sectors provide a connected, watertight ring.
        cells = []
        for i in range(count):
            a, b = 2 * math.pi * i / count - 0.00002, 2 * math.pi * (i + 1) / count + 0.00002
            cells.append(
                prism(
                    [
                        (r * math.cos(t), r * math.sin(t))
                        for r, t in [(root, a), (outer, a), (outer, b), (root, b)]
                    ],
                    width,
                )
            )
        radii = [tip + (root - tip) * i / 7 for i in range(8)]

        def half(r):
            return math.pi / (2 * teeth) - backlash / (2 * pitch) + inv(r) - inv_pitch
    else:
        root, tip = pitch - 1.25 * module, pitch + module
        cells = [cylinder(root, width, segments=min(120, teeth * 4))]
        radii = [root, max(root, base)] + [
            max(root, base) + (tip - max(root, base)) * i / 7 for i in range(1, 8)
        ]

        def half(r):
            return math.pi / (2 * teeth) - backlash / (2 * pitch) + inv_pitch - inv(r)

    outline = [
        (r * math.cos(sign * half(r)), r * math.sin(sign * half(r)))
        for sign, samples in [(1, radii), (-1, list(reversed(radii)))]
        for r in samples
    ]
    # Extend teeth slightly into the core/ring to avoid a disconnected tangency.
    if not internal:
        outline += [
            (root * 0.985 * math.cos(half(root)), root * 0.985 * math.sin(half(root))),
            (root * 0.985 * math.cos(half(root)), -root * 0.985 * math.sin(half(root))),
        ]
    else:
        outline += [
            (root * 1.002 * math.cos(half(root)), root * 1.002 * math.sin(half(root))),
            (root * 1.002 * math.cos(half(root)), -root * 1.002 * math.sin(half(root))),
        ]
    for i in range(teeth):
        cells.append(transform(prism(outline, width), phase + 2 * math.pi * i / teeth))
    return cells

def reference_parts(task: Task) -> list[Part]:
    p = task.parameters
    if task.family == "spur":
        return [
            Part.from_cells("input", gear_cells(p["teeth_in"], p["module"], backlash=p["backlash"])),
            Part.from_cells(
                "output",
                gear_cells(
                    p["teeth_out"],
                    p["module"],
                    backlash=p["backlash"],
                    phase=math.pi + math.pi / p["teeth_out"],
                ),
            ),
        ]
    if task.family == "slider_crank":
        r, length = p["radius"], p["length"]
        return [
            Part.from_cells("crank", [box(r + 6, 6, 4, (r / 2, 0, 0))]),
            Part.from_cells("rod", [box(length + 6, 6, 4, (length / 2, 0, 0))]),
            Part.from_cells("slider", [box(12, 12, 4)]),
        ]
    if task.family == "cam":
        return [
            Part.from_cells("cam", [cylinder(p["radius"], 6, (0, p["eccentricity"], 0), segments=120)]),
            Part.from_cells("follower", [box(2 * p["radius"] + 2, 4, 6)]),
        ]
    if task.family == "linear":
        return [
            Part.from_cells("carriage", [box(12, 8, 6)]),
            Part.from_cells(
                "guide",
                [
                    box(100, 12.4, 2, (0, 0, -4.2)),
                    box(100, 2, 9.2, (0, -5.2, -0.6)),
                    box(100, 2, 9.2, (0, 5.2, -0.6)),
                ],
            ),
        ]
    if task.family == "planetary":
        ns, np_, nr, m = [p[k] for k in ("teeth_sun", "teeth_planet", "teeth_ring", "module")]
        orbit = (ns + np_) * m / 2
        return [
            Part.from_cells("sun", gear_cells(ns, m, backlash=p["backlash"])),
            Part.from_cells("carrier", [box(orbit + 6, 6, 4, (orbit / 2, 0, 0))]),
            Part.from_cells(
                "planet", gear_cells(np_, m, backlash=p["backlash"], phase=math.pi + math.pi / np_)
            ),
            Part.from_cells("ring", gear_cells(nr, m, backlash=p["ring_backlash"], internal=True)),
        ]
    raise ValueError(task.family)

task=Task.model_validate(json.loads('{"bodies":[{"axis":[0.0,0.0,1.0],"damping":1e-05,"density":1200.0,"envelope":[20.0,20.0,4.0],"joint":"hinge","max_volume":1000000.0,"min_volume":10.0,"mounts":[[0.0,0.0,0.0]],"name":"sun","parent":"world","pos":[0.0,0.0,0.0]},{"axis":[0.0,0.0,1.0],"damping":1e-05,"density":1200.0,"envelope":[33.0,6.0,2.0],"joint":"hinge","max_volume":1000000.0,"min_volume":10.0,"mounts":[[0.0,0.0,0.0],[28.0,0.0,0.0]],"name":"carrier","parent":"world","pos":[0.0,0.0,7.0]},{"axis":[0.0,0.0,1.0],"damping":1e-05,"density":1200.0,"envelope":[16.0,16.0,4.0],"joint":"hinge","max_volume":1000000.0,"min_volume":10.0,"mounts":[[0.0,0.0,0.0]],"name":"planet","parent":"carrier","pos":[28.0,0.0,-7.0]},{"axis":[0.0,0.0,1.0],"damping":1e-05,"density":1200.0,"envelope":[47.0,47.0,4.0],"joint":"fixed","max_volume":1000000.0,"min_volume":10.0,"mounts":[[44.0,0.0,0.0]],"name":"ring","parent":"world","pos":[0.0,0.0,0.0]}],"clearances":[{"a":"sun","b":"planet","maximum_mm":0.35,"minimum_mm":0.003},{"a":"planet","b":"ring","maximum_mm":0.35,"minimum_mm":0.003},{"a":"carrier","b":"planet","maximum_mm":3.0,"minimum_mm":1.0}],"connections":[],"description":"Design a one-planet epicyclic train: sun 16, planet 12, fixed internal ring 40 teeth, module 2.0 mm, pressure angle 20 degrees. Drive the sun; the carrier output must obey Willis\' relation through tooth contacts.","driver":"sun","duration":10.7,"family":"planetary","format":"kcb-task-1","id":"planetary-000000","max_closure_mm":0.12,"max_guidance_error_mm":0.5,"max_penetration_mm":0.08,"max_tilt_rad":0.03,"minimum_travel":22.091148575128553,"motor_kv":0.005,"motor_limit":0.004,"output":"carrier","parameters":{"backlash":0.14,"module":2.0,"ratio":0.2857142857142857,"ring_backlash":0.3,"teeth_planet":12.0,"teeth_ring":40.0,"teeth_sun":16.0,"width":6.0},"position_tolerance":0.07,"ratio_tolerance":0.005,"seed":0,"speed_tolerance":0.2,"timestep":0.0005,"trials":[{"force":0.002,"load":0.0002,"name":"forward","speed":3.0},{"force":0.002,"load":0.0004,"name":"reverse_loaded","speed":-2.7}],"warmup":0.3}'))
export(reference_parts(task),sys.argv[1])
