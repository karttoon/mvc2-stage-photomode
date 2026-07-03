#!/usr/bin/env python3
"""
mvc2_disc.py - Extract MvC2 fighting-stage files (STG*POL.BIN / STG*TEX.BIN)
from Dreamcast .cdi disc images.

Pipeline:
  1. Parse the CDI footer (DiscJuggler format, port of cdirip 0.6.4) to locate
     the main data track and dump its 2048-byte user sectors into one ISO buffer.
  2. Walk the ISO9660 filesystem with an auto-detecting LBA-bias scheme that
     handles BOTH relative-addressed discs (start_lba 0; most mixes) and
     absolute-addressed discs (e.g. AccurateMix, start_lba 11702).
  3. Return {FILENAME.BIN: bytes} for the 17 fighting-stage files only.
"""
import os, struct, sys

def is_stage_file(name):
    u=name.upper()
    return u.startswith('STG') and (u.endswith('POL.BIN') or u.endswith('TEX.BIN'))

# ---------------------------------------------------------------- CDI footer
CDI_V2, CDI_V3, CDI_V35 = 0x80000004, 0x80000005, 0x80000006

class Track:
    __slots__=('mode','sector_size','pregap_length','length','total_length',
               'start_lba','data_offset')

def parse_cdi(path):
    f=open(path,'rb')
    f.seek(0,2); length=f.tell()
    if length<8: raise ValueError("image too short")
    f.seek(length-8)
    version,header_offset=struct.unpack('<II',f.read(8))
    if header_offset==0: raise ValueError("bad image (no header_offset)")
    if version not in (CDI_V2,CDI_V3,CDI_V35):
        raise ValueError("unsupported CDI version 0x%08x"%version)
    f.seek(length-header_offset if version==CDI_V35 else header_offset)
    (sessions,)=struct.unpack('<H',f.read(2))
    tracks=[]; cursor=0
    for s in range(sessions):
        (ntracks,)=struct.unpack('<H',f.read(2))
        for t in range(ntracks):
            tr=_read_track(f,version)
            tr.data_offset=cursor
            cursor+=tr.total_length*tr.sector_size
            tracks.append(tr)
        f.read(4); f.read(8)
        if version!=CDI_V2: f.read(1)
    f.close()
    return length,tracks

def _read_track(f,version):
    (tv,)=struct.unpack('<I',f.read(4))
    if tv!=0: f.read(8)
    f.read(10); f.read(10)   # two track start marks
    f.read(4)
    (flen,)=struct.unpack('<B',f.read(1))
    f.read(flen); f.read(11); f.read(4); f.read(4)
    (tv,)=struct.unpack('<I',f.read(4))
    if tv==0x80000000: f.read(8)
    f.read(2)
    tr=Track()
    (tr.pregap_length,)=struct.unpack('<I',f.read(4))
    (tr.length,)=struct.unpack('<i',f.read(4))
    f.read(6)
    (tr.mode,)=struct.unpack('<I',f.read(4))
    f.read(12)
    (tr.start_lba,)=struct.unpack('<I',f.read(4))
    (tr.total_length,)=struct.unpack('<I',f.read(4))
    f.read(16)
    (ssv,)=struct.unpack('<I',f.read(4))
    tr.sector_size={0:2048,1:2336,2:2352}.get(ssv)
    if tr.sector_size is None: raise ValueError("bad sector size %d"%ssv)
    if tr.mode>2: raise ValueError("unsupported track mode %d"%tr.mode)
    f.read(29)
    if version!=CDI_V2:
        f.read(5)
        (tv,)=struct.unpack('<I',f.read(4))
        if tv==0xffffffff: f.read(78)
    return tr

def _header_len(mode,ss):
    if mode==2: return {2352:24,2336:8}.get(ss,0)
    return {2352:16}.get(ss,0)

