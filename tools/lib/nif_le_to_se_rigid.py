"""Convert a rigid (unskinned, single-shape) Skyrim LE mesh to Skyrim SE: weapons, shields, clutter.

blender --background --factory-startup --python nif_le_to_se_rigid.py -- <src.nif> <out.nif> [options]
  --scale S           uniform scale around the node origin, i.e. the attach point (default 1.0)
  --angle A           smoothing angle in degrees for the rebuilt normals (default 60)
  --keep-normals      keep the source normals instead of rebuilding them from the faces
  --hull-max N        maximum vertices of the regenerated convex collision (default 48)
  --root-name NAME    root node name (default: the source's)
  --shape-name NAME   shape name (default: the source's)
  --tex SLOT=PATH     texture override, repeatable (Diffuse, Normal, Glow, EnvMap, EnvMask, Specular)
  --report FILE       JSON report: counts, bounds (for OBND), collision

The source is welded (it is often a triangle soup) and its normals rebuilt, texture paths are made relative to
Data, root extra data (BSXFlags, BSInvMarker, NiStringExtraData such as Prn) and the rigid body settings are
carried over. When the source has convex collision, a convex hull of the new mesh replaces it, with centre of
mass and inertia recomputed (inertia calibrated against the source body).
"""
import json
import math
import os
import sys

import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
src_path, out_path = argv[:2]
opts = {}
tex_overrides = {}
i = 2
while i < len(argv):
    key = argv[i]
    if key == "--keep-normals":
        opts[key] = True
        i += 1
        continue
    if key == "--tex":
        slot, _, path = argv[i + 1].partition("=")
        tex_overrides[slot] = path
    else:
        opts[key] = argv[i + 1]
    i += 2
scale = float(opts.get("--scale", 1.0))
smooth_angle = float(opts.get("--angle", 60))
hull_max = int(opts.get("--hull-max", 48))

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.preferences.addon_enable(module="io_scene_nifly")
from io_scene_nifly.pyn.pynifly import NifFile  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nif_rigid_lib as lib  # noqa: E402

src = NifFile(src_path)
if len(src.shapes) != 1:
    raise SystemExit("expected one shape, found %d" % len(src.shapes))
sshape = src.shapes[0]
if sshape.has_skin_instance:
    raise SystemExit("skinned mesh: use Outfit Studio / PyNifly import-export instead")
V = np.array(sshape.verts, dtype=np.float64)
T = np.array(sshape.tris, dtype=np.int64)
UV = np.array(sshape.uvs, dtype=np.float64)
UV[:, 1] = np.where(UV[:, 1] < 0.0, UV[:, 1] + 1.0, UV[:, 1])
report = {"source": src_path, "scale": scale, "source_counts": {"verts": len(V), "tris": len(T)}}

pos_key = np.round(V / 1e-4).astype(np.int64)
_, pos_id = np.unique(pos_key, axis=0, return_inverse=True)
pos_id = pos_id.reshape(-1)
P = np.zeros((pos_id.max() + 1, 3))
P[pos_id] = V
corner_pos = pos_id[T]
fn = np.cross(P[corner_pos[:, 1]] - P[corner_pos[:, 0]], P[corner_pos[:, 2]] - P[corner_pos[:, 0]])
area2 = np.linalg.norm(fn, axis=1)
keep = area2 > 1e-10
T, corner_pos, fn, area2 = T[keep], corner_pos[keep], fn[keep], area2[keep]
fnu = fn / area2[:, None]
report["degenerate_removed"] = int((~keep).sum())

if "--keep-normals" in opts:
    src_normals = np.array(sshape.normals, dtype=np.float64)
    corner_normals = src_normals[T]
else:
    def corner_angles(pts):
        def ang(p, q, r):
            u = q - p
            w = r - p
            c = np.einsum("ij,ij->i", u, w) / (np.linalg.norm(u, axis=1) * np.linalg.norm(w, axis=1) + 1e-20)
            return np.arccos(np.clip(c, -1, 1))
        a, b, c = pts[:, 0], pts[:, 1], pts[:, 2]
        return np.stack([ang(a, b, c), ang(b, c, a), ang(c, a, b)], axis=1)

    angles = corner_angles(P[corner_pos])
    incident = [[] for _ in range(len(P))]
    for f in range(len(corner_pos)):
        for j in range(3):
            incident[corner_pos[f, j]].append((f, j))
    cos_thr = math.cos(math.radians(smooth_angle))
    corner_normals = np.zeros((len(corner_pos), 3, 3))
    for f in range(len(corner_pos)):
        for j in range(3):
            acc = np.zeros(3)
            for g, k in incident[corner_pos[f, j]]:
                if np.dot(fnu[f], fnu[g]) >= cos_thr:
                    acc += angles[g, k] * fnu[g]
            corner_normals[f, j] = acc / (np.linalg.norm(acc) + 1e-20)

keys = {}
out_pos, out_uv, out_nrm = [], [], []
out_tris = np.zeros_like(T)
corner_uv = UV[T]
for f in range(len(T)):
    for j in range(3):
        p = corner_pos[f, j]
        uv = corner_uv[f, j]
        nr = corner_normals[f, j]
        key = (int(p), round(uv[0], 5), round(uv[1], 5), round(nr[0], 3), round(nr[1], 3), round(nr[2], 3))
        idx = keys.get(key)
        if idx is None:
            idx = len(out_pos)
            keys[key] = idx
            out_pos.append(P[p])
            out_uv.append(uv)
            out_nrm.append(nr)
        out_tris[f, j] = idx
out_pos = np.array(out_pos) * scale
out_uv = np.array(out_uv)
out_nrm = np.array(out_nrm)
check = np.einsum("ij,ij->i", fnu, out_nrm[out_tris[:, 0]])
report["counts"] = {"verts": len(out_pos), "tris": len(out_tris)}
report["normal_vs_face_dot"] = {"min": round(float(check.min()), 3), "median": round(float(np.median(check)), 3)}


nif = NifFile()
nif.initialize("SKYRIMSE", out_path, root_type="BSFadeNode", root_name=opts.get("--root-name", src.rootName))
root = nif.root
root.flags = src.root.flags
lib.copy_root_extra_data(src.root, nif, root)
textures = {slot: lib.relative_texture(path) for slot, path in sshape.textures.items() if path}
textures.update(tex_overrides)
lib.add_shape(nif, root, opts.get("--shape-name", sshape.name), out_pos, out_tris, out_uv, out_nrm, sshape.flags,
              sshape.shader.properties, textures)
report["textures"] = textures

coll_src = src.root.collision_object
if coll_src is not None and coll_src.body is not None and coll_src.body.shape.blockname == "bhkConvexVerticesShape":
    calibration = lib.inertia_calibration(coll_src.body)
    mass = round(float(coll_src.body.properties.mass) * scale ** 3, 2)
    report["collision"] = lib.add_convex_collision(root, out_pos, coll_src, mass, calibration, hull_max)
elif coll_src is not None:
    print("CONVERT: source collision is not a single convex shape; no collision written")

nif.save()
report["bounds"] = lib.bounds(out_pos)
if "--report" in opts:
    with open(opts["--report"], "w") as fh:
        json.dump(report, fh, indent=2)
print("CONVERT:", out_path, json.dumps(report["counts"]), "obnd", report["bounds"]["obnd"])
