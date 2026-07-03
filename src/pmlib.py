#!/usr/bin/env python3
"""Photo-mode driver library: flycast process control, harness commands,
window capture (PrintWindow via ctypes), and match navigation."""
import ctypes, ctypes.wintypes as wt
import os, sys, subprocess, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import PM_DIR, FLYCAST_EXE as FLYCAST, FLYCAST_DIR as FLY_DIR
CMD_FILE = os.path.join(PM_DIR, "cmd.txt")
OUT_LOG  = os.path.join(PM_DIR, "out.log")

user32 = ctypes.windll.user32
gdi32  = ctypes.windll.gdi32

# ---------------------------------------------------------------- process
def kill_flycast():
    subprocess.run(["taskkill", "/IM", "flycast.exe", "/F"],
                   capture_output=True)
    time.sleep(2)

def launch(cdi):
    open(CMD_FILE, "w").write("0\n-- noop\n")
    open(OUT_LOG, "w").close()
    subprocess.Popen([FLYCAST, cdi], cwd=FLY_DIR)
    time.sleep(10)

# ---------------------------------------------------------------- window
def find_hwnd():
    hwnds = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, l):
        if user32.IsWindowVisible(h):
            n = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(h, n, 256)
            if n.value.startswith("Flycast"):
                hwnds.append(h)
        return True
    user32.EnumWindows(cb, 0)
    return hwnds[0] if hwnds else None

def ensure_window(w=1280, h=960, x=20, y=20):
    hwnd = find_hwnd()
    if not hwnd:
        raise RuntimeError("flycast window not found")
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    time.sleep(0.3)
    user32.MoveWindow(hwnd, x, y, w, h, True)
    time.sleep(0.2)
    cr = wt.RECT(); user32.GetClientRect(hwnd, ctypes.byref(cr))
    wr = wt.RECT(); user32.GetWindowRect(hwnd, ctypes.byref(wr))
    fw = (wr.right - wr.left) - cr.right
    fh = (wr.bottom - wr.top) - cr.bottom
    user32.MoveWindow(hwnd, x, y, w + fw, h + fh, True)
    time.sleep(0.2)
    return hwnd

def client_screen_rect(hwnd):
    cr = wt.RECT(); user32.GetClientRect(hwnd, ctypes.byref(cr))
    pt = wt.POINT(0, 0); user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x, pt.y, cr.right, cr.bottom  # x, y, w, h

def foreground(hwnd):
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.4)

# SetWindowPos flags
_HWND_TOPMOST, _HWND_NOTOPMOST = -1, -2
_SWP_NOMOVE, _SWP_NOSIZE, _SWP_NOACTIVATE = 0x0002, 0x0001, 0x0010

def set_topmost(hwnd, on=True):
    """Pin the window above all others (so screen-region capture can't be
    occluded) WITHOUT stealing keyboard focus (NOACTIVATE)."""
    user32.ShowWindow(hwnd, 9)
    user32.SetWindowPos(hwnd, _HWND_TOPMOST if on else _HWND_NOTOPMOST,
                        0, 0, 0, 0,
                        _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE)
    time.sleep(0.3)

