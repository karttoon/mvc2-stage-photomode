#!/usr/bin/env python3
"""Build the MvC2 stage-showcase page (internal template) from real captures.

GROUPED BY STAGE (scales as stages grow): one card per stage. Click -> popup with a
Modified / Default FLIP toggle (compare the retexture in place), an autoplay+loop pan
video, and the three stills (Left/Center/Right). Click a still -> image lightbox
(fullscreen + X), no new tab. Names/order/status/links come from stage_meta.json.

Output: output/site_mockups/index.html  (+ assets/, lightweight jpg thumbs/stills)
"""
import os, sys, json, glob, shutil
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from config import OUTPUT as OUT, OUT_MODIFIED as MOD, OUT_DEFAULTS as DEF, SITE
ASSETS = os.path.join(SITE, "assets")
META = json.load(open(os.path.join(HERE, "stage_meta.json"), encoding="utf-8"))


def slot_of(tag):
    return tag.split("_", 1)[0][3:].upper()


def collect(root):
    out = {}
    for d in sorted(glob.glob(os.path.join(root, "stg*"))):
        tag = os.path.basename(d)
        still = os.path.join(d, f"{tag}_still.png")
        panel = os.path.join(d, f"{tag}_panel.png")
        if not (os.path.exists(still) and os.path.exists(panel)):
            continue
        out[slot_of(tag)] = {
            "tag": tag, "still": still, "panel": panel,
            "left": os.path.join(d, f"{tag}_left.png"),
            "right": os.path.join(d, f"{tag}_right.png"),
            "vid": os.path.join(d, f"{tag}_pan_small.mp4"),
        }
    return out


def _split_panel(panel_path, gap=10):
    im = Image.open(panel_path).convert("RGB")
    W, H = im.size
    h = H - 2 * gap
    cellW = (W - 4 * gap) // 3
    return (im.crop((gap, gap, gap + cellW, gap + h)),
            im.crop((3 * gap + 2 * cellW, gap, 3 * gap + 3 * cellW, gap + h)))


def _save(im, path, w, q=85):
    if isinstance(im, str):
        im = Image.open(im)
    im = im.convert("RGB")
    im.resize((w, int(im.height * w / im.width)), Image.LANCZOS).save(path, quality=q)


def prep(stage, base):
    """thumb + left/center/right stills + video. Returns web paths dict."""
    a = {}
    a["thumb"] = f"assets/{base}_thumb.jpg"
    _save(stage["still"], os.path.join(SITE, a["thumb"]), 420)
    a["c"] = f"assets/{base}_c.jpg";  _save(stage["still"], os.path.join(SITE, a["c"]), 760)
    if os.path.exists(stage["left"]) and os.path.exists(stage["right"]):
        limg, rimg = Image.open(stage["left"]), Image.open(stage["right"])
    else:
        limg, rimg = _split_panel(stage["panel"])
    a["l"] = f"assets/{base}_l.jpg"; _save(limg, os.path.join(SITE, a["l"]), 760)
    a["r"] = f"assets/{base}_r.jpg"; _save(rimg, os.path.join(SITE, a["r"]), 760)
    if os.path.exists(stage["vid"]):
        a["v"] = f"assets/{base}_pan.mp4"
        shutil.copyfile(stage["vid"], os.path.join(SITE, a["v"]))
    else:
        a["v"] = None
    return a