def build_iso(path):
    """Return (iso_bytes, start_lba) for the main data track."""
    size,tracks=parse_cdi(path)
    data_tracks=[t for t in tracks if t.mode in (1,2) and t.length>1000]
    if not data_tracks: raise ValueError("no data track")
    tr=max(data_tracks,key=lambda t:t.length)
    hlen=_header_len(tr.mode,tr.sector_size)
    start=tr.data_offset+tr.pregap_length*tr.sector_size
    f=open(path,'rb'); f.seek(start)
    out=bytearray()
    ss=tr.sector_size
    # read in big chunks for speed
    CH=4096
    remaining=tr.length
    while remaining>0:
        n=min(CH,remaining)
        raw=f.read(n*ss)
        if len(raw)<n*ss: n=len(raw)//ss
        if n==0: break
        for k in range(n):
            out+=raw[k*ss+hlen:k*ss+hlen+2048]
        remaining-=n
    f.close()
    return bytes(out),tr.start_lba

# ------------------------------------------------------ ISO9660 walk (buffered)
def _sec(iso,n): return iso[n*2048:(n+1)*2048]

def _parse_dir(iso,phys_lba,size):
    blob=iso[phys_lba*2048: phys_lba*2048 + ((size+2047)//2048)*2048]
    i=0; n=len(blob); out=[]
    while i<n:
        rl=blob[i]
        if rl==0:
            nxt=((i//2048)+1)*2048
            if nxt<=i: break
            i=nxt; continue
        rec=blob[i:i+rl]
        if len(rec)<33: break
        elba=struct.unpack('<I',rec[2:6])[0]
        sz=struct.unpack('<I',rec[10:14])[0]
        fl=rec[25]; nl=rec[32]; nm=rec[33:33+nl]
        out.append((nm,elba,sz,fl))
        i+=rl
    return out

def _find_pvd(iso):
    for s in range(16, 64):
        sec=_sec(iso,s)
        if sec[1:6]==b'CD001' and sec[0]==1:
            return s
    return None

def walk_iso(iso,start_lba):
    """Yield (name, phys_lba, size) for files. Auto-detects LBA bias."""
    pvds=_find_pvd(iso)
    if pvds is None: return []
    pvd=_sec(iso,pvds)
    root=pvd[156:156+34]
    root_lba=struct.unpack('<I',root[2:6])[0]
    root_size=struct.unpack('<I',root[10:14])[0]
    # detect bias: stored_lba - bias = physical sector in iso buffer.
    # A valid ISO9660 root directory ALWAYS begins with '.' (name 0x00) and
    # '..' (name 0x01) self-entries -- use that as the definitive signature.
    bias=None
    for b in (start_lba,0,root_lba-23,root_lba-20):
        if b is None or b<0 or (root_lba-b)<0: continue
        recs=_parse_dir(iso,root_lba-b,root_size)
        if len(recs)>=2 and recs[0][0]==b'\x00' and recs[1][0]==b'\x01':
            bias=b; break
    if bias is None: return []
    files=[]; stack=[('',root_lba,root_size)]; seen=set()
    while stack:
        prefix,lba,size=stack.pop()
        key=(lba,size)
        if key in seen: continue
        seen.add(key)
        phys=lba-bias
        if phys<0: continue
        for nm,elba,sz,fl in _parse_dir(iso,phys,size):
            if nm in (b'\x00',b'\x01'): continue
            try: name=nm.split(b';')[0].decode('ascii')
            except Exception: continue
            if fl&2:
                stack.append((prefix+'/'+name,elba,sz))
            else:
                files.append((name,elba-bias,sz))
    return files

def extract_stage_files(path,verbose=True):
    iso,start_lba=build_iso(path)
    files=walk_iso(iso,start_lba)
    stage={}
    for name,phys,size in files:
        if is_stage_file(name):
            stage[name.upper()]=iso[phys*2048: phys*2048+size]
    if verbose:
        print(f"  iso={len(iso)//1048576}MB start_lba={start_lba} files={len(files)} stages={len(stage)}")
    return stage

if __name__=='__main__':
    import hashlib
    st=extract_stage_files(sys.argv[1])
    for k in sorted(st):
        print(f"  {k:14s} {len(st[k]):>9d} {hashlib.md5(st[k]).hexdigest()}")
    print("total:",len(st))
