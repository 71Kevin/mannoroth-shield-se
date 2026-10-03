"""Build the Mannoroth Shield meshes: subdivided body, glowing eyes, iron shield grip, third- and first-person models per size.

blender --background --factory-startup --python build_meshes.py -- <base.nif> <iron_shield.nif> <meshes_out_dir> <report.json>
    [--crease 50] [--levels 2] [--sizes small=0.8,medium=1.0,large=1.25] [--eyes eye_socket.json]

<base.nif> is the welded SE conversion of the original mesh at scale 1 (nif_le_to_se_rigid.py); <iron_shield.nif> is the
vanilla meshes\\armor\\iron\\shield.nif, whose handle is reused. Third-person models keep the original placement and get
the handle at the hand, its feet stretched to the back of the shield. First-person models turn the body in its own plane,
centre it on the handle, push it outwards, then tilt, scale and shift it per size (FIRST_PERSON) so its rim shows at
the lower left at rest while its back stays in front of the camera when blocking; they leave out the curled plate at
the lower edge, which wraps back towards the arm and would sit in front of the camera.
The skull's eye sockets share one area of the texture (eye_socket.json); the triangles there become a separate shape with
the glow shader, the fel fire glow map and a looping emissive flicker, as vanilla glowing weapons do. Each socket also
gets fel fire: two layers of crossed flame cards rising out of it (the vanilla scrolling fire tile tinted fel green,
scrolling and flickering) and a soft green halo, all additive effect-shader shapes.
"""
import json
import math
import os
import sys
from collections import defaultdict

import bmesh
import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
base_path, iron_path, out_dir, report_path = argv[:4]
opts = dict(zip(argv[4::2], argv[5::2]))
crease_angle = float(opts.get("--crease", 50))
levels = int(opts.get("--levels", 2))
sizes = [(k, float(v)) for k, v in (s.split("=") for s in opts.get("--sizes", "small=0.8,medium=1.0,large=1.25").split(","))]
eyes = json.load(open(opts.get("--eyes", os.path.join(os.path.dirname(os.path.abspath(__file__)), "eye_socket.json"))))

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.preferences.addon_enable(module="io_scene_nifly")
from io_scene_nifly.pyn.pynifly import NifFile  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import nif_rigid_lib as lib  # noqa: E402

GRIP_CENTER = np.array([0.6, 0.0])
FOOT_TOP = -2.0
EMBED = 0.5
FP_DEPTH = -8.0
FIRST_PERSON = {
    "small": dict(rotation=85.0, tilt_x=4.0, tilt_y=0.0, scale=0.97, shift=(-0.9, 0.9, 2.5)),
    "medium": dict(rotation=97.5, tilt_x=21.0, tilt_y=2.5, scale=0.89, shift=(1.4, 1.9, -1.7)),
    "large": dict(rotation=93.0, tilt_x=7.0, tilt_y=0.0, scale=0.96, shift=(3.0, 0.87, -0.9)),
}
FP_HIDDEN_UV = (0.5, 0.78)
EYE_MARGIN = 1.3
FLAME_UP = np.array([-0.62, 0.72, -0.31])
FLAME_STATIONS = 8
FLAME_COLUMNS = np.array([-1.0, -0.5, 0.0, 0.5, 1.0])
FLAME_TEXTURES = {"Diffuse": r"textures\effects\fxfirescrolltile02.dds"}
FLAME_LAYERS = [
    dict(name="Flames", width=1.3, length=2.5, alpha=0.9, u=0.0, v_repeat=1.0, scroll=1.7, mult=3.0,
         color=(0.25, 1.0, 0.08, 1.0)),
    dict(name="FlameCore", width=0.7, length=1.6, alpha=1.0, u=0.37, v_repeat=1.4, scroll=1.1, mult=3.2,
         color=(0.62, 1.0, 0.3, 1.0)),
]
FLAME_FLICKER = [(0.0, 1.0), (0.23, 0.82), (0.41, 0.97), (0.62, 0.86), (0.85, 1.0), (1.06, 0.8), (1.3, 0.95),
                 (1.52, 0.84), (1.75, 1.0)]
