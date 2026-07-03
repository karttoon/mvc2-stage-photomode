#!/usr/bin/env python3
"""Regenerate showcase media for one or more MvC2 stages after you tweak a texture.

Loop: edit STGxxTEX.BIN (or POL) in MvC2_Lvls\\Modified\\  ->  run this  ->  the disc
is re-patched, the stage is re-captured (still + panel + separate L/C/R stills + HQ &
small pan mp4), and the website is rebuilt.

    regen_stage.py 09 0F         # regen specific slots (hex)
    regen_stage.py --changed     # regen every slot whose Modified file is newer than the CDI
    regen_stage.py --all         # regen all 17 modified stages
    regen_stage.py 09 --no-site  # skip the website rebuild

In-place patching needs the edited file to match the disc slot SIZE (standard MvC2
stages always do; ModNao re-exports preserve it). Oversized foreign stages (e.g. CvS2)
need a full ISO rebuild -- this tool will say so and skip them.
"""
import os, sys, subprocess, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mvc2_disc as md
from config import MODIFIED_CDI as CDI, MODDIR, OUT_MODIFIED as OUT
ALL_SLOTS = [f"{i:02X}" for i in range(0x11)]


def _disc_map():
    size, tracks = md.parse_cdi(CDI)
    tr = max((t for t in tracks if t.mode in (1, 2) and t.length > 1000), key=lambda t: t.length)
    ss = tr.sector_size
    hlen = md._header_len(tr.mode, ss)
    base = tr.data_offset + tr.pregap_length * ss
    iso, start = md.build_iso(CDI)
    files = md.walk_iso(iso, start)
    disc = {n.upper(): (p, s) for n, p, s in files
            if n.upper().startswith("STG") and (n.upper().endswith("POL.BIN") or n.upper().endswith("TEX.BIN"))}
    return disc, base, ss, hlen


def patch_slot(slot, disc, f, base, ss, hlen):
    """Write STG<slot>{POL,TEX}.BIN from MODDIR into the open CDI. Returns list of msgs."""
    msgs = []
    for kind in ("POL", "TEX"):
        fn = f"STG{slot}{kind}.BIN"
        src = os.path.join(MODDIR, fn)
        if not os.path.exists(src) or fn not in disc:
            continue
        data = open(src, "rb").read()
        phys, fsize = disc[fn]
        if len(data) != fsize:
            msgs.append(f"  !! {fn}: size {len(data)} != disc {fsize} -- needs ISO rebuild, SKIPPED")
            continue
        off, sec = 0, phys
        while off < len(data):
            f.seek(base + sec * ss + hlen); f.write(data[off:off + 2048])
            off += 2048; sec += 1
        msgs.append(f"  patched {fn} ({fsize} B)")
    return msgs


def changed_slots(disc):
    cdi_mtime = os.path.getmtime(CDI)
    out = []
    for slot in ALL_SLOTS:
        for kind in ("POL", "TEX"):
            src = os.path.join(MODDIR, f"STG{slot}{kind}.BIN")
            if os.path.exists(src) and os.path.getmtime(src) > cdi_mtime:
                out.append(slot); break
    return out


def main():
    args = [a for a in sys.argv[1:]]
    do_site = "--no-site" not in args
    args = [a for a in args if a != "--no-site"]

    disc, base, ss, hlen = _disc_map()
    if "--all" in args:
        slots = ALL_SLOTS
    elif "--changed" in args:
        slots = changed_slots(disc)
        print("changed since CDI:", slots or "(none)")
    else:
        slots = [a.upper().zfill(2) for a in args]
    if not slots:
        print("nothing to do"); return

    # 1) patch the disc in place
    print(f"patching {len(slots)} slot(s) into {os.path.basename(CDI)} ...")
    with open(CDI, "r+b") as f:
        for slot in slots:
            print(f" STG{slot}:")
            for m in patch_slot(slot, disc, f, base, ss, hlen):
                print(m)

    # 2) capture each slot (subprocess keeps flycast state clean per run)
    hexargs = [str(int(s, 16)) for s in slots]
    env = dict(os.environ, PM_CDI=CDI, PM_OUT=OUT)
    print(f"\ncapturing slots {hexargs} ...")
    r = subprocess.run([sys.executable, os.path.join(HERE, "stage_batch.py"), *[f"{int(s,16):02X}" for s in slots]],
                       env=env, cwd=HERE)
    if r.returncode != 0:
        print("capture had errors (see above)")

    # 3) rebuild the website
    if do_site:
        print("\nrebuilding site ...")
        subprocess.run([sys.executable, os.path.join(HERE, "build_mockups.py")], cwd=HERE)
    print(f"\ndone @ {datetime.datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    main()
