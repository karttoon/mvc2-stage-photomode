#!/usr/bin/env python3
"""Batch-capture MvC2 stages: center still + smooth right-to-left pan MP4 + GIF.

v3 pipeline (the one that works):
- CHAR-DRIVEN PAN: slide the (invisible) character pair across the stage and let
  the engine's own camera follow. Gameplay-smooth (no dead-zone stalls), and the
  engine clamps at each stage's designed view limit automatically -- no edge
  detection needed. DEFAULT camera limits are kept (no widening): char +/-1114
  drives the camera exactly onto the game's own +/-960 wall, the true player edge.
- OCCLUSION-PROOF capture: grab the Flycast window's OWN pixels via PrintWindow
  (PW_RENDERFULLCONTENT) straight into memory at ~35-40fps. Immune to overlapping
  windows -- the old gdigrab desktop-region capture silently grabbed whatever window
  covered the region (e.g. the editor) = the "NO MOTION" failures. PrintWindow DOES
  return live DX11 frames here (verified fresh during motion), contrary to old notes.
- POST: trim to the camera-motion span (cross-correlation), inset 1s per side
  (drops the saturated frames where the art edge peeks in), regenerate GIF.

Usage: stage_batch.py [stage_hex ...]   (default: all 17)
Env: PM_CDI (disc image), PM_OUT (output root)
"""
import os, subprocess, sys, time
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pmlib as pm
from config import MODIFIED_CDI, OUT_MODIFIED

CDI = os.environ.get("PM_CDI", MODIFIED_CDI)
OUT_ROOT = os.environ.get("PM_OUT", OUT_MODIFIED)
# Optional suffix appended to the stage tag/filenames -- used for OTHER PEOPLE's
# stages so they never collide with your own captures.
LABEL = os.environ.get("PM_LABEL", "").strip()

CHAR_SWEEP = 1114     # char slide endpoints (+/-). Coupling: render magnitude =
                      # |char| - 154, so char +/-1114 -> cam +/-960 == the game's
                      # DEFAULT clamp (the real player view edge). Symmetric around
                      # cam 0 (the round-start still). No limit widening: the sweep
                      # lands exactly on the natural wall. User-calibrated on Desert.
PAN_SPEED = 125.0     # world units/sec (user-approved pace)
SETTLE_S = 6          # camera convergence hold at the start position
INSET_S = 1.0         # cut this much off each end of the motion span

STAGES = {
    0x00: "AirShip",   0x01: "Desert",     0x02: "Factory",  0x03: "Carnival",
    0x04: "Swamp",     0x05: "BlueCave",   0x06: "Clock",    0x07: "IceRiver",
    0x08: "Abyss",     0x09: "AltAirShip", 0x0A: "AltDesert",0x0B: "Training",
    0x0C: "AltCarnival",0x0D: "PinkSwamp", 0x0E: "LavaCave", 0x0F: "WinterClock",
    0x10: "RiverRaft",
}


def record_char_pan(hwnd, seconds):
    """OCCLUSION-PROOF in-memory capture: grab the Flycast window's own pixels via
    PrintWindow (immune to overlapping windows -- the gdigrab screen-region approach
    got clobbered whenever another window covered the region = the "NO MOTION"
    failures). COMPLETION-BOUNDED: capture from pan start until the harness reports
    the camera pan finished (panDoneCount increments -- authoritative, independent of
    stage ANIMATION, which frame-delta can't distinguish from camera motion). Because
    the whole capture IS the pan, no motion-detection trim is needed. Returns
    (frames, fps, ok)."""
    flag = os.path.join(pm.PM_DIR, "panflag.txt")
    try:
        os.remove(flag)
    except OSError:
        pass
    pm.cmd(f'for _,b in pairs(SLOTS) do freeze(b+CS.pos_x,"f32",{CHAR_SWEEP}); '
           f'freeze(b+CS.pos_y,"f32",0) end', settle=SETTLE_S)
    grab = pm.Grabber(hwnd)
    frames = []
    ok = False
    try:
        # settle>0 so the harness actually consumes startCharPan before the poll
        # loop below starts writing camera-read commands (else it clobbers cmd.txt
        # and the pan never starts).
        pm.cmd(f"startCharPan({CHAR_SWEEP}, {-CHAR_SWEEP}, {seconds})", settle=0.3)
        # HEAD-SKIP: the camera sits clamped at the right wall (+960) for ~2.5s after
        # the pan starts (settling lag) before it visibly moves. Wait -- using the
        # actual CAMERA X (ground truth, immune to stage water/animation) -- until it
        # leaves the wall, THEN start grabbing, so the video moves from frame 0.
        ts = time.time()
        while time.time() - ts < seconds:
            cx = pm.cmd_result("return string.format('%.0f', PM.rdf(0x8C1F9CD8))", settle=0.15)
            try:
                if cx is not None and float(cx) < 950:   # moved off the +960 wall
                    break
            except ValueError:
                pass
        t0 = time.time()
        hard = seconds * 3 + 20
        while time.time() - t0 < hard:
            frames.append(grab.grab())
            if os.path.exists(flag):   # harness wrote it on pan completion
                ok = True
                # grab a couple trailing frames so the left wall isn't cut early
                for _ in range(4):
                    frames.append(grab.grab())
                break
        dt = time.time() - t0
    finally:
        grab.close()
    fps = len(frames) / dt if dt > 0 else 30.0
    return frames, fps, ok


