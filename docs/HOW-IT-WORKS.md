# How it works — MvC2 stage photo-mode

Technical notes and reverse-engineering findings behind this toolkit. Addresses are
for the **Dreamcast NTSC-U** build of MvC2 (and mixes based on it), running in Flycast.
Guest RAM is at `0x8C000000+`; the SH4 CPU executes game code straight out of it, and
Flycast's JIT honours Lua writes to that code (self-modifying-code detection), which is
what makes live code-patching possible.

---

## 1. Architecture

Flycast exposes a Lua API (`flycast.memory` read/write, a `vblank` callback,
`flycast.input`, `flycast.config`). `flycast.lua` is a resident harness that, every
vblank:

1. re-applies any "frozen" memory writes (our overrides the game keeps clobbering),
2. runs the active camera/pan update,
3. every 6 frames, polls a **command file** for new Lua to execute.

**Command protocol (how Python talks to the running game):**

- Python writes `PM_DIR/cmd.txt` = a sequence number on line 1, a Lua chunk after it.
- The harness notices a new sequence number, runs the chunk, appends
  `=> <result>` to `PM_DIR/out.log`.
- `pmlib.cmd()` / `cmd_result()` implement this round-trip.

Do **not** call `flycast.emulator.saveState`/`loadState` from the vblank callback — it
deadlocks and wedges the emulator (kill + relaunch to recover).

---

## 2. Memory map (the addresses that matter)

**Camera** — a look-at camera at base `0x8C26A518`, with *smoothing*: each point has a
CURRENT copy and an interpolation TARGET copy; the engine lerps current→target every
frame, so a single write snaps back. Freeze **both** to pin it (`cam()` does this).

| field | current | target |
|---|---|---|
| eye x / y / z | `0x8C26A524 / 528 / 52C` | `0x8C26A530 / 534 / 538` |
| look x / y / z | `0x8C26A56C / 570 / 574` | `0x8C26A578 / 57C / 580` |
| FOV (deg, default 43) | `0x8C26A584` | — |
| view X limits (default ±1280) | `0x8C26A5B0` (L) / `0x8C26A5B4` (R) | — |

- Rendered/interpolated camera X (read-only, tracks the view): `0x8C1F9CD8`.
- FOV ~88 ≈ whole stage, ~120 ≈ fisheye diorama.

**Match / stage state**

| what | address | note |
|---|---|---|
| live stage id (STG_ID) | `0x8C26A95C` | force it from boot to pick a stage; `0x8C289638` copy is often stale |
| match timer | `0x8C289630` (u16) | **freeze > 0** (e.g. 99) or the round ends and all animation stops |
| match tracker | freeze to `4` | holds mid-match state |

**Characters** — six point-character slots; each has a world `pos_x` at a fixed struct
offset. The engine hard-clamps characters on-screen (fighting-game rule) — you cannot
move them off-frame, only pin them.

**HUD / effects assets** (destroyed rather than un-drawn — see §3):

- `DM00POL.BIN` (HUD geometry incl. bar fills) resident in RAM at `0x8CE80000`, len
  `0x164E8`. Reloaded per match, so re-zero each match.
- `DM00TEX.BIN` (HUD art) and `FONT.BIN` (WINS/text) are uploaded to VRAM
  (`0xA4000000..0xA47FFFFF`); their addresses shift per boot, so needle-scan for a
  known byte pair from the disc file and zero the region.

---

## 3. The clean-stage recipe (live SH4 code patching)

The frame render (`loc_8c030858`) runs per-*layer* translucent passes shaped
`jsr <setup + stage models>; bsr loc_8c0301ce; bra loc_8c030410(layerId)`, where
`loc_8c030410` draws that layer's object linked-list. Key discovery: **layers draw the
HUD/shadows AND the stage's own animated models in the same pass**, so NOPing a whole
layer also kills stage animation. The working recipe (`stripStage()`):

- **Characters:** NOP the sprite-draw routine `Render_sprites` at `0x8C0308C2`
  (`patchRet` = write `rts; nop` = bytes `4F26 000B 0009`... actually the entry
  becomes `lds.l @r15+,pr; rts; nop`). Do **not** use scale/palette tricks — they race
  the AI's per-frame animation writes and the character flickers back in.
- **Shadows:** the character floor shadows are **layer 6** (`loc_8c030d24`). Skip only
  that layer's *draw* tail (`skipLayerDraw`) — keeps the stage models in that layer.
- **HUD + the off-screen "2P▶1P" indicator:** do **not** patch layer 5 (it also draws
  animated stage models, e.g. Factory machinery). Instead **destroy the HUD assets**
  (`hudKill()` — zero DM00POL RAM + needle-scan/zero DM00TEX & FONT in VRAM).
- Keep the **timer frozen > 0** and pin the point characters symmetric (see §4).

Result: no characters / shadows / HUD / indicator; stage geometry present and animating.

