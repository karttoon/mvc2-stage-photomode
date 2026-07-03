#!/usr/bin/env python3
"""INTERNAL stage-capture tool (local only -- never expose this).

Run it, open the printed URL. Pick a stage, upload a texture (.BIN) -- and for a
non-standard/foreign stage also a POL -- and it orchestrates the whole thing: patch or
build the disc, launch Flycast, capture, and show you the 3 stills + 2 videos (+ panel).

  Standard stage : uploads STG<slot>TEX.BIN into MvC2_Lvls\\Modified\\, runs regen_stage
                   (re-patches the Modified disc, captures, rebuilds the gallery).
  Custom stage   : uploads POL+TEX, builds a Training-slot capture disc (donor-repoint
                   for oversized textures), captures stage 0B.

No auth, runs local commands -> your machine only.  python internal_tool.py
"""
import os, sys, json, subprocess, urllib.parse, http.server, socketserver, webbrowser, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from config import MODDIR, OUTPUT as OUT, SITE, MODIFIED_CDI as MOD_CDI, CUSTOM_CDI
UP = os.path.join(HERE, "_uploads")
PORT = 8765

META = json.load(open(os.path.join(HERE, "stage_meta.json"), encoding="utf-8"))
# slot hex -> (folder tag name, display). Standard slots are 00..10.
STD = {s: META["stages"][s]["name"] for s in META["order"] if s != "CV"}
# folder tag suffix per slot, from the existing modified/ folders
import glob
TAG = {}
for d in glob.glob(os.path.join(OUT, "modified", "stg*")):
    t = os.path.basename(d); TAG[t[3:5].upper()] = t


def _opts():
    o = "".join(f'<option value="{s}">STG{s} — {n}</option>' for s, n in STD.items())
    return o + '<option value="custom">Custom / foreign stage (Training slot)</option>'