# ---------------------------------------------------------------- trim + gif
def _profile(a):
    g = a.astype(np.float32).mean(axis=2)
    h = g.shape[0]
    p = g[int(h * .35) : int(h * .65)].mean(axis=0)
    return p - p.mean()


def _shift(p1, p2, maxlag=10):
    best, bs = -1e18, 0
    for lag in range(-maxlag, maxlag + 1):
        v = float((p1[max(0, lag):len(p1) + min(0, lag)] *
                   p2[max(0, -lag):len(p2) - max(0, lag)]).sum())
        if v > best:
            best, bs = v, lag
    return bs


def _trim_span(frames, fps):
    """Return (a, b) indices of the SUSTAINED leftward-motion span. Smoothed shift
    drops to ~0 at the settling head and the saturated wall tail, so those get cut."""
    n = len(frames)
    profs = [_profile(np.asarray(f, dtype=np.float32)) for f in frames]
    sh = np.array([_shift(profs[k], profs[k + 1]) for k in range(n - 1)], dtype=float)
    win = max(5, int(fps * 0.5))
    sm = np.convolve(sh, np.ones(win) / win, mode="same")
    moving = np.where(sm <= -0.3)[0]
    if len(moving) == 0:
        return None
    ins = int(fps * 0.4)
    a = max(0, int(moving[0]) + ins)
    b = min(n, int(moving[-1]) + 2 - ins)
    return (a, b)