CSS = """
body{padding-top:40px;background:#fff;color:#000;font-family:'Courier New',Courier,monospace;}
a{color:#000;}
.nav{width:100%;font-size:13px;font-weight:bold;padding:14px 0;text-transform:uppercase;position:fixed;left:0;top:0;background:#fff;z-index:50;border-bottom:1px solid #000;}
.nav li{display:inline;padding-left:4em;}
.main{width:100%;padding:30px 0 6px;margin-top:20px;text-align:center;font-size:14px;}
.articles{width:90%;padding:0 5%;text-align:left;font-size:14px;}
.small{font-size:12px;color:#444;}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px;margin:16px 0 30px;}
.card{border:2px solid #000;background:#fff;cursor:pointer;transition:background .12s;}
.card:hover{background:#eee;}
.card img{display:block;width:100%;height:auto;border-bottom:2px solid #000;}
.card .cn{font-weight:bold;font-size:12px;text-transform:uppercase;padding:7px 8px 2px;}
.card .cs{font-size:10px;padding:0 8px 7px;}
.badge{display:inline-block;border:1px solid #000;padding:0 5px;font-size:10px;font-weight:bold;text-transform:uppercase;}
.b-done{background:#000;color:#fff;}
.b-wip{background:#fff;color:#000;}
.b-stock{background:#fff;color:#555;border-color:#999;}
/* tab box */
.box{border:2px solid #000;margin:14px 0 30px;}
.tabs{display:flex;border-bottom:2px solid #000;}
.tabs button{font-family:inherit;font-size:13px;font-weight:bold;text-transform:uppercase;padding:10px 26px;background:#fff;border:0;border-right:2px solid #000;cursor:pointer;}
.tabs button.on{background:#000;color:#fff;}
.tabs .count{margin-left:auto;padding:10px 16px;font-size:12px;color:#555;align-self:center;}
.tabpad{padding:16px;}
.tabpad .grid{margin:0;}
/* stage popup */
.lb{display:none;position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:100;overflow:auto;}
.lb.on{display:block;}
.lb .box2{background:#fff;border:2px solid #000;max-width:760px;margin:34px auto;}
.hd{display:flex;align-items:center;border-bottom:2px solid #000;padding:10px 14px;gap:10px;}
.hd h3{margin:0;font-size:15px;text-transform:uppercase;}
.hd .sp{flex:1;}
.hd .x{font-weight:bold;cursor:pointer;border:2px solid #000;padding:0 9px;}
.flip{display:inline-flex;border:2px solid #000;}
.flip button{font-family:inherit;font-size:11px;font-weight:bold;text-transform:uppercase;padding:4px 12px;background:#fff;border:0;border-right:2px solid #000;cursor:pointer;}
.flip button:last-child{border-right:0;}
.flip button.on{background:#000;color:#fff;}
.bd{padding:14px;}
.bd video{display:block;width:100%;max-width:620px;margin:0 auto 6px;border:1px solid #000;background:#000;}
.metarow{text-align:center;font-size:12px;margin:8px 0 14px;min-height:1em;}
.metarow a{border:1px solid #000;padding:2px 8px;margin:0 4px;text-decoration:none;font-weight:bold;}
.metarow a.dead{color:#999;border-color:#bbb;cursor:not-allowed;}
.stills{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;}
.st{border:1px solid #000;}
.st img{display:block;width:100%;cursor:zoom-in;}
.st .cap{display:flex;align-items:center;border-top:1px solid #000;font-size:11px;font-weight:bold;text-transform:uppercase;padding:3px 6px;}
.st .cap .lbl{flex:1;}
.st .cap a{text-decoration:none;border:1px solid #000;padding:0 4px;margin-left:3px;font-size:11px;}
/* image lightbox (level 2) */
.ilb{display:none;position:fixed;inset:0;background:rgba(0,0,0,.92);z-index:200;}
.ilb.on{display:flex;align-items:center;justify-content:center;}
.ilb img{max-width:94vw;max-height:88vh;border:2px solid #fff;}
.ilb .ix{position:fixed;top:14px;right:20px;color:#fff;border:2px solid #fff;padding:2px 12px;font-weight:bold;cursor:pointer;font-size:16px;}
.ilb .idl{position:fixed;top:14px;left:20px;color:#fff;border:2px solid #fff;padding:2px 12px;font-weight:bold;text-decoration:none;font-size:13px;}
"""