The shadow, historically, was a red herring in a dozen other theories (palette,
modifier volumes, sprite id, KO state) — it is untextured layer-6 geometry.

---

## 4. Camera coupling & the pan

The engine camera follows the character **midpoint**. With the (invisible) point
characters pinned symmetric (`P1C1.pos_x = -213`, `P2C1.pos_x = +213`), the midpoint is
0 and the camera rests at the **true round-start center** — this is the still framing.

To pan, we **slide the pinned pair** and let the engine camera track them natively
(`startCharPan`). This is gameplay-smooth — no freecam dead-zone stall.

**Bounds (calibrated):** driving the pair to `char ±1114` lands the camera exactly on
the game's own `±960` view wall — the real player-view edge. The settled coupling is
`render_magnitude = |char| − 154`, i.e. `char ±1114 → cam ±960`. **Do not widen the
`0x8C26A5B0/5B4` limits** to reach further — that removes the clamp and pans into the
blue render-void past the stage art. The pan sweeps `cam +960 → −960` (right→left).

> For other capture styles (orbits, zoom pulses, height changes) use the freecam
> directly: `cam(ex,ey,ez, lx,ly,lz, fov)` and `startPan(x0,x1,seconds,...)` in
> `flycast.lua` write the full look-at struct each frame.

---

## 5. Capturing reliably (harder than it sounds)

- **Occlusion-proof capture.** Grab the Flycast window's *own* pixels with
  `PrintWindow(PW_RENDERFULLCONTENT)` straight into memory (`pmlib.Grabber`, ~35–40 fps).
  A screen-region grab (ffmpeg gdigrab) silently captures whatever window overlaps the
  region — when another window comes to the foreground mid-pan you get a frozen frame.
  (PrintWindow *does* return live DX11 frames here, contrary to common belief.)
- **Knowing when the pan is done.** The pan is frame-counted in the vblank, but the
  emulator's fps drops under capture load, so a fixed wall-clock window misses the
  motion. The harness writes a **flag file** (`panflag.txt`) when the pan completes;
  Python deletes it before the pan and polls for it. Don't use the cmd/out.log
  round-trip for this (it lags at low fps), and don't use inter-frame pixel delta
  (animated stages keep it high after the camera stops).
- **No static head.** The camera sits at the wall ~2.5 s before it visibly moves
  (settling lag). Poll the camera X (`0x8C1F9CD8`) and start grabbing only once it
  leaves the wall — so the video moves from frame 0. (Give `startCharPan` a moment to
  be consumed first, or the poll clobbers `cmd.txt` and the pan never starts.)
- **Navigation.** Force the stage id from boot and drive inputs until memory shows a
  real human match (`is_cpu == 0`) — this avoids capturing an attract-mode demo.

---

## 6. Discs: patching, loading, and non-standard stages

- **In-place patching** (`patch_cdi.py`): overwrite a stage's `POL`/`TEX` in the CDI at
  the same byte length. Maps each ISO sector to its raw CDI offset (mode-2/2336
  sectors, 8-byte subheader); EDC/ECC isn't recomputed — Flycast ignores it. Standard
  stage edits keep their slot size (ModNao re-exports preserve it), so this is enough
  for the 17 built-ins.
- **The stage POL loads verbatim** to a fixed RAM base (`~0x8CEA0000`, self-referential
  pointers baked as `0x0CEAxxxx`); the stage TEX is uploaded to VRAM.
- **MvC2 resolves stage files through the ISO9660 filesystem** (proven). That unlocks
  non-standard stages:
  - Only the **non-animated Training slot (STG0B)** is safe for a foreign *static*
    stage — animated slots parse animation data the foreign POL lacks and **crash on
    load** (tested: STG10/River-Raft crashes CvS2 even though the size fits).
  - A foreign **TEX can exceed** the Training TEX slot (1,064,960). Since a capture disc
    only ever loads STG0B, `build_custom_stage.py` writes the full texture into a big
    **sacrificial donor slot** (STG00TEX, 1,671,168) and **repoints STG0BTEX's directory
    record** (extent LBA + size) at it — no ISO rebuild, no truncation. (Directory
    record: extent LE@+2 / BE@+6, size LE@+10 / BE@+14; disc byte =
    `base + (isoByte//2048)*ss + hlen + isoByte%2048`.)

---

## 7. Dead ends kept for the record

- Hiding characters via palette-zero / scale=0 / active=0 / sprite_id=0 / KO —
  each leaves the shadow and/or flickers. `ModifierVolumes=false` does **not** remove
  the shadow (it isn't a modifier volume).
- The blue border around a pulled-back view is the **render void** past the finite
  stage mesh — never use it as a stage edge; the player view ends well inside it.
- Widening the camera limits to reach "more stage" pans past the art into the void.
- gdigrab screen-region capture (occlusion) and inter-frame-delta pan-end detection
  (fooled by stage animation / scrolling water) — both replaced (see §5).
