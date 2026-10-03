"""Build the texture sets of the Mannoroth Shield from the original 512x512 diffuse, one per package.

python make_textures.py <original diffuse.dds> <out_dir> <cache_dir> [--sets 2K=4096,4K=8192] [--upscaler <exe>]

--sets maps each package label to the texture size in pixels; each set goes to
<out_dir>\\<label>\\textures\\weapons\\mannoroth. The labels describe the detail the player sees: the source is a 512 px
painting, so the upscaled 4096 px set reads as 2K and the 8192 px set as 4K (2048 px is also supported).
Diffuse: Real-ESRGAN x4plus, 512 -> 2048 -> 8192. 4096 px blends both passes equally (the first resampled up keeps the
painted grain, the second resampled down the sharp edges); 8192 px keeps 70% of the second pass and 30% of the first
resampled up; 2048 px is the 4096 px set resampled down.
Normal map: height from the cavity map in the original alpha (upscaled the same way) plus fine grain from the brightness,
specular mask on metal in its alpha. 4096 and 8192 px are built at their size (strength, blur and grain radius scale
with it); 2048 px is the 4096 px map's second mip level.
Environment mask at half the diffuse size: metal parts reflect, bone, leather and cloth barely do.
Glow map (half the diffuse size, at most 2048): fel fire in the skull's eye socket (eye_socket.json), which both eyes of
the model share. All BC7 with full mip chains. Working files go to <cache_dir>\\<size in pixels>.
--upscaler is the realesrgan-ncnn-vulkan executable (default: found on PATH); it only runs when <cache_dir> lacks an
upscaled image.
"""
import json
import os
import struct
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
TEXCONV = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\texconv.exe")
TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
NAME = "Mannoroth Shield"
NORMAL_4K = {"strength": 28, "blur": 3, "detail": 0.12, "detail_radius": 6}
GLOW_MAX = 2048
GLOW_RAMP = [(0.0, (0, 0, 0)), (0.2, (0.0, 0.07, 0.0)), (0.45, (0.03, 0.3, 0.01)), (0.7, (0.13, 0.68, 0.04)),
             (0.9, (0.33, 0.94, 0.1)), (1.0, (0.58, 1.0, 0.28))]

args = sys.argv[1:]
src_dds, out_dir, cache = args[:3]
opts = dict(zip(args[3::2], args[4::2]))
sets = [(label, int(size)) for label, size in
        (item.split("=") for item in opts.get("--sets", "2K=4096,4K=8192").split(","))]
ESRGAN = opts.get("--upscaler", "realesrgan-ncnn-vulkan.exe")
eye = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "eye_socket.json")))
os.makedirs(cache, exist_ok=True)


def read_bgra_dds(path):
    d = open(path, "rb").read()
    h, w = struct.unpack_from("<II", d, 12)
    px = np.frombuffer(d, dtype=np.uint8, count=w * h * 4, offset=128).reshape(h, w, 4)
    return px[..., [2, 1, 0, 3]]


