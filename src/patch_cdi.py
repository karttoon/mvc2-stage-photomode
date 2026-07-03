#!/usr/bin/env python3
"""Patch stage POL/TEX files into a CDI disc image IN PLACE (same-size files only).

Maps ISO9660 file extents back to raw CDI offsets (accounting for the data
track's sector layout / mode-2 subheader) and overwrites the user-data bytes.
EDC/ECC for mode-2 sectors is NOT recomputed -- Flycast ignores it.

Usage: patch_cdi.py <src.cdi> <dst.cdi> <moddir>
"""
import os, shutil, struct, sys, hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mvc2_disc as md


def main(src, dst, moddir):
    print(f"copying {src} -> {dst} ...")
    shutil.copyfile(src, dst)

    size, tracks = md.parse_cdi(dst)
    data_tracks = [t for t in tracks if t.mode in (1, 2) and t.length > 1000]
    tr = max(data_tracks, key=lambda t: t.length)
    ss = tr.sector_size
    hlen = md._header_len(tr.mode, ss)
    base = tr.data_offset + tr.pregap_length * ss
    print(f"data track: mode={tr.mode} ss={ss} hlen={hlen} base=0x{base:X} start_lba={tr.start_lba}")

    iso, start_lba = md.build_iso(dst)
    files = md.walk_iso(iso, start_lba)
    disc = {}
    for name, phys, fsize in files:
        u = name.upper()
        if u.startswith("STG") and (u.endswith("POL.BIN") or u.endswith("TEX.BIN")):
            disc[u] = (phys, fsize)

    patched, skipped = 0, []
    f = open(dst, "r+b")
    for fn in sorted(os.listdir(moddir)):
        u = fn.upper()
        if u not in disc:
            continue
        data = open(os.path.join(moddir, fn), "rb").read()
        phys, fsize = disc[u]
        if len(data) != fsize:
            skipped.append((u, len(data), fsize))
            continue
        # sanity: current disc bytes must equal the iso extraction
        assert iso[phys * 2048 : phys * 2048 + fsize] is not None
        off = 0
        sec = phys
        while off < len(data):
            chunk = data[off : off + 2048]
            f.seek(base + sec * ss + hlen)
            f.write(chunk)
            off += 2048
            sec += 1
        patched += 1
        print(f"  patched {u:14s} {fsize:>8d} bytes @ iso sector {phys}")
    f.close()

    for u, m, d in skipped:
        print(f"  SKIPPED (size) {u} mod={m} disc={d}")
    print(f"patched {patched} files")

    # verify: re-extract from dst and hash-compare
    iso2, sl2 = md.build_iso(dst)
    files2 = {n.upper(): (p, s) for n, p, s in md.walk_iso(iso2, sl2)}
    bad = 0
    for fn in sorted(os.listdir(moddir)):
        u = fn.upper()
        if u not in disc:
            continue
        data = open(os.path.join(moddir, fn), "rb").read()
        phys, fsize = files2[u]
        if len(data) != fsize:
            continue
        got = iso2[phys * 2048 : phys * 2048 + fsize]
        if hashlib.md5(got).hexdigest() != hashlib.md5(data).hexdigest():
            print(f"  VERIFY FAIL {u}")
            bad += 1
    print("verify:", "ALL OK" if bad == 0 else f"{bad} FAILURES")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