def capture(path, hwnd=None):
    """PrintWindow(flag 2) the flycast window, crop to client area, save PNG."""
    from PIL import Image
    hwnd = hwnd or find_hwnd()
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 4); time.sleep(0.4)
    wr = wt.RECT(); user32.GetWindowRect(hwnd, ctypes.byref(wr))
    ww, wh = wr.right - wr.left, wr.bottom - wr.top
    cr = wt.RECT(); user32.GetClientRect(hwnd, ctypes.byref(cr))
    cw, ch = cr.right, cr.bottom
    pt = wt.POINT(0, 0); user32.ClientToScreen(hwnd, ctypes.byref(pt))
    offx, offy = pt.x - wr.left, pt.y - wr.top

    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, ww, wh)
    gdi32.SelectObject(mem, bmp)
    user32.PrintWindow(hwnd, mem, 2)  # PW_RENDERFULLCONTENT

    class BMIH(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                    ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                    ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                    ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]
    bih = BMIH(ctypes.sizeof(BMIH), ww, -wh, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(ww * wh * 4)
    gdi32.GetDIBits(mem, bmp, 0, wh, buf, ctypes.byref(bih), 0)
    gdi32.DeleteObject(bmp); gdi32.DeleteDC(mem); user32.ReleaseDC(hwnd, hdc)

    im = Image.frombuffer("RGB", (ww, wh), buf, "raw", "BGRX", 0, 1)
    im = im.crop((offx, offy, offx + cw, offy + ch))
    im.save(path)
    return im

class Grabber:
    """Fast, OCCLUSION-PROOF window capture via PrintWindow(PW_RENDERFULLCONTENT).
    Reuses DC/bitmap/buffer across grabs -> ~40fps for a 1280x960 client. Captures
    the window's OWN pixels regardless of z-order, so nothing overlapping the screen
    region can corrupt the frame (unlike gdigrab desktop capture)."""

    class _BMIH(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                    ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                    ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                    ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]

    def __init__(self, hwnd):
        import numpy as np
        self.np = np
        self.hwnd = hwnd
        wr = wt.RECT(); user32.GetWindowRect(hwnd, ctypes.byref(wr))
        self.ww, self.wh = wr.right - wr.left, wr.bottom - wr.top
        cr = wt.RECT(); user32.GetClientRect(hwnd, ctypes.byref(cr))
        self.cw, self.ch = cr.right, cr.bottom
        pt = wt.POINT(0, 0); user32.ClientToScreen(hwnd, ctypes.byref(pt))
        self.offx, self.offy = pt.x - wr.left, pt.y - wr.top
        self.bih = Grabber._BMIH(ctypes.sizeof(Grabber._BMIH), self.ww, -self.wh,
                                 1, 32, 0, 0, 0, 0, 0, 0)
        self.buf = ctypes.create_string_buffer(self.ww * self.wh * 4)
        self.hdc = user32.GetWindowDC(hwnd)
        self.mem = gdi32.CreateCompatibleDC(self.hdc)
        self.bmp = gdi32.CreateCompatibleBitmap(self.hdc, self.ww, self.wh)
        gdi32.SelectObject(self.mem, self.bmp)

    def grab(self):
        """Return an RGB uint8 HxWx3 array cropped to the client area."""
        np = self.np
        user32.PrintWindow(self.hwnd, self.mem, 2)
        gdi32.GetDIBits(self.mem, self.bmp, 0, self.wh, self.buf, ctypes.byref(self.bih), 0)
        a = np.frombuffer(self.buf.raw, dtype=np.uint8).reshape(self.wh, self.ww, 4)
        a = a[self.offy:self.offy + self.ch, self.offx:self.offx + self.cw, :3]  # BGR
        return a[:, :, ::-1].copy()  # -> RGB

    def close(self):
        gdi32.DeleteObject(self.bmp); gdi32.DeleteDC(self.mem)
        user32.ReleaseDC(self.hwnd, self.hdc)


# ---------------------------------------------------------------- harness cmd
_seq = [None]
def _next_seq():
    if _seq[0] is None:
        try:
            _seq[0] = int(open(CMD_FILE).readline().strip())
        except Exception:
            _seq[0] = 0
    _seq[0] += 1
    return _seq[0]

def cmd(lua, settle=1.5):
    s = _next_seq()
    with open(CMD_FILE, "w") as f:
        f.write(f"{s}\n{lua}\n")
    time.sleep(settle)
    return s

def cmd_result(lua, settle=1.5):
    s = cmd(lua, settle)
    # find "== cmd <s> ==" ... "=> result"
    txt = open(OUT_LOG, encoding="utf-8", errors="replace").read()
    key = f"== cmd {s} @"
    i = txt.rfind(key)
    if i < 0:
        return None
    j = txt.find("=> ", i)
    k = txt.find(f"== cmd {s} done ==", i)
    if j < 0 or (0 <= k < j):
        return None
    return txt[j + 3 : txt.find("\n== cmd", j)].strip()

# ---------------------------------------------------------------- navigation
def read_state():
    """(match_tracker, in_match, stage_id, p1c1_is_cpu) or None."""
    r = cmd_result(
        'return string.format("%d,%d,%d,%d", PM.rd8(G.match_tracker), '
        'PM.rd8(G.in_match), PM.rd8(G.stg_id2), PM.rd8(SLOTS.P1C1+0x525))',
        settle=1.0)
    if not r:
        return None
    try:
        return tuple(int(v) for v in r.split(","))
    except ValueError:
        return None


def goto_match(stage_id, timeout=150):
    """STATE-DRIVEN navigation: force the stage, then keep cycling
    START/join/confirm inputs and re-checking memory until we are in a REAL
    human match (is_cpu==0 -- an attract demo can never satisfy this).
    Robust to boot-timing drift, attract loops, and menu variations."""
    cmd(f'freeze(G.stg_id2, "u8", {stage_id})\n'
        'pcall(function() flycast.config.maple.setDeviceType(2, 0) end)', settle=1.5)
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = read_state()
        if s:
            tr, im, st, cpu = s
            if im == 1 and tr == 4 and cpu == 0:
                # unpause safeguard: a stray START right at match start pauses
                f1 = cmd_result("return PM.rd32(G.frame_counter)", settle=0.8)
                f2 = cmd_result("return PM.rd32(G.frame_counter)", settle=0.8)
                if f1 is not None and f1 == f2:
                    cmd('tap("START", 6)', settle=1.5)
                return st
        # advance whatever screen we're on: title/attract -> START;
        # char select -> P2 join (START) + both players confirm (A)
        cmd('tap("START", 8); tap(0, 45); tap2("START", 8); tap(0, 45); '
            'tap("A", 8); tap(0, 30); tap2("A", 8); tap(0, 30); '
            'tap("A", 8); tap(0, 30); tap2("A", 8)', settle=6)
    raise RuntimeError("match did not start (state-driven nav timeout)")

def mute():
    # silence the emulator (background capture runs headless-quiet)
    cmd('pcall(function() flycast.config.audio.AudioVolume = 0 end)\n'
        'pcall(function() flycast.config.audio.DSPEnabled = false end)', settle=0.8)

def strip_stage():
    cmd("stripStage()\nflycast.config.video.VSync = true", settle=2.5)
    mute()

def cam(x, fov=43, y=95, z=812, look_y=95):
    cmd(f"cam({x},{y},{z},{x},{look_y},0,{fov})", settle=1.2)

# (removed widen_limits: the game's own per-stage camera clamp is the player edge)