NAV = """<div class="nav"><div class="container"><ul id="menu">
<li><a href="/index.html">root@ropgadget[.]com:~#</a></li>
<li><a href="/main.html">_Zmain</a></li>
<li><a href="/about.html">disass</a></li>
<li><a href="/mvc2.html">MvC2</a></li>
<li><a href="/sections.html">.Sections</a></li>
<li><a href="/links.html">PLT</a></li>
</ul></div></div>"""


def main():
    if os.path.exists(SITE):
        shutil.rmtree(SITE)
    os.makedirs(ASSETS)
    mod, def_ = collect(MOD), collect(DEF)
    order = META["order"]
    smeta = META["stages"]

    mcards, dcards, data = [], [], []

    def card(idx, name, thumb, badge, lbl, start):
        return (f'<div class="card" onclick="openStage({idx},\'{start}\')">'
                f'<img loading="lazy" src="{thumb}">'
                f'<div class="cn">{name}</div>'
                f'<div class="cs"><span class="badge {badge}">{lbl}</span></div></div>')

    for slot in order:
        if slot not in mod and slot not in def_:
            continue
        m = smeta.get(slot, {})
        name = m.get("name", slot)
        status = m.get("status", "wip")
        mod_a = prep(mod[slot], f"m_{slot}") if slot in mod else None
        def_a = prep(def_[slot], f"d_{slot}") if slot in def_ else None
        idx = len(data)
        badge = {"done": "b-done", "wip": "b-wip"}.get(status, "b-stock")
        lbl = {"done": "done", "wip": "work in progress"}.get(status, "stock")
        if mod_a:
            mcards.append(card(idx, name, mod_a["thumb"], badge, lbl, "mod"))
        if def_a:
            dcards.append(card(idx, name, def_a["thumb"], "b-stock", "stock", "def"))
        data.append({
            "n": name, "st": status,
            "mod": mod_a, "def": def_a,
            "tex": m.get("texture_url", ""), "yt": m.get("yt_url", ""),
        })

    data_js = json.dumps(data)
    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>MvC2 Stage Archive</title><style>{CSS}</style></head><body>
{NAV}
<div class="main"><div class="container">/* gallery(stages) - MvC2 Stage Archive */</div></div>
<div class="articles"><div class="container">
<p class="small">Custom-retextured MvC2 stages, captured clean (no characters / HUD /
shadows). Click a stage for the pan video + left / center / right stills; inside, flip
between my <b>Modified</b> edit and the stock <b>Default</b> to compare.</p>
<div class="box">
 <div class="tabs">
  <button id="tabM" class="on" onclick="showTab('M')">Modified</button>
  <button id="tabD" onclick="showTab('D')">Default</button>
  <span class="count" id="count"></span>
 </div>
 <div class="tabpad">
  <div id="gridM" class="grid">{''.join(mcards)}</div>
  <div id="gridD" class="grid" style="display:none">{''.join(dcards)}</div>
 </div>
</div>
</div></div>

<!-- stage popup -->
<div class="lb" id="lb"><div class="box2">
 <div class="hd"><h3 id="lbT"></h3><span id="lbB"></span>
   <span id="lbFlip"></span><span class="sp"></span>
   <span class="x" onclick="closeStage()">[x]</span></div>
 <div class="bd">
   <div id="lbV"></div>
   <div class="metarow" id="lbM"></div>
   <div class="stills" id="lbS"></div>
 </div>
</div></div>

<!-- image lightbox -->
<div class="ilb" id="ilb">
  <a class="idl" id="ilbDL" download>&#x2913; download</a>
  <span class="ix" onclick="closeImg()">[x]</span>
  <img id="ilbImg">
</div>

