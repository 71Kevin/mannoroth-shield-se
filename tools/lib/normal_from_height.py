"""Build a Skyrim tangent-space normal map (DirectX convention: green points down the texture) from a height source.

python normal_from_height.py <input> <out_n.dds> [--height alpha|luma] [--strength 3.5] [--blur 0.8]
                             [--detail 0] [--detail-radius 6] [--spec none|metal] [--preview out.png]

<input> is a PNG/TGA or an uncompressed 32-bit DDS (convert BCn files first: texconv -ft png).
--height alpha  uses the input's alpha channel (painted height/cavity maps often live there); luma uses brightness.
--detail W      adds W times the high-pass of the brightness (radius --detail-radius pixels) to the height, for fine
                surface grain on top of the height source.
--spec metal    writes a specular mask to the alpha channel: grey, desaturated areas get up to 0.36, the rest stays
                low and crevices get none. Default none (alpha 0 = no specular).
The output is uncompressed B8G8R8A8 with a full, renormalised mip chain. Works in float32 and, when OpenCV is
installed, blurs with it (same wrap-around Gaussian as the NumPy path), so 8192 px inputs fit in a few GB of memory.
"""
import struct
import sys

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

args = sys.argv[1:]
src, dst = args[0], args[1]
opts = dict(zip(args[2::2], args[3::2]))
strength = float(opts.get("--strength", 3.5))
blur_sigma = float(opts.get("--blur", 0.8))
height_mode = opts.get("--height", "alpha")
spec_mode = opts.get("--spec", "none")
F = np.float32


def read_rgba(path):
    if path.lower().endswith(".dds"):
        d = open(path, "rb").read()
        h, w = struct.unpack_from("<II", d, 12)
        pf_flags, fourcc, bits = struct.unpack_from("<I4sI", d, 80)
        masks = struct.unpack_from("<IIII", d, 92)
        if fourcc != b"\0\0\0\0" or bits != 32 or masks != (0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000):
            raise SystemExit("only uncompressed 32-bit BGRA DDS is read directly; run: texconv -ft png " + path)
        px = np.frombuffer(d, dtype=np.uint8, count=w * h * 4, offset=128).reshape(h, w, 4)
        return px[..., [2, 1, 0, 3]]
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    return np.asarray(Image.open(path).convert("RGBA"))


def blur(img, sigma):
    if sigma <= 0:
        return img
    radius = max(1, int(3 * sigma))
    x = np.arange(-radius, radius + 1)
    k = np.exp(-x ** 2 / (2 * sigma ** 2))
    k = (k / k.sum()).astype(F)
    if cv2 is not None:
        padded = np.pad(img, radius, mode="wrap")
        return cv2.sepFilter2D(padded, cv2.CV_32F, k, k, borderType=cv2.BORDER_CONSTANT)[radius:-radius, radius:-radius]
    out = img
    for axis in (0, 1):
        out = sum(np.roll(out, s, axis=axis) * wgt for s, wgt in zip(x, k))
    return out.astype(F)


def write_bgra_dds(path, levels):
    h, w = levels[0].shape[:2]
    header = bytearray(128)
    struct.pack_into("<4sIIIIIII", header, 0, b"DDS ", 124, 0x2100F, h, w, w * 4, 0, len(levels))
    struct.pack_into("<IIIIIIII", header, 76, 32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    struct.pack_into("<I", header, 108, 0x401008)
    with open(path, "wb") as fh:
        fh.write(header)
        for lvl in levels:
            fh.write(np.ascontiguousarray(lvl[..., [2, 1, 0, 3]]).tobytes())


rgba = read_rgba(src)
luma = rgba[..., 0] * F(0.299 / 255) + rgba[..., 1] * F(0.587 / 255) + rgba[..., 2] * F(0.114 / 255)
source = rgba[..., 3] * F(1 / 255) if height_mode == "alpha" else luma
height = blur(source, blur_sigma)
detail = float(opts.get("--detail", 0))
if detail:
    radius = float(opts.get("--detail-radius", 6))
    height += F(detail) * (luma - blur(luma, radius))
nx = (np.roll(height, 1, axis=1) - np.roll(height, -1, axis=1)) * F(strength / 2)
ny = (np.roll(height, 1, axis=0) - np.roll(height, -1, axis=0)) * F(strength / 2)
del height
inv = 1 / np.sqrt(nx * nx + ny * ny + 1)
n = np.empty(nx.shape + (3,), dtype=F)
n[..., 0] = nx * inv
n[..., 1] = ny * inv
n[..., 2] = inv
del nx, ny, inv

if spec_mode == "metal":
    mx = rgba[..., :3].max(axis=2) * F(1 / 255)
    mn = rgba[..., :3].min(axis=2) * F(1 / 255)
    saturation = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, F(1e-6)), F(0))
    metal = np.clip((F(0.35) - saturation) / F(0.2), 0, 1) * np.clip((mx - F(0.18)) / F(0.25), 0, 1)
    del mn, saturation
    spec = blur((F(0.06) + F(0.30) * metal) * np.clip((source - F(0.45)) / F(0.4), 0, 1), 0.6)
    del mx, metal
else:
    spec = np.zeros(n.shape[:2], dtype=F)
del rgba, luma, source


def to_level(nrm, sp):
    out = np.empty(nrm.shape[:2] + (4,), dtype=np.uint8)
    out[..., :3] = np.clip(np.round((nrm * 0.5 + 0.5) * 255), 0, 255)
    out[..., 3] = np.clip(np.round(sp * 255), 0, 255)
    return out


levels = [to_level(n, spec)]
spec_mean = float(spec.mean())
cur_n, cur_s = n, spec
while cur_n.shape[0] > 1 and cur_n.shape[1] > 1:
    hh, ww = cur_n.shape[0] // 2, cur_n.shape[1] // 2
    cur_n = cur_n[:hh * 2, :ww * 2].reshape(hh, 2, ww, 2, 3).mean(axis=(1, 3))
    cur_n /= np.linalg.norm(cur_n, axis=2, keepdims=True)
    cur_s = cur_s[:hh * 2, :ww * 2].reshape(hh, 2, ww, 2).mean(axis=(1, 3))
    levels.append(to_level(cur_n, cur_s))
del n, spec
write_bgra_dds(dst, levels)
print("normal map %s: %dx%d, %d mips, spec mean %.3f" % (dst, levels[0].shape[1], levels[0].shape[0], len(levels), spec_mean))
if "--preview" in opts:
    from PIL import Image
    Image.fromarray(levels[0][..., :3]).save(opts["--preview"])
