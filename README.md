# mvc2-stage-photomode

A "photo mode" for **Marvel vs Capcom 2** stages running in the
[Flycast](https://github.com/flyinghead/flycast) emulator. It strips the characters,
HUD, shadows and effects at runtime, drives an invisible camera across the stage, and
captures clean showcase media — then builds a small website gallery from it.

Per stage you get:

- `*_still.png` — round-start center framing
- `*_left.png` / `*_right.png` / `*_panel.png` — the pan's far edges (and a 3-up strip)
- `*_pan.mp4` — HQ pan video, right→left, ~15 s, moving from frame 0
- `*_pan_small.mp4` — a ~2–4 MB H.264 share encode

It works on the 17 built-in stages (as *modified* and *stock* sets) **and** on
non-standard / foreign stages loaded into the Training slot (e.g. the CvS2 rooftop
ports). It can also load an **oversized** texture that doesn't fit the disc slot,
without an ISO rebuild — see [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md).

> This grew out of a personal project; it's shared so others can build on it. The
> camera code is a general look-at freecam (`cam()` / `startPan()` in `flycast.lua`),
> so if you want the classic "bouncing camera" showreel style (zoom in/out, varied
> heights, orbits) the primitives are already there — this repo just uses a flat
> right→left truck.

## How it works (the short version)

Flycast has a built-in Lua API that can read/write Dreamcast guest RAM and runs a
callback every vblank. `flycast.lua` is a harness that:

- polls a command file (`cmd.txt`) for Lua chunks and writes results to `out.log`;
- live-patches the game's SH4 render routines (running from guest RAM) to skip the
  character sprites and shadow pass, and destroys the HUD assets — leaving the stage
  and its animations intact;
- pins the (invisible) characters symmetric so the engine camera rests at the true
  round-start center, then slides them wall-to-wall so the engine pans natively.

Python (`pmlib.py` + `stage_batch.py`) drives Flycast, navigates into a match, captures
the window's own pixels via `PrintWindow` (occlusion-proof), and encodes the media.

Full technical write-up — memory addresses, the clean-stage recipe, pan bounds, the
capture reliability tricks, and the CDI/filesystem loading — is in
**[docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md)**.

## Requirements

- **Windows** (capture uses the Win32 `PrintWindow` API via `ctypes`).
- **Flycast** built with **Lua scripting** enabled.
- **Python 3.10+** and `pip install -r requirements.txt`
  (`numpy`, `Pillow`, `imageio`, `imageio-ffmpeg` — ffmpeg is bundled by the last one).
- A **MvC2 Dreamcast disc image** you own, and its stage `POL`/`TEX` files. Base disc
  images are built with `patch_cdi.py` (same-size in-place stage patching).

## Setup

1. `pip install -r requirements.txt`
2. Edit **`src/config.py`** — the four paths at the top (Flycast folder, your two base
   CDIs, and your editable stage-source folder). Everything else derives from those.
3. Edit the `PM_DIR` line at the top of **`src/flycast.lua`** to this repo's `src/`
   folder (must match `config.py`'s `PM_DIR`), then **copy `flycast.lua` into your
   Flycast folder** so the emulator loads it.
4. Build your base discs (see `patch_cdi.py` — patch your modified stages into a copy
   of your MvC2 disc; do the same with stock stages for the "default" set).

## Usage

All commands run from `src/`.

```bash
# Re-capture standard stages after you tweak a texture in your Modified\ folder
python regen_stage.py 09 0F        # specific slots (hex)
python regen_stage.py --changed    # every slot newer than the CDI
python regen_stage.py --all        # all 17

# Full rip of a whole set (env vars pick the disc + output)
PM_CDI=<Modified.cdi> PM_OUT=<...\output\modified>  python stage_batch.py
PM_CDI=<Defaults.cdi> PM_OUT=<...\output\defaults>  python stage_batch.py

# Someone ELSE'S stage -- guest mode. Never writes to your stage-source folder or
# your own discs; output is labelled and kept separate from your captures.
python build_guest_stage.py 05 <their_tex.bin> ..\MVC2_Guest.cdi
PM_CDI=..\MVC2_Guest.cdi PM_OUT=..\output\guests PM_LABEL=authorname python stage_batch.py 05
# (or just fill in the "Label" box in internal_tool.py and it does all of this)

# A non-standard / foreign static stage (loads into the Training slot; oversized
# textures are handled by a directory-record repoint — no ISO rebuild)
python build_custom_stage.py "<folder with STG0BPOL/TEX>"  ..\MVC2_Custom.cdi
PM_CDI=..\MVC2_Custom.cdi PM_OUT=..\output\custom  python stage_batch.py 0B

# Build the website gallery from captured media
python build_mockups.py

# Point-and-click front end (LOCAL ONLY): pick a stage, upload a texture, it does
# the whole build -> capture -> media, and shows the result
python internal_tool.py            # http://127.0.0.1:8765
#   (optional "Label" field = guest mode: someone else's stage, kept separate)
```

## Repo layout

```
src/
  config.py             # <-- EDIT: all machine-specific paths
  flycast.lua           # in-emulator harness (edit PM_DIR, copy to Flycast folder)
  pmlib.py              # Python driver: launch, capture, match navigation
  stage_batch.py        # the capture pipeline
  regen_stage.py        # patch a standard slot + capture + rebuild gallery
  build_custom_stage.py # capture disc for a foreign / oversized stage
  patch_cdi.py          # in-place same-size stage patcher for a CDI
  build_mockups.py      # website gallery builder
  stage_meta.json       # gallery data: order, names, done/wip, links
  internal_tool.py      # local web front end over the above
  mvc2_disc.py          # vendored CDI / ISO9660 helper
docs/HOW-IT-WORKS.md    # the deep technical write-up
output/                 # captures + gallery land here (gitignored)
```

## Credits & sources

Dreamcast memory-map / label groundwork from the MvC2 reverse-engineering community —
notably **t3chnicallyinclined**'s `mvc2-oracle` and the `marvelous2` SH4 disassembly.
Nothing here ships game assets; you supply your own disc.

No warranty — this pokes emulator memory and rewrites disc images. Work on copies.
