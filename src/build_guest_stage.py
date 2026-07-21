#!/usr/bin/env python3
"""Build a capture disc for SOMEONE ELSE'S stage, without touching any of your files.

Copies a clean base disc and patches just the given slot's TEX (and optional POL) into
that copy, in place. Your MvC2_Lvls\\Modified\\ folder and your own base discs are
never written to -- so guest stages can't clobber your own work.

    build_guest_stage.py <slotHex> <tex.bin> <out.cdi> [--pol <pol.bin>] [--base <base.cdi>]

Sizes: a guest file smaller than the disc slot is zero-padded to fit. Larger than the
slot is rejected -- for an oversized/foreign stage use build_custom_stage.py instead
(Training slot + donor repoint).
"""
import os, sys, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mvc2_disc as md
from config import DEFAULTS_CDI as DEFAULT_BASE


def build(slot, tex_path, out_cdi, pol_path=None, base=DEFAULT_BASE):
    slot = slot.upper().zfill(2)
    print(f"copying base -> {os.path.basename(out_cdi)} ...")
    shutil.copyfile(base, out_cdi)

    size, tracks = md.parse_cdi(out_cdi)
    tr = max((t for t in tracks if t.mode in (1, 2) and t.length > 1000), key=lambda t: t.length)
    ss = tr.sector_size
    hlen = md._header_len(tr.mode, ss)
    disc_base = tr.data_offset + tr.pregap_length * ss
    iso, start = md.build_iso(out_cdi)
    disc = {n.upper(): (p, s) for n, p, s in md.walk_iso(iso, start)
            if n.upper().startswith("STG")}

    with open(out_cdi, "r+b") as f:
        for kind, src in (("TEX", tex_path), ("POL", pol_path)):
            if not src:
                continue
            fn = f"STG{slot}{kind}.BIN"
            if fn not in disc:
                raise SystemExit(f"{fn} not on disc")
            data = open(src, "rb").read()
            phys, fsize = disc[fn]
            if len(data) > fsize:
                raise SystemExit(
                    f"{fn}: {len(data)} bytes > disc slot {fsize}. Oversized guest stage --\n"
                    f"use build_custom_stage.py (Training slot + donor repoint) instead.")
            if len(data) < fsize:
                data += b"\x00" * (fsize - len(data))     # pad to the slot
            for k in range((len(data) + 2047) // 2048):
                f.seek(disc_base + (phys + k) * ss + hlen)
                f.write(data[k * 2048:(k + 1) * 2048])
            print(f"  patched {fn} ({os.path.getsize(src)} -> {fsize} bytes)")
    print("built ->", out_cdi)
    return out_cdi


def main():
    a = sys.argv[1:]
    pol = base = None
    for flag, var in (("--pol", "pol"), ("--base", "base")):
        if flag in a:
            i = a.index(flag)
            val = a[i + 1]
            a = a[:i] + a[i + 2:]
            if var == "pol":
                pol = val
            else:
                base = val
    if len(a) != 3:
        raise SystemExit(__doc__)
    slot, tex, out = a
    build(slot, tex, out, pol, base or DEFAULT_BASE)


if __name__ == "__main__":
    main()