<script>
var S={data_js}, CUR=0, VAR='mod';
function variant(){{ return S[CUR][VAR] || S[CUR].mod || S[CUR]['def']; }}
function render(){{
 var s=S[CUR], a=variant();
 // video: autoplay + loop + muted (muted required for autoplay)
 document.getElementById('lbV').innerHTML = a && a.v ?
   ('<video autoplay loop muted playsinline controls src="'+a.v+'"></video>') : '';
 // metadata only for the Modified variant of non-stock stages
 var meta='';
 if(VAR==='mod' && s.st!=='stock'){{
   meta='Texture: '+link(s.tex,'download .BIN')+' &nbsp; Video (HQ): '+link(s.yt,'YouTube');
 }} else if(VAR==='def') {{ meta='<span class="small">stock game art</span>'; }}
 document.getElementById('lbM').innerHTML=meta;
 document.getElementById('lbS').innerHTML = a ?
   (still('Left',a.l)+still('Center',a.c)+still('Right',a.r)) : '';
}}
function link(url,label){{ return url? '<a href="'+url+'" target="_blank">'+label+'</a>'
   : '<a class="dead" title="not available yet">'+label+' (soon)</a>'; }}
function still(lbl,src){{
 return '<figure class="st" style="margin:0"><img src="'+src+'" onclick="openImg(\\''+src+'\\')">'+
  '<div class="cap"><span class="lbl">'+lbl+'</span>'+
  '<a href="'+src+'" download title="download">&#x2913;</a></div></figure>';
}}
function showTab(t){{
 document.getElementById('tabM').classList.toggle('on',t==='M');
 document.getElementById('tabD').classList.toggle('on',t==='D');
 document.getElementById('gridM').style.display=t==='M'?'':'none';
 document.getElementById('gridD').style.display=t==='D'?'':'none';
 document.getElementById('count').textContent=
   document.getElementById(t==='M'?'gridM':'gridD').querySelectorAll('.card').length+' stages';
}}
function setVar(v){{ VAR=v;
 document.getElementById('bMod').classList.toggle('on',v==='mod');
 document.getElementById('bDef').classList.toggle('on',v==='def');
 render();
}}
function openStage(i,start){{
 CUR=i; VAR=start||'mod'; var s=S[i];
 document.getElementById('lbT').textContent=s.n;
 var bmap={{done:'b-done',wip:'b-wip',stock:'b-stock'}}, blbl={{done:'done',wip:'work in progress',stock:'stock'}};
 document.getElementById('lbB').innerHTML='<span class="badge '+(bmap[s.st]||'b-stock')+'">'+(blbl[s.st]||'stock')+'</span>';
 // flip toggle only when both variants exist
 document.getElementById('lbFlip').innerHTML = (s.mod && s['def']) ?
   ('<span class="flip"><button id="bMod" class="'+(VAR==='mod'?'on':'')+'" onclick="setVar(\\'mod\\')">Modified</button>'+
    '<button id="bDef" class="'+(VAR==='def'?'on':'')+'" onclick="setVar(\\'def\\')">Default</button></span>') : '';
 render();
 document.getElementById('lb').classList.add('on');
}}
function closeStage(){{ document.getElementById('lb').classList.remove('on');
 document.getElementById('lbV').innerHTML=''; }}
function openImg(src){{ document.getElementById('ilbImg').src=src;
 document.getElementById('ilbDL').href=src;
 document.getElementById('ilb').classList.add('on'); }}
function closeImg(){{ document.getElementById('ilb').classList.remove('on'); }}
document.getElementById('lb').addEventListener('click',function(e){{if(e.target===this)closeStage();}});
document.getElementById('ilb').addEventListener('click',function(e){{if(e.target===this)closeImg();}});
document.addEventListener('keydown',function(e){{ if(e.key!=='Escape')return;
 if(document.getElementById('ilb').classList.contains('on'))closeImg(); else closeStage(); }});
showTab('M');
</script>
</body></html>"""
    open(os.path.join(SITE, "index.html"), "w", encoding="utf-8").write(html)
    print(f"built {len(data)} stages (grouped, mod/def flip) -> {SITE}")


if __name__ == "__main__":
    main()
