#!/usr/bin/env python3
"""Build a capture disc for a NON-STANDARD (foreign / oversized) static stage by
placing it in the non-animated TRAINING slot (STG0B).

Why: MvC2's animated stage slots crash on a static foreign stage (no animation data),
so only the Training slot is safe. But a foreign TEX can exceed the Training TEX slot
(1,064,960). Since a capture disc only ever loads STG0B, we:
  * patch the POL into the Training POL slot in place (padded);
  * if the TEX fits the Training TEX slot -> patch it in place (padded);
  * else (oversized) write the FULL TEX into a big SACRIFICIAL donor slot (STG00TEX,
    1,671,168) and REPOINT STG0BTEX's ISO9660 directory record at it.
MvC2 resolves stage files through the filesystem, so the repoint is honoured.

    build_custom_stage.py <pol.bin> <tex.bin> <out.cdi>
    build_custom_stage.py <folder-with-STG0BPOL/TEX> <out.cdi>
"""
import os, sys, shutil, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mvc2_disc as md
from config import DEFAULTS_CDI as BASE
DONOR = "STG00TEX.BIN"        # sacrificial big slot, 1,671,168 (816 sectors)


def _iso_offsets(cdi):
    size, tracks = md.parse_cdi(cdi)
    tr = max((t for t in tracks if t.mode in (1, 2) and t.length > 1000), key=lambda t: t.length)
    ss = tr.sector_size
    return tr.data_offset + tr.pregap_length * ss, ss, md._header_len(tr.mode, ss)


def _cdi_off(base, ss, hlen, iso_byte):
    sec, within = divmod(iso_byte, 2048)
    return base + sec * ss + hlen + within


def find_records(iso, targets):
    """{NAME: (dir_phys_lba, off_in_dir, elba, size)} + bias."""
    pvd = md._sec(iso, md._find_pvd(iso))
    root = pvd[156:156 + 34]
    root_lba, root_size = struct.unpack('<I', root[2:6])[0], struct.unpack('<I', root[10:14])[0]
    bias = None
    for b in (0, root_lba - 23, root_lba - 20):
        recs = md._parse_dir(iso, root_lba - b, root_size)
        if len(recs) >= 2 and recs[0][0] == b'\x00' and recs[1][0] == b'\x01':
            bias = b; break
    found, stack, seen = {}, [(root_lba, root_size)], set()
    while stack:
        lba, size = stack.pop()
        if (lba, size) in seen:
            continue
        seen.add((lba, size))
        phys = lba - bias
        blob = iso[phys * 2048: phys * 2048 + ((size + 2047) // 2048) * 2048]
        i = 0
        while i < len(blob):
            rl = blob[i]
            if rl == 0:
                nxt = ((i // 2048) + 1) * 2048
                if nxt <= i:
                    break
                i = nxt; continue
            rec = blob[i:i + rl]
            if len(rec) < 33:
                break
            elba = struct.unpack('<I', rec[2:6])[0]
            sz = struct.unpack('<I', rec[10:14])[0]
            fl, nl = rec[25], rec[32]
            name = rec[33:33 + nl].split(b';')[0].decode('ascii', 'ignore')
            if fl & 2 and rec[33:33 + nl] not in (b'\x00', b'\x01'):
                stack.append((elba, sz))
            elif name.upper() in targets:
                found[name.upper()] = (phys, i, elba, sz)
            i += rl
    return found, bias


def _write_slot(f, base, ss, hlen, phys, data):
    for k in range((len(data) + 2047) // 2048):
        f.seek(base + (phys + k) * ss + hlen)
        f.write(data[k * 2048:(k + 1) * 2048])


def build(pol_path, tex_path, dst):
    pol = open(pol_path, "rb").read()
    tex = open(tex_path, "rb").read()
    print(f"POL {len(pol)}  TEX {len(tex)}")
    shutil.copyfile(BASE, dst)
    base, ss, hlen = _iso_offsets(dst)
    iso, start = md.build_iso(dst)
    recs, bias = find_records(iso, {"STG0BPOL.BIN", "STG0BTEX.BIN", DONOR})

    pol_phys, pol_slot = recs["STG0BPOL.BIN"][2] - bias, recs["STG0BPOL.BIN"][3]
    tex_phys, tex_slot = recs["STG0BTEX.BIN"][2] - bias, recs["STG0BTEX.BIN"][3]
    tex_dir_phys, tex_off = recs["STG0BTEX.BIN"][0], recs["STG0BTEX.BIN"][1]
    donor_elba, donor_cap = recs[DONOR][2], recs[DONOR][3]

    if len(pol) > pol_slot:
        raise SystemExit(f"POL {len(pol)} exceeds Training POL slot {pol_slot} -- not supported")
    if len(tex) > donor_cap:
        raise SystemExit(f"TEX {len(tex)} exceeds donor slot {donor_cap} -- need a bigger donor")

    f = open(dst, "r+b")
    # POL: in-place (padded)
    _write_slot(f, base, ss, hlen, pol_phys, pol + b"\x00" * (pol_slot - len(pol)))
    print(f"  POL -> Training slot in place ({len(pol)}/{pol_slot})")
    if len(tex) <= tex_slot:
        # TEX fits Training slot: in-place (padded), no repoint
        _write_slot(f, base, ss, hlen, tex_phys, tex + b"\x00" * (tex_slot - len(tex)))
        print(f"  TEX -> Training slot in place ({len(tex)}/{tex_slot})")
    else:
        # oversized: write into donor + repoint STG0BTEX directory record
        _write_slot(f, base, ss, hlen, donor_elba - bias, tex)
        db = tex_dir_phys * 2048 + tex_off
        f.seek(_cdi_off(base, ss, hlen, db + 2));  f.write(struct.pack('<I', donor_elba))
        f.seek(_cdi_off(base, ss, hlen, db + 6));  f.write(struct.pack('>I', donor_elba))
        f.seek(_cdi_off(base, ss, hlen, db + 10)); f.write(struct.pack('<I', len(tex)))
        f.seek(_cdi_off(base, ss, hlen, db + 14)); f.write(struct.pack('>I', len(tex)))
        print(f"  TEX oversized -> donor {DONOR} + repointed dir record ({len(tex)})")
    f.close()
    print("built ->", dst)
    return dst


def main():
    a = sys.argv[1:]
    if len(a) == 2 and os.path.isdir(a[0]):
        folder, dst = a
        pol = os.path.join(folder, "STG0BPOL.BIN")
        tex = os.path.join(folder, "STG0BTEX.BIN")
    elif len(a) == 3:
        pol, tex, dst = a
    else:
        raise SystemExit(__doc__)
    build(pol, tex, dst)


if __name__ == "__main__":
    main()