def esrgan(src, dst):
    if not os.path.exists(dst):
        subprocess.run([ESRGAN, "-i", src, "-o", dst, "-n", "realesrgan-x4plus", "-s", "4", "-t", "128", "-f", "png"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return dst


def texconv(src, target):
    subprocess.run([TEXCONV, "-nologo", "-y", "-f", "BC7_UNORM", "-m", "0", "-o", target, src], check=True,
                   stdout=subprocess.DEVNULL)


def resized(img, size):
    return np.asarray(Image.fromarray(img).resize((size, size), Image.LANCZOS))


def normal_map(height_png, raw_dds, scale):
    p = NORMAL_4K
    subprocess.run([sys.executable, os.path.join(TOOLS, "normal_from_height.py"), height_png, raw_dds,
                    "--height", "alpha", "--strength", str(p["strength"] * scale), "--blur", str(p["blur"] * scale),
                    "--detail", str(p["detail"]), "--detail-radius", str(p["detail_radius"] * scale), "--spec", "metal"],
                   check=True)


def half_normal(raw_dds, dst):
    """Write the raw DDS's mip chain from level 1 on as a DDS of its own (a renormalised half-size normal map)."""
    d = open(raw_dds, "rb").read()
    h, w = struct.unpack_from("<II", d, 12)
    mips = struct.unpack_from("<I", d, 28)[0]
    header = bytearray(d[:128])
    struct.pack_into("<II", header, 12, h // 2, w // 2)
    struct.pack_into("<I", header, 20, (w // 2) * 4)
    struct.pack_into("<I", header, 28, mips - 1)
    with open(dst, "wb") as fh:
        fh.write(header)
        fh.write(d[128 + w * h * 4:])


def env_mask(diffuse, cav, size):
    small = resized(diffuse, size).astype(np.float64) / 255
    cav_small = resized(cav, size).astype(np.float64) / 255
    mx, mn = small.max(axis=2), small.min(axis=2)
    saturation = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0)
    metal = np.clip((0.35 - saturation) / 0.2, 0, 1) * np.clip((mx - 0.18) / 0.25, 0, 1)
    env = (0.05 + 0.45 * metal) * np.clip((cav_small - 0.35) / 0.4, 0.3, 1)
    return np.clip(np.round(env * 255), 0, 255).astype(np.uint8)


def fbm(h, w, seed, octaves, base):
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        n = base * 2 ** o
        out += amp * cv2.resize(rng.random((n + 1, n + 1)).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
        total += amp
        amp *= 0.55
    out /= total
    return (out - out.min()) / (out.max() - out.min())


def glow_map(diffuse):
    """Fel fire in the eye socket: an ember deep in the dark of the socket, mottled like flame, dark near the bone rim."""
    h, w = diffuse.shape[:2]
    luma = (diffuse.astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)) / 255
    cx, cy = eye["uv_center"][0] * w, eye["uv_center"][1] * h
    rx, ry = eye["uv_radius"][0] * w, eye["uv_radius"][1] * h
    x0, x1, y0, y1 = int(cx - 1.4 * rx), int(cx + 1.4 * rx), int(cy - 1.4 * ry), int(cy + 1.4 * ry)
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    r = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
    dark = np.clip((0.48 - luma[y0:y1, x0:x1]) / 0.2, 0, 1) * np.clip((1.0 - r) / 0.2, 0, 1)
    s = rx / 40
    mask = cv2.GaussianBlur(dark, (0, 0), s * 1.5)
    depth = cv2.GaussianBlur(cv2.distanceTransform((dark > 0.5).astype(np.uint8), cv2.DIST_L2, 5), (0, 0), s * 3)
    core = depth / depth.max()
    flame = fbm(y1 - y0, x1 - x0, 3, 6, 5)
    grain = fbm(y1 - y0, x1 - x0, 9, 4, 24)
    heat = np.clip(core ** 1.4 * (0.4 + 0.6 * flame) * (0.85 + 0.3 * grain) + 0.12 * mask * flame, 0, 1)
    ts = np.array([t for t, _ in GLOW_RAMP])
    cols = np.array([c for _, c in GLOW_RAMP])
    out = np.zeros((h, w, 3), np.uint8)
    out[y0:y1, x0:x1] = np.clip(np.round(np.stack([np.interp(heat, ts, cols[:, k]) for k in range(3)], -1) * 255), 0, 255)
    return out


def save(img, folder, name):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name + ".png")
    Image.fromarray(img).save(path, compress_level=1)
    return path


original = read_bgra_dds(src_dds)
Image.fromarray(original[..., :3]).save(os.path.join(cache, "diffuse_512.png"))
Image.fromarray(np.repeat(original[..., 3:4], 3, axis=2)).save(os.path.join(cache, "cavity_512.png"))
pass1 = esrgan(os.path.join(cache, "diffuse_512.png"), os.path.join(cache, "diffuse_2048.png"))
pass2 = esrgan(pass1, os.path.join(cache, "diffuse_8192.png"))
cavity = esrgan(os.path.join(cache, "cavity_512.png"), os.path.join(cache, "cavity_2048.png"))

up = np.asarray(Image.open(pass1).convert("RGB").resize((4096, 4096), Image.LANCZOS), dtype=np.float32)
down = np.asarray(Image.open(pass2).convert("RGB").resize((4096, 4096), Image.LANCZOS), dtype=np.float32)
diffuse4 = np.clip(np.round(0.5 * up + 0.5 * down), 0, 255).astype(np.uint8)
del up, down
cav4 = np.asarray(Image.open(cavity).convert("L").resize((4096, 4096), Image.LANCZOS), dtype=np.uint8)
glow4 = glow_map(diffuse4)

work4 = os.path.join(cache, "4096")
raw4 = os.path.join(work4, NAME + "_n.dds")
os.makedirs(work4, exist_ok=True)
normal_map(save(np.dstack([diffuse4, cav4]), work4, "height_source"), raw4, 1)

for label, size in sets:
    work = os.path.join(cache, str(size))
    target = os.path.join(out_dir, label, "textures", "weapons", "mannoroth")
    os.makedirs(target, exist_ok=True)
    if size == 4096:
        diffuse, cav = diffuse4, cav4
        texconv(raw4, target)
    elif size == 2048:
        diffuse, cav = resized(diffuse4, 2048), cav4
        raw = os.path.join(work, NAME + "_n.dds")
        os.makedirs(work, exist_ok=True)
        half_normal(raw4, raw)
        texconv(raw, target)
    else:
        sharp = np.asarray(Image.open(pass2).convert("RGB"))
        soft = np.asarray(Image.open(pass1).convert("RGB").resize((size, size), Image.LANCZOS))
        diffuse = np.empty_like(sharp)
        for row in range(0, size, 1024):
            a = sharp[row:row + 1024].astype(np.uint16)
            b = soft[row:row + 1024].astype(np.uint16)
            diffuse[row:row + 1024] = (7 * a + 3 * b + 5) // 10
        del sharp, soft
        cav = np.asarray(Image.open(esrgan(cavity, os.path.join(cache, "cavity_8192.png"))).convert("L"))
        raw = os.path.join(work, NAME + "_n.dds")
        normal_map(save(np.dstack([diffuse, cav]), work, "height_source"), raw, size // 4096)
        texconv(raw, target)
    texconv(save(diffuse, work, NAME), target)
    texconv(save(np.repeat(env_mask(diffuse, cav, size // 2)[..., None], 3, axis=2), work, NAME + "_m"), target)
    texconv(save(resized(glow4, min(size // 2, GLOW_MAX)), work, NAME + "_g"), target)
    for suffix in ("", "_n", "_m", "_g"):
        path = os.path.join(target, NAME + suffix + ".dds")
        d = open(path, "rb").read(148)
        h, w = struct.unpack_from("<II", d, 12)
        mips = struct.unpack_from("<I", d, 28)[0]
        print("TEXTURE: %s package, %s %dx%d mips=%d %.1f MB" % (label, NAME + suffix + ".dds", w, h, mips,
                                                                os.path.getsize(path) / 2 ** 20))
