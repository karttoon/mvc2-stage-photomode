#!/usr/bin/env python3
"""Emit a community-submission bundle from a capture, ready for the website.

Produces 6 files (7 for geometry-replacing mods) + meta.json, flat in one folder, named c_{stageId}_{sub}_{suffix}:

  c_{id}_{sub}_thumb.jpg   420x315 JPEG   <- *_still.png
  c_{id}_{sub}_c.jpg       760x570 JPEG   <- *_still.png   (center)
  c_{id}_{sub}_l.jpg       760x570 JPEG   <- *_left.png
  c_{id}_{sub}_r.jpg       760x570 JPEG   <- *_right.png
  c_{id}_{sub}_pan.mp4     byte copy      <- *_pan_small.mp4
  c_{id}_{sub}_tex.BIN     byte copy      <- the submitted texture
  c_{id}_{sub}_pol.BIN     byte copy      <- ONLY if the mod replaces geometry
  meta.json   {"stageId","sub","author","title"}

`sub` = first 8 lowercase hex chars of the MD5 of the RAW texture .BIN bytes. Hashing
the texture (not the images) makes the id stable across recaptures and gives instant
duplicate detection. Fallback when no .BIN is supplied: MD5 of the center still PNG.

  export_submission.py <capture_dir> --stage 04 --author name
                       [--tex texture.BIN] [--pol geometry.BIN] [--title "Moonlight"]
                       [--out <dir>]

The HQ *_pan.mp4 and *_panel.png are intentionally NOT exported -- they stay local
as masters; the site doesn't use them.
"""
import os, sys, glob, json, shutil, hashlib
from PIL import Image

THUMB = (420, 315)
LARGE = (760, 570)
JPEG_Q = 85


def sub_hash(tex_path=None, still_path=None):
    """First 8 lowercase hex of MD5 -- of the texture .BIN if given, else the still."""
    src = tex_path if (tex_path and os.path.exists(tex_path)) else still_path
    if not src or not os.path.exists(src):
        raise SystemExit("need a texture .BIN or a center still to hash")
    return hashlib.md5(open(src, "rb").read()).hexdigest()[:8].lower()


def _find(capture_dir, suffix):
    hits = glob.glob(os.path.join(capture_dir, f"*{suffix}"))
    if not hits:
        raise SystemExit(f"missing *{suffix} in {capture_dir}")
    return hits[0]


def _jpg(src, dst, size):
    Image.open(src).convert("RGB").resize(size, Image.LANCZOS).save(dst, quality=JPEG_Q)


def export(capture_dir, stage_id, author, tex=None, title=None, out_root=None, pol=None):
    stage_id = stage_id.upper().zfill(2)   # "4"->"04", "CV"/"XX" pass through
    still = _find(capture_dir, "_still.png")
    left = _find(capture_dir, "_left.png")
    right = _find(capture_dir, "_right.png")
    pan = _find(capture_dir, "_pan_small.mp4")

    sub = sub_hash(tex, still)
    out_root = out_root or os.path.join(os.path.dirname(capture_dir.rstrip("\\/")), "..", "submissions")
    dest = os.path.normpath(os.path.join(out_root, f"c_{stage_id}_{sub}"))
    os.makedirs(dest, exist_ok=True)
    p = lambda suf: os.path.join(dest, f"c_{stage_id}_{sub}_{suf}")

    _jpg(still, p("thumb.jpg"), THUMB)
    _jpg(still, p("c.jpg"), LARGE)
    _jpg(left,  p("l.jpg"), LARGE)
    _jpg(right, p("r.jpg"), LARGE)
    shutil.copyfile(pan, p("pan.mp4"))
    if tex and os.path.exists(tex):
        shutil.copyfile(tex, p("tex.BIN"))
    # Optional 7th file: only when the submission REPLACES GEOMETRY (ports /
    # originals). Pure retextures ship no POL and omit this. The site auto-detects
    # its presence -> adds a second download; no meta.json change needed.
    if pol and os.path.exists(pol):
        shutil.copyfile(pol, p("pol.BIN"))

    meta = {"stageId": stage_id, "sub": sub, "author": author}
    if title:
        meta["title"] = title
    with open(os.path.join(dest, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"submission -> {dest}")
    for fn in sorted(os.listdir(dest)):
        print(f"  {fn}  ({os.path.getsize(os.path.join(dest, fn))} bytes)")
    return dest, sub


def main():
    a = sys.argv[1:]
    opts = {}
    for flag in ("--stage", "--author", "--tex", "--title", "--out", "--pol"):
        if flag in a:
            i = a.index(flag)
            opts[flag.lstrip("-")] = a[i + 1]
            a = a[:i] + a[i + 2:]
    if len(a) != 1 or "stage" not in opts or "author" not in opts:
        raise SystemExit(__doc__)
    export(a[0], opts["stage"], opts["author"], opts.get("tex"),
           opts.get("title"), opts.get("out"), opts.get("pol"))


if __name__ == "__main__":
    main()