def _encode(ff, frames, fps, out, crf, scale=None):
    """Pipe RGB frames to ffmpeg -> H.264 mp4 at the given CRF (lower = better)."""
    h, w = frames[0].shape[:2]
    vf = ["format=yuv420p"]
    if scale:
        vf.insert(0, f"scale={scale}:-2")
    args = [ff, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{w}x{h}", "-framerate", str(int(round(fps))), "-i", "-",
            "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
            "-vf", ",".join(vf), "-movflags", "+faststart", "-an", out]
    p = subprocess.Popen(args, stdin=subprocess.PIPE,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for fr in frames:
        p.stdin.write(np.ascontiguousarray(fr, dtype=np.uint8).tobytes())
    p.stdin.close()
    p.wait()
    return os.path.getsize(out)


def _motion_onset(frames, fps):
    """First frame index where the camera actually starts translating left. Uses
    HORIZONTAL cross-correlation shift (global pan), which ignores local stage
    animation -- so it finds the true pan start past the ~2.5s camera-settling head."""
    profs = [_profile(np.asarray(f, dtype=np.float32)) for f in frames]
    sh = np.array([_shift(profs[k], profs[k + 1]) for k in range(len(frames) - 1)], float)
    sm = np.convolve(sh, np.ones(5) / 5, mode="same")
    run = max(3, int(fps * 0.15))
    for i in range(len(sm) - run):
        if all(sm[i + k] <= -0.4 for k in range(run)):
            return i
    return 0


def finalize(frames, fps, mp4_hq, mp4_small, gif=None):
    """Trim the camera-settling HEAD (so the pan is moving from frame 0) + a tiny
    tail, then encode: HQ mp4 + small (~4MB) shareable mp4 + optional slim gif.
    Returns (summary, first_frame, last_frame) for the 3-pic panel."""
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    if len(frames) < fps * 3:
        return (f"TOO SHORT ({len(frames)/fps:.1f}s)", None, None)
    # head already skipped at capture (camera-truth); just shave settling edges
    a = int(fps * 0.1)
    b = max(a + 1, len(frames) - int(fps * 0.2))
    sub = frames[a:b]
    hq = _encode(ff, sub, fps, mp4_hq, crf=17)             # near-lossless, full res
    sm = _encode(ff, sub, fps, mp4_small, crf=25)          # Discord-friendly
    if gif:
        gstep = max(1, round(fps / 12))
        g = [Image.fromarray(sub[i]).resize((480, 360), Image.LANCZOS)
                 .quantize(colors=96, method=Image.FASTOCTREE)
             for i in range(0, len(sub), gstep)]
        g[0].save(gif, save_all=True, append_images=g[1:], loop=0,
                  duration=int(1000 / 12), disposal=2, optimize=True)
    res = (f"{len(sub)}f {len(sub)/fps:.1f}s  hq={hq/1e6:.1f}MB "
           f"small={sm/1e6:.1f}MB")
    return (res, sub[0], sub[-1])


def make_panel(out, left, center, right, gap=10, bg=(15, 15, 15)):
    """Horizontal 3-up: far-left | center | far-right (for website use)."""
    from PIL import Image as I
    ims = [I.fromarray(np.asarray(x)).convert("RGB") for x in (left, center, right)]
    h = min(im.height for im in ims)
    ims = [im.resize((int(im.width * h / im.height), h)) for im in ims]
    W = sum(im.width for im in ims) + gap * (len(ims) + 1)
    canvas = I.new("RGB", (W, h + gap * 2), bg)
    x = gap
    for im in ims:
        canvas.paste(im, (x, gap))
        x += im.width + gap
    canvas.save(out)


def do_stage(sid):
    name = STAGES[sid]
    tag = f"stg{sid:02X}_{name}" + (f"__{LABEL}" if LABEL else "")
    outdir = os.path.join(OUT_ROOT, tag)
    os.makedirs(outdir, exist_ok=True)
    log = lambda m: print(f"[{tag}] {m}", flush=True)

    pm.kill_flycast()
    pm.launch(CDI)
    hwnd = pm.ensure_window()
    time.sleep(4)
    st = pm.goto_match(sid)
    log(f"in match, stage={st}")
    pm.strip_stage()
    # DEFAULT camera limits (no widen). char +/-1114 lands the camera exactly on
    # the game's own +/-960 wall == the player view edge.
    time.sleep(1)

    # center still: stripStage pins chars neutral -> engine camera rests at
    # the true round-start framing. Nothing else to do.
    time.sleep(1.5)
    still_path = os.path.join(outdir, f"{tag}_still.png")
    still = pm.capture(still_path, hwnd)

    seconds = round(2 * CHAR_SWEEP / PAN_SPEED)
    # Retry the record+finalize a couple times as a belt-and-suspenders guard (the
    # PrintWindow capture is occlusion-proof so this rarely triggers now).
    res, first, last = "NO MOTION", None, None
    for attempt in range(1, 3):
        log(f"recording char-driven pan ({seconds}s slide) attempt {attempt}")
        frames, fps, ok = record_char_pan(hwnd, seconds)
        log(f"captured {len(frames)} frames @ {fps:.0f}fps pan_done={ok}; finalizing")
        res, first, last = finalize(
            frames, fps,
            os.path.join(outdir, f"{tag}_pan.mp4"),        # HQ
            os.path.join(outdir, f"{tag}_pan_small.mp4"),  # shareable
            gif=None)                                       # GIFs dropped (mp4 suffices)
        frames = None   # release ~2GB before the next attempt/stage
        if first is not None and ok:
            break
        log(f"  -> {res}; retrying")
        time.sleep(2)
    # 3-pic panel: pan sweeps right->left, so first frame = RIGHT edge (+960),
    # last frame = LEFT edge (-960); center = the round-start still. Also save the
    # three edges as SEPARATE stills (for the website's per-image popup).
    if first is not None:
        make_panel(os.path.join(outdir, f"{tag}_panel.png"),
                   last, np.asarray(still), first)
        Image.fromarray(np.asarray(last)).save(os.path.join(outdir, f"{tag}_left.png"))
        Image.fromarray(np.asarray(first)).save(os.path.join(outdir, f"{tag}_right.png"))
    else:
        log("!! FAILED after retries")
    log(f"DONE ({res})")
    with open(os.path.join(outdir, "meta.txt"), "w") as f:
        f.write(f"stage={sid:#04x} {name}\nchar_sweep=+/-{CHAR_SWEEP} "
                f"speed={PAN_SPEED}u/s\nfinal={res}\n")


def main():
    ids = [int(a, 16) for a in sys.argv[1:]] or sorted(STAGES)
    failures = []
    for sid in ids:
        try:
            do_stage(sid)
        except Exception as e:
            print(f"[stg{sid:02X}] FAILED: {e}", flush=True)
            failures.append((sid, str(e)))
    pm.kill_flycast()
    print("\n=== SUMMARY ===")
    print(f"ok: {len(ids) - len(failures)}/{len(ids)}")
    for sid, e in failures:
        print(f"  FAILED stg{sid:02X} {STAGES[sid]}: {e}")


if __name__ == "__main__":
    main()
