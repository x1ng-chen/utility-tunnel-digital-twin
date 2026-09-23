"""Exact triangle/prism clearance check for a flat annular floor (Blender).

Clip each low equipment triangle against the XY footprint of actual floor-top
triangles. Unlike a bounding box or vertex-only test, this respects the hole
and detects long faces crossing the slab with all vertices outside it.
Units are inherited scene units, not certified construction dimensions.
"""
import math
from mathutils import Vector

TOLERANCE = 1e-5
EXEMPT = {
    'MESH_RING_FLOOR': 'Reference slab itself',
    'MESH_BASE_01': 'Designed foundation below the reference slab',
    'GEO_UT_RING_RENDER_GROUND': 'Presentation ground below foundation',
}


def bounds(obj):
    points = [obj.matrix_world @ Vector(p) for p in obj.bound_box]
    return [[min(p[i] for p in points) for i in range(3)],
            [max(p[i] for p in points) for i in range(3)]]


def clip(poly, distance):
    result = []
    if not poly:
        return result
    previous = poly[-1]
    dp = distance(previous)
    for point in poly:
        dc = distance(point)
        if (dc >= 0) != (dp >= 0):
            result.append(previous + (point - previous) * (dp / (dp - dc)))
        if dc >= 0:
            result.append(point)
        previous, dp = point, dc
    return result


def audit(objects):
    floor = objects['MESH_RING_FLOOR']
    top = bounds(floor)[1][2]
    floor.data.calc_loop_triangles()
    grid = {}
    cell = .05

    def cells(points):
        xmin, xmax = [math.floor(f(p.x for p in points) / cell) for f in (min, max)]
        ymin, ymax = [math.floor(f(p.y for p in points) / cell) for f in (min, max)]
        return [(x, y) for x in range(xmin, xmax + 1) for y in range(ymin, ymax + 1)]

    tops = []
    for tri in floor.data.loop_triangles:
        ps = [floor.matrix_world @ floor.data.vertices[i].co for i in tri.vertices]
        if all(abs(p.z - top) < TOLERANCE for p in ps):
            if (ps[1] - ps[0]).cross(ps[2] - ps[0]).z < 0:
                ps.reverse()
            idx = len(tops)
            tops.append(ps)
            for key in cells(ps):
                grid.setdefault(key, []).append(idx)
    assert tops, 'Floor is not a supported flat slab'
    findings = []
    checked = 0
    for obj in objects:
        if obj.type != 'MESH' or obj.name in EXEMPT:
            continue
        checked += 1
        if bounds(obj)[0][2] >= top - TOLERANCE:
            continue
        obj.data.calc_loop_triangles()
        vertices = [obj.matrix_world @ v.co for v in obj.data.vertices]
        depth = 0
        count = 0
        for tri in obj.data.loop_triangles:
            ps = [vertices[i] for i in tri.vertices]
            low = clip(ps, lambda p: top - TOLERANCE - p.z)
            if not low:
                continue
            ids = {i for key in cells(low) for i in grid.get(key, [])}
            hit = False
            for idx in ids:
                intersection = low
                ts = tops[idx]
                for a, b in zip(ts, ts[1:] + ts[:1]):
                    intersection = clip(intersection, lambda p: (b.x-a.x)*(p.y-a.y)-(b.y-a.y)*(p.x-a.x))
                    if not intersection:
                        break
                if intersection:
                    d = top - min(p.z for p in intersection)
                    if d > TOLERANCE * 1.01:
                        depth = max(depth, d)
                        hit = True
            count += hit
        if count:
            findings.append({'name': obj.name, 'intersectingTriangles': count,
                             'maximumDepth': depth, 'bounds': bounds(obj)})
    return {'method': 'triangle clipping against actual floor-top triangular prisms',
            'floorTop': top, 'tolerance': TOLERANCE, 'topTriangles': len(tops),
            'checkedMeshes': checked, 'exceptions': EXEMPT,
            'findings': findings, 'status': 'PASS' if not findings else 'FAIL'}