HALO_TEXTURES = {"Diffuse": r"textures\effects\GlowSoft01.dds"}
HALO_RADIUS = 0.9
HALO_COLOR = (0.3, 1.0, 0.12, 1.0)
HALO_MULT = 1.6
EFFECT_BASE = dict(Shader_Flags_2=0x30, falloffStartAngle=0.866, falloffStopAngle=0.174, falloffStartOpacity=1.0,
                   falloffStopOpacity=0.0, textureClampMode=3, UV_Scale_U=1.0, UV_Scale_V=1.0, UV_Offset_U=0.0,
                   UV_Offset_V=0.0, LightingInfluence=255)
FLAME_FLAGS = 0xC0000048
HALO_FLAGS = 0xC0000048
EMISSIVE_MULTIPLE, V_OFFSET = 0, 8
GLOW_TEXTURE = r"textures\weapons\mannoroth\Mannoroth Shield_g.dds"
GLOW_SHADER = 2
ENVIRONMENT_MAPPING = 0x80
GLOW_MAP = 0x40
BSX_ANIMATED = 0x1
EYE_EMISSIVE_MULT = 2.0
EYE_FLICKER = [
    (0.0, (1.0, 1.0, 1.0)), (0.35, (0.8, 0.86, 0.8)), (0.6, (0.95, 0.97, 0.94)), (1.05, (0.74, 0.82, 0.76)),
    (1.4, (0.97, 0.99, 0.95)), (1.85, (0.82, 0.88, 0.82)), (2.15, (1.0, 1.0, 0.97)), (2.65, (0.76, 0.84, 0.78)),
    (2.95, (0.92, 0.95, 0.92)), (3.2, (1.0, 1.0, 1.0)),
]

base = NifFile(base_path)
bshape = base.shapes[0]
body_textures = {slot: tex for slot, tex in bshape.textures.items() if tex}
base_bsx = next(int(ed.properties.integerData) for ed in base.root.extra_data() if ed.blockname == "BSXFlags")
report = {"crease": crease_angle, "levels": levels, "sizes": {}}


def subdivided_body():
    me = bpy.data.meshes.new("body")
    me.from_pydata([Vector(v) for v in bshape.verts], [], [tuple(t) for t in bshape.tris])
    uv_layer = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            u, v = bshape.uvs[me.loops[li].vertex_index]
            uv_layer.data[li].uv = (u, 1.0 - v)
    ob = bpy.data.objects.new("body", me)
    bpy.context.scene.collection.objects.link(ob)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-4)
    bmesh.ops.join_triangles(bm, faces=bm.faces[:], angle_face_threshold=math.radians(12),
                             angle_shape_threshold=math.radians(35), cmp_seam=False, cmp_sharp=False, cmp_uvs=True)
    crease = bm.edges.layers.float.new("crease_edge")
    for e in bm.edges:
        if len(e.link_faces) != 2 or e.calc_face_angle(0) > math.radians(crease_angle):
            e[crease] = 1.0
    bm.to_mesh(me)
    bm.free()
    mod = ob.modifiers.new("subdivision", "SUBSURF")
    mod.levels = mod.render_levels = levels
    mod.uv_smooth = "PRESERVE_BOUNDARIES"
    mod.boundary_smooth = "PRESERVE_CORNERS"
    mod.use_creases = True
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier="subdivision")
    me.set_sharp_from_angle(angle=math.radians(crease_angle))
    me.calc_loop_triangles()
    uv_layer = me.uv_layers.active.data
    normals = me.corner_normals
    keys, pos, uvs, nrm, tris = {}, [], [], [], []
    for lt in me.loop_triangles:
        tri = []
        for li in lt.loops:
            vi = me.loops[li].vertex_index
            u, v = uv_layer[li].uv
            n = normals[li].vector
            key = (vi, round(u, 5), round(v, 5), round(n.x, 3), round(n.y, 3), round(n.z, 3))
            idx = keys.get(key)
            if idx is None:
                idx = len(pos)
                keys[key] = idx
                pos.append(me.vertices[vi].co[:])
                uvs.append((u, 1.0 - v))
                nrm.append((n.x, n.y, n.z))
            tri.append(idx)
        tris.append(tri)
    return np.array(pos), np.array(tris), np.array(uvs), np.array(nrm)