PAGE = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Stage Capture (internal)</title>
<style>
body{{font-family:'Courier New',monospace;background:#fff;color:#000;max-width:900px;margin:36px auto;padding:0 16px;}}
h1{{font-size:18px;text-transform:uppercase;border-bottom:2px solid #000;padding-bottom:8px;}}
label{{font-weight:bold;text-transform:uppercase;font-size:12px;display:block;margin:14px 0 4px;}}
select,input[type=file]{{font-family:inherit;font-size:13px;padding:6px;border:2px solid #000;width:100%;box-sizing:border-box;}}
button{{font-family:inherit;font-size:14px;font-weight:bold;text-transform:uppercase;padding:10px 26px;background:#000;color:#fff;border:2px solid #000;cursor:pointer;margin-top:16px;}}
button:disabled{{background:#888;border-color:#888;cursor:default;}}
.small{{font-size:12px;color:#555;}}
#log{{white-space:pre-wrap;background:#111;color:#0f0;padding:12px;margin-top:16px;font-size:12px;min-height:40px;border:2px solid #000;display:none;}}
.spin{{display:none;margin-top:12px;font-weight:bold;text-transform:uppercase;}}
#res{{display:none;margin-top:20px;}}
#res h2{{font-size:15px;text-transform:uppercase;border-bottom:2px solid #000;}}
.vids{{display:grid;grid-template-columns:1fr 1fr;gap:12px;}}
.vids video{{width:100%;border:2px solid #000;background:#000;}}
.stills{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-top:12px;}}
.stills figure{{margin:0;border:2px solid #000;}}
.stills img{{display:block;width:100%;}}
.stills figcaption{{font-size:11px;font-weight:bold;text-transform:uppercase;text-align:center;border-top:2px solid #000;padding:3px;}}
a.btn{{display:inline-block;border:2px solid #000;padding:6px 16px;text-decoration:none;color:#000;font-weight:bold;text-transform:uppercase;font-size:12px;margin-top:14px;}}
#polrow{{display:none;}}
</style></head><body>
<h1>MvC2 Stage Capture &mdash; internal</h1>
<p class="small">Pick a stage, upload its texture (.BIN). For a custom/foreign stage also
upload the POL. It patches/builds the disc, captures in Flycast (~2 min), and shows the
media. Standard stages also update the gallery.</p>
<label>Stage</label>
<select id="stage" onchange="onStage()">{opts}</select>
<label>Texture (STGxxTEX.BIN)</label><input type="file" id="tex" accept=".bin,.BIN">
<div id="polrow"><label>POL (STGxxPOL.BIN) &mdash; required for custom</label><input type="file" id="pol" accept=".bin,.BIN"></div>
<button id="go" onclick="run()">Generate</button>
<div class="spin" id="spin">&#9881; working&hellip; Flycast is capturing (~2 min)&hellip;</div>
<div id="log"></div>
<div id="res"><h2>Result</h2>
  <div class="vids"><div><div class="small">Small (share)</div><video id="vs" controls loop muted></video></div>
    <div><div class="small">HQ</div><video id="vh" controls loop muted></video></div></div>
  <div class="stills">
    <figure><img id="il"><figcaption>Left</figcaption></figure>
    <figure><img id="ic"><figcaption>Center</figcaption></figure>
    <figure><img id="ir"><figcaption>Right</figcaption></figure></div>
  <a class="btn" href="/gallery" target="_blank">Open gallery &#8599;</a>
</div>
<script>
function onStage(){{ document.getElementById('polrow').style.display =
  document.getElementById('stage').value==='custom' ? 'block':'none'; }}
function up(slot,kind,file){{ return fetch('/upload?slot='+slot+'&kind='+kind,{{method:'POST',body:file}}); }}
async function run(){{
 var slot=document.getElementById('stage').value;
 var tex=document.getElementById('tex').files[0];
 var pol=document.getElementById('pol').files[0];
 var log=document.getElementById('log'), spin=document.getElementById('spin'), go=document.getElementById('go');
 log.style.display='block'; log.textContent='';
 if(!tex){{ log.textContent='Pick a texture .BIN first.'; return; }}
 if(slot==='custom' && !pol){{ log.textContent='Custom stage needs a POL .BIN too.'; return; }}
 go.disabled=true; spin.style.display='block';
 try{{
   await up(slot,'tex',tex);
   if(pol) await up(slot,'pol',pol);
   var r=await fetch('/generate?slot='+slot,{{method:'POST'}});
   var j=await r.json();
   log.textContent=j.log;
   if(j.ok){{
     document.getElementById('vs').src=j.small; document.getElementById('vh').src=j.hq;
     document.getElementById('il').src=j.left; document.getElementById('ic').src=j.center;
     document.getElementById('ir').src=j.right; document.getElementById('res').style.display='block';
   }}
 }}catch(e){{ log.textContent+='\\nERROR: '+e; }}
 spin.style.display='none'; go.disabled=false;
}}
onStage();
</script></body></html>"""


def _capture(cdi, slot_hex, out_dir):
    env = dict(os.environ, PM_CDI=cdi, PM_OUT=out_dir)
    return subprocess.run([sys.executable, os.path.join(HERE, "stage_batch.py"), f"{slot_hex:02X}"],
                          cwd=HERE, env=env, capture_output=True, text=True)


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/plain; charset=utf-8"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers()
        self.wfile.write(b)

    def _serve(self, root, rel):
        fp = os.path.normpath(os.path.join(root, urllib.parse.unquote(rel)))
        if fp.startswith(os.path.normpath(root)) and os.path.isfile(fp):
            import mimetypes
            with open(fp, "rb") as fh:
                return self._send(200, fh.read(), mimetypes.guess_type(fp)[0] or "application/octet-stream")
        return self._send(404, "not found")

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if p.path in ("/", "/index.html"):
            return self._send(200, PAGE.format(opts=_opts()), "text/html; charset=utf-8")
        if p.path == "/gallery":
            self.send_response(302); self.send_header("Location", "/site/index.html"); self.end_headers(); return
        if p.path.startswith("/site/"):
            return self._serve(SITE, p.path[len("/site/"):])
        if p.path.startswith("/media/"):
            return self._serve(OUT, p.path[len("/media/"):])
        return self._send(404, "not found")

    def do_POST(self):
        p = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(p.query)
        if p.path == "/upload":
            os.makedirs(UP, exist_ok=True)
            slot = q.get("slot", [""])[0]; kind = q.get("kind", [""])[0]
            data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            fn = f"{'CUSTOM' if slot == 'custom' else 'STG' + slot}{kind.upper()}.BIN"
            open(os.path.join(UP, fn), "wb").write(data)
            return self._send(200, "ok")
        if p.path == "/generate":
            slot = q.get("slot", [""])[0]
            try:
                return self._generate(slot)
            except Exception as e:
                return self._send(200, json.dumps({"ok": False, "log": f"ERROR: {e}"}), "application/json")
        return self._send(404, "not found")

    def _result(self, out_dir, tag, log, ok=True):
        base = f"/media/{os.path.relpath(os.path.join(out_dir, tag), OUT).replace(os.sep, '/')}/{tag}"
        return self._send(200, json.dumps({
            "ok": ok, "log": log,
            "small": base + "_pan_small.mp4", "hq": base + "_pan.mp4",
            "left": base + "_left.png", "center": base + "_still.png", "right": base + "_right.png",
        }), "application/json")

    def _generate(self, slot):
        if slot == "custom":
            pol = os.path.join(UP, "CUSTOMPOL.BIN"); tex = os.path.join(UP, "CUSTOMTEX.BIN")
            log = ["building custom Training-slot disc ..."]
            r = subprocess.run([sys.executable, os.path.join(HERE, "build_custom_stage.py"), pol, tex, CUSTOM_CDI],
                               cwd=HERE, capture_output=True, text=True)
            log.append(r.stdout + (("\n" + r.stderr) if r.stderr else ""))
            out_dir = os.path.join(OUT, "custom")
            log.append("capturing (Flycast, ~2 min) ...")
            c = _capture(CUSTOM_CDI, 0x0B, out_dir)
            log.append(c.stdout[-600:] + (("\n" + c.stderr[-400:]) if c.stderr else ""))
            ok = "DONE (" in c.stdout
            return self._result(out_dir, "stg0B_Training", "\n".join(log), ok)
        # standard slot
        s = slot.upper()
        for kind in ("TEX", "POL"):
            src = os.path.join(UP, f"STG{s}{kind}.BIN")
            if os.path.exists(src):
                shutil.copyfile(src, os.path.join(MODDIR, f"STG{s}{kind}.BIN"))
        log = [f"copied upload(s) -> Modified\\, regenerating STG{s} ..."]
        r = subprocess.run([sys.executable, os.path.join(HERE, "regen_stage.py"), s],
                           cwd=HERE, capture_output=True, text=True)
        log.append((r.stdout or "")[-1200:] + (("\n" + r.stderr[-400:]) if r.stderr else ""))
        ok = "DONE (" in (r.stdout or "")
        tag = TAG.get(s) or f"stg{s}_Stage"
        return self._result(os.path.join(OUT, "modified"), tag, "\n".join(log), ok)


def main():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), H) as httpd:
        url = f"http://127.0.0.1:{PORT}/"
        print(f"internal stage-capture tool: {url}\n(Ctrl+C to stop)")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        httpd.serve_forever()


if __name__ == "__main__":
    main()
