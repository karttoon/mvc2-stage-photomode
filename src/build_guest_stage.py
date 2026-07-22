#!/usr/bin/env python3
"""Build a capture disc for SOMEONE ELSE'S stage, without touching any of your files.

Copies a clean base disc and patches just the given slot's TEX (and optional POL) into
that copy, in place. Your MvC2_Lvls\\Modified\\ folder and your own base discs are
never written to -- so guest stages can't clobber your own work.

    build_guest_stage.py <slotHex> <tex.bin> <out.cdi> [--pol <pol.bin>] [--base <base.cdi>]

Sizes: a guest file smaller than the disc slot is zero-padded to fit. An OVERSIZED
texture is written into another slot's texture region (a sacrificial 'donor' --
safe because this disc only ever loads the one slot) and this file's ISO9660
directory record is repointed at it, so no ISO rebuild is needed.
"""
import os, sys, shutil, struct
from build_custom_stage import find_records, _cdi_off
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

    recs, bias = find_records(iso, {f"STG{i:02X}TEX.BIN" for i in range(0x11)} |
                                   {f"STG{slot}POL.BIN"})

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
                # OVERSIZED. A guest capture disc only ever loads this one slot, so we
                # can sacrifice another slot's texture region: write the full file
                # there and repoint this file's ISO9660 directory record at it.
                if kind != "TEX":
                    raise SystemExit(f"{fn}: {len(data)} > slot {fsize}; oversized POL unsupported")
                cands = [(nm, r) for nm, r in recs.items()
                         if nm.endswith("TEX.BIN") and nm != fn and r[3] >= len(data)]
                if not cands:
                    raise SystemExit(f"{fn}: {len(data)} bytes -- no donor slot big enough")
                dnm, (_, _, delba, dcap) = max(cands, key=lambda kv: kv[1][3])
                dphys = delba - bias
                for k in range((len(data) + 2047) // 2048):
                    f.seek(disc_base + (dphys + k) * ss + hlen)
                    f.write(data[k * 2048:(k + 1) * 2048])
                dirsec, off = recs[fn][0], recs[fn][1]
                db = dirsec * 2048 + off
                f.seek(_cdi_off(disc_base, ss, hlen, db + 2));  f.write(struct.pack('<I', delba))
                f.seek(_cdi_off(disc_base, ss, hlen, db + 6));  f.write(struct.pack('>I', delba))
                f.seek(_cdi_off(disc_base, ss, hlen, db + 10)); f.write(struct.pack('<I', len(data)))
                f.seek(_cdi_off(disc_base, ss, hlen, db + 14)); f.write(struct.pack('>I', len(data)))
                print(f"  {fn} oversized ({len(data)} > {fsize}) -> donor {dnm} "
                      f"(cap {dcap}) + dir-record repoint")
                continue

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