def iron_grip():
    iron = NifFile(iron_path)
    s = iron.shapes[0]
    V = np.array(s.verts) + np.array(s.transform.translation)
    T = np.array(s.tris)
    parent = list(range(len(V)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    groups = defaultdict(list)
    for i, k in enumerate(map(tuple, np.round(V, 3))):
        groups[k].append(i)
    for idx in groups.values():
        for j in idx[1:]:
            parent[find(idx[0])] = find(j)
    for a, b, c in T:
        parent[find(a)] = find(b)
        parent[find(b)] = find(c)
    comp = np.array([find(i) for i in range(len(V))])
    roots, counts = np.unique(comp, return_counts=True)
    handle = roots[np.argmin(counts)]
    keep = np.where(comp == handle)[0]
    remap = -np.ones(len(V), dtype=np.int64)
    remap[keep] = np.arange(len(keep))
    tris = np.array([remap[t] for t in T if comp[t[0]] == handle])
    textures = {slot: path for slot, path in s.textures.items() if path}
    return V[keep], tris, np.array(s.uvs)[keep], np.array(s.normals)[keep], s.shader.properties, s.flags, textures


def loose_parts(verts, tris):
    """Connected part of each vertex (vertices at the same position count as connected)."""
    parent = list(range(len(verts)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    by_position = defaultdict(list)
    for i, k in enumerate(map(tuple, np.round(verts, 4))):
        by_position[k].append(i)
    for group in by_position.values():
        for j in group[1:]:
            parent[find(group[0])] = find(j)
    for a, b, c in tris:
        parent[find(a)] = find(b)
        parent[find(b)] = find(c)
    return np.array([find(i) for i in range(len(verts))])


def first_person_hidden(verts, tris, uvs):
    """Triangles of the loose parts textured only from the lower right of the texture: the curled plate at the
    lower edge wraps back towards the arm, and in first person it sits in front of the camera over the back of the
    shield. First person only ever shows the back, so the first-person models leave it out."""
    part = loose_parts(verts, tris)
    hidden = [p for p in np.unique(part)
              if (uvs[part == p][:, 0] >= FP_HIDDEN_UV[0]).all() and (uvs[part == p][:, 1] >= FP_HIDDEN_UV[1]).all()]
    return np.isin(part[tris[:, 0]], hidden)


def eye_triangles(tris, uvs):
    centre = uvs[tris].mean(axis=1)
    d = ((centre - np.array(eyes["uv_center"])) / np.array(eyes["uv_radius"])) ** 2
    return d.sum(axis=1) <= EYE_MARGIN ** 2


def subset(verts, tris, uvs, normals, keep):
    used = np.unique(tris[keep])
    remap = -np.ones(len(verts), dtype=np.int64)
    remap[used] = np.arange(len(used))
    return verts[used], remap[tris[keep]], uvs[used], normals[used]


def first_hit_z(V, T, points):
    v0, v1, v2 = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    e1, e2 = v1 - v0, v2 - v0
    d = np.array([0.0, 0.0, -1.0])
    p = np.cross(d, e2)
    det = np.einsum("ij,ij->i", e1, p)
    ok = np.abs(det) > 1e-9
    inv = np.where(ok, 1.0 / np.where(ok, det, 1), 0)
    out = []
    for x, y in points:
        o = np.array([x, y, 200.0])
        s = o - v0
        u = np.einsum("ij,ij->i", s, p) * inv
        q = np.cross(s, e1)
        v = np.einsum("j,ij->i", d, q) * inv
        t = np.einsum("ij,ij->i", e2, q) * inv
        hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0)
        out.append(200.0 - t[hit].min() if hit.any() else None)
    return out


def fitted_grip(grip_v, body_v, body_t):
    """Stretch the handle's feet (below FOOT_TOP) so they end just inside the back of the body."""
    out = grip_v.copy()
    feet = np.where(grip_v[:, 2] < FOOT_TOP)[0]
    lowest = grip_v[feet, 2].min()
    hits = first_hit_z(body_v, body_t, grip_v[feet, :2])
    stretched = 0
    for i, z_surface in zip(feet, hits):
        if z_surface is None:
            continue
        target = z_surface - EMBED
        out[i, 2] = FOOT_TOP + (grip_v[i, 2] - FOOT_TOP) * (FOOT_TOP - target) / (FOOT_TOP - lowest)
        stretched += 1
    return out, stretched


def first_person(body, scale, p):
    """The first-person placement of one size as a function of (points, normals): the body turned in its own plane,
    centred on the handle, pushed outwards, tilted and scaled around the handle and shifted."""
    c, s = math.cos(math.radians(p["rotation"])), math.sin(math.radians(p["rotation"]))
    turn = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    tx, ty = math.radians(p["tilt_x"]), math.radians(p["tilt_y"])
    rx = np.array([[1.0, 0.0, 0.0], [0.0, math.cos(tx), -math.sin(tx)], [0.0, math.sin(tx), math.cos(tx)]])
    ry = np.array([[math.cos(ty), 0.0, math.sin(ty)], [0.0, 1.0, 0.0], [-math.sin(ty), 0.0, math.cos(ty)]])
    tilt = ry @ rx
    offset = np.array([*(GRIP_CENTER - (body @ turn.T)[:, :2].mean(0)), FP_DEPTH * scale])
    pivot = np.array([GRIP_CENTER[0], GRIP_CENTER[1], 0.0])
    shift = np.array(p["shift"]) * scale

    def apply(points, normals):
        placed = (points @ turn.T + offset - pivot) @ tilt.T * p["scale"] + pivot + shift
        return placed, normals @ (tilt @ turn).T

    return apply


def eye_sockets(verts, tris, uvs, normals, is_eye):
    """Centre, outward normal and size of each eye socket: the eye triangles split into connected patches, each
    weighted towards the socket centre in the texture."""
    used = np.unique(tris[is_eye])
    parent = {int(i): int(i) for i in used}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    by_position = defaultdict(list)
    for i in used:
        by_position[tuple(np.round(verts[i], 4))].append(int(i))
    for group in by_position.values():
        for j in group[1:]:
            parent[find(group[0])] = find(j)
    for a, b, c in tris[is_eye]:
        parent[find(int(a))] = find(int(b))
        parent[find(int(b))] = find(int(c))
    patches = defaultdict(list)
    for i in used:
        patches[find(int(i))].append(int(i))
    sockets = []
    for idx in sorted(patches.values(), key=len, reverse=True)[:2]:
        idx = np.array(idx)
        d = (((uvs[idx] - np.array(eyes["uv_center"])) / np.array(eyes["uv_radius"])) ** 2).sum(axis=1)
        w = np.clip(1.0 - d, 0.0, None)
        if w.sum() == 0:
            continue
        centre = (verts[idx] * w[:, None]).sum(0) / w.sum()
        normal = (normals[idx] * w[:, None]).sum(0)
        normal /= np.linalg.norm(normal)
        size = 2.0 * math.sqrt((w * ((verts[idx] - centre) ** 2).sum(axis=1)).sum() / w.sum())
        sockets.append({"centre": centre, "normal": normal, "size": size})
    return sockets


def grid_tris(rows, cols, start):
    out = []
    for r in range(rows - 1):
        for c in range(cols - 1):
            a = start + r * cols + c
            out += [(a, a + 1, a + cols), (a + 1, a + cols + 1, a + cols)]
    return out


def flame_cards(sockets, layer):
    """Three crossed flame cards per socket, following a curve that leaves the socket along its normal and bends up;
    width and vertex alpha taper towards the tip and the edges, the texture runs along the length."""
    up = FLAME_UP / np.linalg.norm(FLAME_UP)
    verts, tris, uvs, normals, colors = [], [], [], [], []
    for sock in sockets:
        n, size = sock["normal"], sock["size"]
        length, width = layer["length"] * size, layer["width"] * size
        p0 = sock["centre"] + n * 0.15 * size
        p1 = p0 + n * 0.45 * length
        p2 = p0 + n * 0.3 * length + up * length
        side = np.cross(up, n)
        side /= np.linalg.norm(side)
        for k in range(3):
            theta = math.pi * k / 3
            start = len(verts)
            for i in range(FLAME_STATIONS + 1):
                s = i / FLAME_STATIONS
                q = (1 - s) ** 2 * p0 + 2 * (1 - s) * s * p1 + s ** 2 * p2
                t = 2 * (1 - s) * (p1 - p0) + 2 * s * (p2 - p1)
                t /= np.linalg.norm(t)
                b = side - np.dot(side, t) * t
                b /= np.linalg.norm(b)
                wdir = math.cos(theta) * b + math.sin(theta) * np.cross(t, b)
                half = 0.5 * width * (1 - s ** 1.6) * (0.75 + 0.25 * math.sin(math.pi * s)) + 0.02 * size
                profile = min(1.0, 0.4 + s / 0.18) * (1 - s) ** 1.1
                card_normal = np.cross(t, wdir)
                for x in FLAME_COLUMNS:
                    verts.append(q + wdir * x * half)
                    uvs.append((layer["u"] + 0.5 + 0.22 * x, s * layer["v_repeat"]))
                    normals.append(card_normal)
                    colors.append((1.0, 1.0, 1.0, layer["alpha"] * (1 - x * x) * profile))
            tris += grid_tris(FLAME_STATIONS + 1, len(FLAME_COLUMNS), start)
    return np.array(verts), np.array(tris), np.array(uvs), np.array(normals), np.array(colors)


def halos(sockets, segments=16):
    verts, tris, uvs, normals, colors = [], [], [], [], []
    for sock in sockets:
        n, size = sock["normal"], sock["size"]
        a = np.cross(n, [0.0, 0.0, 1.0] if abs(n[2]) < 0.9 else [1.0, 0.0, 0.0])
        a /= np.linalg.norm(a)
        b = np.cross(n, a)
        centre = sock["centre"] + n * 0.12 * size
        start = len(verts)
        verts.append(centre)
        uvs.append((0.5, 0.5))
        for k in range(segments):
            ang = 2 * math.pi * k / segments
            verts.append(centre + (a * math.cos(ang) + b * math.sin(ang)) * HALO_RADIUS * size)
            uvs.append((0.5 + 0.5 * math.cos(ang), 0.5 + 0.5 * math.sin(ang)))
        for k in range(segments):
            tris.append((start, start + 1 + k, start + 1 + (k + 1) % segments))
        normals += [n] * (segments + 1)
        colors += [(1.0, 1.0, 1.0, 1.0)] * (segments + 1)
    return np.array(verts), np.array(tris), np.array(uvs), np.array(normals), np.array(colors)


def fel_fire(sockets):
    """The flame layers and the halo as (name suffix, geometry, shader settings, textures, controller channels)."""
    parts = []
    for layer in FLAME_LAYERS:
        settings = dict(EFFECT_BASE, Shader_Flags_1=FLAME_FLAGS, Emissive_Color=layer["color"],
                        Emissive_Mult=layer["mult"], softFalloffDepth=3.0)
        channels = [(V_OFFSET, [(0.0, 1.0), (layer["scroll"], 0.0)]),
                    (EMISSIVE_MULTIPLE, [(t, layer["mult"] * f) for t, f in FLAME_FLICKER])]
        parts.append((layer["name"], flame_cards(sockets, layer), settings, FLAME_TEXTURES, channels))
    settings = dict(EFFECT_BASE, Shader_Flags_1=HALO_FLAGS, Emissive_Color=HALO_COLOR, Emissive_Mult=HALO_MULT,
                    softFalloffDepth=2.0, textureClampMode=0)
    parts.append(("Halo", halos(sockets), settings, HALO_TEXTURES,
                  [(EMISSIVE_MULTIPLE, [(t, HALO_MULT * f) for t, f in FLAME_FLICKER])]))
    return parts


def transformed(parts, apply):
    out = []
    for name, (v, t, uv, n, col), settings, textures, channels in parts:
        tv, tn = apply(v, n)
        out.append((name, (tv, t, uv, tn, col), settings, textures, channels))
    return out


def scaled(parts, scale):
    return [(name, (v * scale, t, uv, n, col), settings, textures, channels)
            for name, (v, t, uv, n, col), settings, textures, channels in parts]


def glow_shader(src):
    shader = type(src)()
    lib.copy_shader(src, shader)
    shader.Shader_Type = shader.bslspShaderType = GLOW_SHADER
    shader.Shader_Flags_1 &= ~ENVIRONMENT_MAPPING
    shader.Shader_Flags_2 |= GLOW_MAP
    shader.Emissive_Color[:] = (*EYE_FLICKER[0][1], 1.0)
    shader.Emissive_Mult = EYE_EMISSIVE_MULT
    return shader


def write_nif(path, root_name, body, eyes_part, fire, grip, collision_points, mass):
    nif = NifFile()
    nif.initialize("SKYRIMSE", path, root_type="BSFadeNode", root_name=root_name)
    root = nif.root
    root.flags = base.root.flags
    lib.copy_root_extra_data(base.root, nif, root, bsx_flags=base_bsx | BSX_ANIMATED)
    lib.add_shape(nif, root, root_name + ":0", *body, bshape.flags, bshape.shader.properties, body_textures)
    eye_textures = {"Diffuse": body_textures["Diffuse"], "Normal": body_textures["Normal"], "Glow": GLOW_TEXTURE}
    eye_shape = lib.add_shape(nif, root, root_name + "Eyes:0", *eyes_part, bshape.flags, eye_shader, eye_textures)
    lib.add_emissive_loop(nif, eye_shape, EYE_FLICKER)
    for part, geometry, settings, textures, channels in fire:
        shape = lib.add_effect_shape(nif, root, root_name + part + ":0", *geometry, settings, textures)
        lib.add_effect_float_controllers(nif, shape, channels)
    lib.add_shape(nif, root, root_name + "Grip:0", *grip)
    info = lib.add_convex_collision(root, collision_points, base.root.collision_object, mass, calibration, 48)
    nif.save()
    return info


body_v, body_t, body_uv, body_n = subdivided_body()
is_eye = eye_triangles(body_t, body_uv)
fp_hidden = first_person_hidden(body_v, body_t, body_uv)
sockets = eye_sockets(body_v, body_t, body_uv, body_n, is_eye)
fire_parts = fel_fire(sockets)
grip_v, grip_t, grip_uv, grip_n, grip_shader, grip_flags, grip_tex = iron_grip()
eye_shader = glow_shader(bshape.shader.properties)
calibration = lib.inertia_calibration(base.root.collision_object.body)
base_mass = float(base.root.collision_object.body.properties.mass)
report["body"] = {"verts": len(body_v), "tris": len(body_t), "eye_tris": int(is_eye.sum()),
                  "first_person_hidden_tris": int(fp_hidden.sum())}
report["eye_sockets"] = [{k: np.round(v, 3).tolist() for k, v in s.items()} for s in sockets]
report["fel_fire"] = {name: {"verts": len(g[0]), "tris": len(g[1])} for name, g, _, _, _ in fire_parts}
report["grip"] = {"verts": len(grip_v), "tris": len(grip_t), "textures": grip_tex}
report["first_person"] = {"depth": FP_DEPTH, "sizes": FIRST_PERSON}
os.makedirs(out_dir, exist_ok=True)

for name, scale in sizes:
    suffix = "" if name == "medium" else "_" + name
    sv = body_v * scale
    mass = round(base_mass * scale ** 3, 2)
    grip = (grip_v, grip_t, grip_uv, grip_n, grip_flags, grip_shader, grip_tex)
    fire3 = scaled(fire_parts, scale)

    grip3, stretched = fitted_grip(grip_v, sv, body_t)
    third = os.path.join(out_dir, "mannorothshield%s.nif" % suffix)
    coll3 = write_nif(third, "MannorothShield", subset(sv, body_t, body_uv, body_n, ~is_eye),
                      subset(sv, body_t, body_uv, body_n, is_eye), fire3, (grip3,) + grip[1:], sv, mass)

    place = first_person(sv, scale, FIRST_PERSON[name])
    fv, fn = place(sv, body_n)
    first = os.path.join(out_dir, "1stpersonmannorothshield%s.nif" % suffix)
    write_nif(first, "1stPersonMannorothShield", subset(fv, body_t, body_uv, fn, ~is_eye & ~fp_hidden),
              subset(fv, body_t, body_uv, fn, is_eye), transformed(fire3, place), grip, fv, mass)

    report["sizes"][name] = {"scale": scale, "third_person": os.path.basename(third), "first_person": os.path.basename(first),
                             "grip_feet_stretched": stretched, "collision": coll3,
                             "bounds": lib.bounds(np.vstack([sv, grip3] + [g[0] for _, g, _, _, _ in fire3]))}
    print("MESHES:", name, os.path.basename(third), os.path.basename(first), report["sizes"][name]["bounds"]["obnd"])

with open(report_path, "w") as fh:
    json.dump(report, fh, indent=2)
