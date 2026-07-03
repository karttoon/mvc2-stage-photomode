-- MvC2 Photo Mode harness for Flycast (Dreamcast NTSC-U / mixes based on it)
-- Polls PM_DIR/cmd.txt for Lua chunks (first line = seq number), executes them,
-- appends results to PM_DIR/out.log. Applies "freeze" writes every vblank.
--
-- Address sources: mvc2-oracle (t3chnicallyinclined) docs/MVC2-MEMORY-MAP.md,
-- web/labels.json, docs/re-catalog/spreadsheet-data.md (marvelous2-confirmed).

-- EDIT THIS to the absolute path of this toolkit's src/ folder (double
-- backslashes, trailing slash). MUST match config.py's PM_DIR (default: src/).
local PM_DIR = "C:\\Repo\\mvc2-stage-photomode\\src\\"
local CMD_FILE = PM_DIR .. "cmd.txt"
local OUT_FILE = PM_DIR .. "out.log"

-- ============================== float helpers ==============================
local hasPack = type(string.pack) == "function"

local function bitsToFloat(u)
  if hasPack then return (string.unpack("<f", string.pack("<I4", u))) end
  -- pure-Lua IEEE754 single decode
  local sign = (u >= 0x80000000) and -1 or 1
  local expo = math.floor(u / 0x800000) % 0x100
  local mant = u % 0x800000
  if expo == 0 then
    return sign * mant * 2^-149
  elseif expo == 0xFF then
    return mant == 0 and sign * math.huge or 0/0
  end
  return sign * (1 + mant / 0x800000) * 2^(expo - 127)
end

local function floatToBits(f)
  if hasPack then return (string.unpack("<I4", string.pack("<f", f))) end
  if f == 0 then return 0 end
  local sign = 0
  if f < 0 then sign = 0x80000000; f = -f end
  local mant, expo = math.frexp(f)
  expo = expo - 1
  if expo < -126 then
    mant = mant * 2^(expo + 126); expo = -127
  end
  mant = math.floor((mant * 2 - 1) * 0x800000 + 0.5)
  return sign + (expo + 127) * 0x800000 + mant
end

-- ============================== memory helpers ==============================
local mem = flycast.memory
local function rd8(a)  return mem.read8(a)  end
local function rd16(a) return mem.read16(a) end
local function rd32(a) return mem.read32(a) end
local function rdf(a)  return bitsToFloat(mem.read32(a)) end
local function wr8(a,v)  mem.write8(a,v)  end
local function wr16(a,v) mem.write16(a,v) end
local function wr32(a,v) mem.write32(a,v) end
local function wrf(a,v)  mem.write32(a, floatToBits(v)) end

-- ============================== address map ==============================
CAM = {
  lock   = 0x8C26A51F, -- u8: 0 reset / 1 default / 2 custom
  xrot   = 0x8C26A524, -- f32 default 0
  yrot   = 0x8C26A528, -- f32 default 95
  z      = 0x8C26A52C, -- f32 zoom, default 812.357
  zscale = 0x8C26A538, -- f32 default 812.357
  x      = 0x8C26A56C, -- f32 default 0
  y      = 0x8C26A570, -- f32 default 95
  fov    = 0x8C26A584, -- f32 default 43
  lmax   = 0x8C26A5B0, -- f32 default -1280
  rmax   = 0x8C26A5B4, -- f32 default 1280
}
CAM_LEGACY = { x = 0x8C1F9CD8, y = 0x8C1F9CDC } -- page-505 camera (wire-confirmed)

-- Full look-at camera struct (base 0x8C26A518). Each point has a CURRENT copy
-- and an interpolation TARGET copy; the engine lerps current->target each frame,
-- so freezing BOTH pins the camera. Mapped live 2026-07-02.
FREECAM = {
  eye_x = 0x8C26A524, eye_y = 0x8C26A528, eye_z = 0x8C26A52C, -- current
  eye_xt = 0x8C26A530, eye_yt = 0x8C26A534, eye_zt = 0x8C26A538, -- target
  look_x = 0x8C26A56C, look_y = 0x8C26A570, look_z = 0x8C26A574, -- current
  look_xt = 0x8C26A578, look_yt = 0x8C26A57C, look_zt = 0x8C26A580, -- target
  fov = 0x8C26A584,
}
-- default resting values (Desert): eye(-40,140,812) look(-315,95,0) fov 43

SLOTS = { -- char struct bases, stride 0x5A4
  P1C1 = 0x8C268340, P2C1 = 0x8C2688E4, P1C2 = 0x8C268E88,
  P2C2 = 0x8C26942C, P1C3 = 0x8C2699D0, P2C3 = 0x8C269F74,
}
CS = { -- char struct offsets
  active = 0x000, char_id = 0x001, anim_lock = 0x004, color = 0x025,
  pos_x = 0x034, pos_y = 0x038,
  scale_x = 0x050, scale_y = 0x054, scale_z = 0x058,
  screen_x = 0x0E0, screen_y = 0x0E4,
  hb_scale_x = 0x0EC, hb_scale_y = 0x0F0,
  sprite_id = 0x144, stance = 0x1F9, health = 0x420,
}

POOL = { base = 0x8C26AA54, stride = 0x1D0, count = 256,
         cull = 0x12C, sprite_id = 0x144, owner = 0x080, category = 0x003 }

G = {
  match_sub_state = 0x8C289621, in_match = 0x8C289624, round = 0x8C28962B,
  timer = 0x8C289630, stage_id = 0x8C289638,
  match_tracker = 0x8C2895F0, -- 0 loading 2 intro 3 walk 4 mid 5 KO 6 win 9 finish
  frame_counter = 0x8C3496B0,
  stg_id2 = 0x8C26A95C, stage_state = 0x8C1F978C,
  stage_anim_timer = 0x8C1F9D80,
}

-- DC controller bitmask (kcode active-low; pressButtons clears bits)
BTN = { C=1, B=2, A=4, START=8, UP=0x10, DOWN=0x20, LEFT=0x40, RIGHT=0x80,
        Z=0x100, Y=0x200, X=0x400, D=0x800 }

-- ============================== output ==============================
local function out(msg)
  local f = io.open(OUT_FILE, "a")
  if f then f:write(tostring(msg), "\n"); f:close() end
end

local function notify(msg)
  pcall(function() flycast.emulator.displayNotification(msg, 3000) end)
end

-- ============================== freeze engine ==============================
-- freezes[addr] = {t="f32"|"u8"|"u16"|"u32", v=value}; applied every vblank
freezes = {}
function freeze(addr, t, v) freezes[addr] = { t = t, v = v } end
function unfreeze(addr) freezes[addr] = nil end
function unfreezeAll() freezes = {} end

local function applyFreezes()
  for a, s in pairs(freezes) do
    if s.t == "f32" then wrf(a, s.v)
    elseif s.t == "u8" then wr8(a, s.v)
    elseif s.t == "u16" then wr16(a, s.v)
    else wr32(a, s.v) end
  end
end

-- ============================== input tap queue ==============================
-- tap("A", holdFrames) presses then releases automatically; tap2 = player 2
local tapQueue = {}
function tap(name, frames, player)
  table.insert(tapQueue, { mask = BTN[name] or name, left = frames or 5, pl = player or 1 })
end
function tap2(name, frames) tap(name, frames, 2) end

local function applyTaps()
  local q = tapQueue[1]
  if not q then return end
  if q.left > 0 then
    flycast.input.pressButtons(q.pl, q.mask)
    q.left = q.left - 1
  else
    flycast.input.releaseButtons(q.pl, q.mask)
    table.remove(tapQueue, 1)
  end
end

-- ============================== photo mode ops ==============================
savedScales = nil

function eachSlot(fn)
  for name, base in pairs(SLOTS) do fn(name, base) end
end

function hideChars()
  savedScales = savedScales or {}
  eachSlot(function(name, base)
    savedScales[name] = savedScales[name] or {
      x = rd32(base + CS.scale_x), y = rd32(base + CS.scale_y), z = rd32(base + CS.scale_z) }
    freeze(base + CS.scale_x, "f32", 0)
    freeze(base + CS.scale_y, "f32", 0)
    freeze(base + CS.scale_z, "f32", 0)
  end)
  out("hideChars: scales frozen to 0 on all 6 slots")
end

function showChars()
  eachSlot(function(name, base)
    unfreeze(base + CS.scale_x); unfreeze(base + CS.scale_y); unfreeze(base + CS.scale_z)
    if savedScales and savedScales[name] then
      wr32(base + CS.scale_x, savedScales[name].x)
      wr32(base + CS.scale_y, savedScales[name].y)
      wr32(base + CS.scale_z, savedScales[name].z)
    end
  end)
  out("showChars: scales restored")
end

cullFx_on = false
local function applyCullFx()
  for i = 0, POOL.count - 1 do
    local node = POOL.base + i * POOL.stride
    wr8(node + POOL.cull, 1) -- skip render if != 0
  end
end
function cullFx(on) cullFx_on = (on ~= false); out("cullFx=" .. tostring(cullFx_on)) end

function camLock()
  freeze(CAM.lock, "u8", 2)
  out("camLock: Camera_Lock frozen to 2 (custom)")
end

function camSet(x, y, z, fov)
  if x then freeze(CAM.x, "f32", x) end
  if y then freeze(CAM.y, "f32", y) end
  if z then freeze(CAM.z, "f32", z) end
  if fov then freeze(CAM.fov, "f32", fov) end
  out(string.format("camSet x=%s y=%s z=%s fov=%s",
    tostring(x), tostring(y), tostring(z), tostring(fov)))
end

function camReset()
  for _, a in pairs({CAM.x, CAM.y, CAM.z, CAM.fov, CAM.zscale, CAM.lock}) do unfreeze(a) end
  wr8(CAM.lock, 0) -- 0 = reset
  out("camReset")
end

function freezeTimer() freeze(G.timer, "u16", 99); out("timer frozen") end

function status()
  local s = {}
  s[#s+1] = string.format("frame=%d tracker=%d in_match=%d stage=%d/%d timer=%d",
    rd32(G.frame_counter), rd8(G.match_tracker), rd8(G.in_match),
    rd8(G.stage_id), rd8(G.stg_id2), rd16(G.timer))
  s[#s+1] = string.format("cam lock=%d x=%.2f y=%.2f z=%.3f zscale=%.3f fov=%.2f rot=%.2f/%.2f lmax=%.0f rmax=%.0f",
    rd8(CAM.lock), rdf(CAM.x), rdf(CAM.y), rdf(CAM.z), rdf(CAM.zscale),
    rdf(CAM.fov), rdf(CAM.xrot), rdf(CAM.yrot), rdf(CAM.lmax), rdf(CAM.rmax))
  s[#s+1] = string.format("cam505 x=%.2f y=%.2f", rdf(CAM_LEGACY.x), rdf(CAM_LEGACY.y))
  eachSlot(function(name, base)
    s[#s+1] = string.format("%s active=%d id=0x%02X pos=%.1f,%.1f scale=%.3f,%.3f hp=%d",
      name, rd8(base + CS.active), rd8(base + CS.char_id),
      rdf(base + CS.pos_x), rdf(base + CS.pos_y),
      rdf(base + CS.scale_x), rdf(base + CS.scale_y), rd16(base + CS.health))
  end)
  local msg = table.concat(s, "\n")
  out(msg)
  return msg
end

function freezeAnims()
  eachSlot(function(_, base) freeze(base + CS.anim_lock, "u8", 2) end)
  out("freezeAnims: Animation_Lock=2 on all slots")
end

function unfreezeAnims()
  eachSlot(function(_, base) unfreeze(base + CS.anim_lock); wr8(base + CS.anim_lock, 1) end)
end

function photoOn(z)
  camLock()
  camSet(0, 95, z or 2000, nil)
  hideChars()
  freezeAnims()
  cullFx(true)
  freezeTimer()
  notify("PHOTO MODE ON")
  out("photoOn (z=" .. tostring(z or 2000) .. ")")
end

function photoOff()
  unfreezeAll()
  cullFx_on = false
  showChars()
  unfreezeAnims()
  wr8(CAM.lock, 0)
  notify("PHOTO MODE OFF")
  out("photoOff")
end

-- one-shot navigation: attract/title -> char select -> match (Ruby x3 vs CPU)
function gotoMatch()
  tap("START", 8); tap(0, 150)
  tap("START", 8); tap(0, 150)
  tap("START", 8); tap(0, 180)
  for _ = 1, 6 do tap("A", 8); tap(0, 60) end
  out("gotoMatch: tap sequence queued (~20s)")
end

-- palette-based character hiding: zero alpha of all 6 char palette banks in
-- PVR palette RAM (chars are the only paletted textures; stage/HUD unaffected)
PAL_BANKS = {0xA05F9400, 0xA05F9600, 0xA05F9800, 0xA05F9A00, 0xA05F9C00, 0xA05F9E00}
savedPal = nil
function hideCharsPal()
  savedPal = savedPal or {}
  for _, base in ipairs(PAL_BANKS) do
    for i = 0, 15 do
      local a = base + i*4
      if savedPal[a] == nil then savedPal[a] = rd32(a) end
      freeze(a, "u32", 0)
    end
  end
  out("hideCharsPal: 96 palette entries frozen transparent")
end
function showCharsPal()
  for _, base in ipairs(PAL_BANKS) do
    for i = 0, 15 do
      local a = base + i*4
      unfreeze(a)
      if savedPal and savedPal[a] then wr32(a, savedPal[a]) end
    end
  end
  out("showCharsPal: restored")
end

-- VS mode: P2 joins at char select, both pick, both idle in match
function vsMatch()
  pcall(function() flycast.config.maple.setDeviceType(2, 0) end) -- ensure P2 pad
  tap("START", 8); tap(0, 150)
  tap("START", 8); tap(0, 150)
  tap("START", 8); tap(0, 120)      -- reach char select
  tap2("START", 8); tap(0, 90)      -- P2 joins
  for _ = 1, 8 do                    -- both sides pick (extra taps are harmless)
    tap("A", 8); tap(0, 30)
    tap2("A", 8); tap(0, 30)
  end
  out("vsMatch: tap sequence queued (~30s)")
end

-- HUD removal (the full kill, discovered 2026-07-02):
--  * DM00TEX.BIN (textured HUD art) is uploaded to VRAM: needle-scan + zero.
--  * DM00POL.BIN (HUD geometry incl. bar fills) resident in RAM @0x8CE80000: zero.
--  * FONT.BIN (WINS/text glyphs) in VRAM: needle-scan + zero.
-- VRAM addresses can shift per boot; needles are byte pairs from the disc files.
DM00POL_ADDR, DM00POL_LEN = 0x8CE80000, 0x164E8
DM00TEX_NEEDLE = { off = 0x54, a = 0x59CAF4DB, b = 0x4147EC9A, len = 0x1E000 }
FONT_NEEDLE    = { off = 0x2CC, a = 0xB9CEFBDE, b = 0xB9CE8000, len = 0x12040 }

local function vramFind(n)
  for a = 0xA4000000, 0xA47FFFF8, 4 do
    if rd32(a) == n.a and rd32(a + 4) == n.b then return a - n.off end
  end
  return nil
end

function hudKill()
  for a = DM00POL_ADDR, DM00POL_ADDR + DM00POL_LEN - 4, 4 do wr32(a, 0) end
  local msgs = { "DM00POL zeroed" }
  for _, n in ipairs({ DM00TEX_NEEDLE, FONT_NEEDLE }) do
    local base = vramFind(n)
    if base then
      for a = base, base + n.len - 4, 4 do wr32(a, 0) end
      msgs[#msgs+1] = string.format("VRAM %08X+%X zeroed", base, n.len)
    else
      msgs[#msgs+1] = "needle NOT found"
    end
  end
  out("hudKill: " .. table.concat(msgs, "; "))
end

-- ================= stage asset injection (CvS2 / oversized stages) =============
-- The stage POL loads VERBATIM to a fixed RAM base (self-referential pointers are
-- baked as 0x0CEAxxxx -> guest 0x8CEAxxxx), so a renamed stage POL can be written
-- straight over it. The stage TEX bank is uploaded to VRAM (address shifts per
-- boot), so we needle-scan for the DEFAULT tex's bytes to find the base, then
-- overwrite with the new bank. Used to load stages whose files don't match the
-- disc slot size (can't be patched in-place) -- e.g. the CvS2 Concrete Rooftop
-- edit that normally rides the Training slot on the Steam build.
STAGE_POL_ADDR = 0x8CEA0000

local function readFileBytes(path)
  local f = io.open(path, "rb"); if not f then return nil end
  local d = f:read("*a"); f:close(); return d
end

-- write a binary file to guest RAM as little-endian 32-bit words (one-time)
function loadBinToAddr(path, addr)
  local d = readFileBytes(path)
  if not d then out("loadBin: cannot open " .. path); return nil end
  local n, i = #d, 1
  while i + 3 <= n do
    local b0, b1, b2, b3 = d:byte(i, i + 3)
    wr32(addr + (i - 1), b0 + b1 * 256 + b2 * 65536 + b3 * 16777216)
    i = i + 4
  end
  while i <= n do wr8(addr + (i - 1), d:byte(i)); i = i + 1 end
  out(string.format("loadBin: %d bytes -> %08X", n, addr))
  return n
end

-- scan VRAM for an 8-byte needle taken from `needlePath` at byte offset `off`,
-- returning the VRAM address where the bank BEGINS (base = match - off).
function vramScanFile(needlePath, off)
  local d = readFileBytes(needlePath); if not d then return nil end
  local function u32(k)
    local a, b, c, e = d:byte(k, k + 3)
    return a + b * 256 + c * 65536 + e * 16777216
  end
  local a0, a1 = u32(off + 1), u32(off + 5)
  for a = 0xA4000000, 0xA47FFFF8, 4 do
    if rd32(a) == a0 and rd32(a + 4) == a1 then return a - off end
  end
  return nil
end

-- Freecam: place eye + look-at anywhere. Freezes both current & target copies.
-- ex, ey, ez = camera position; lx, ly, lz = point it looks at; fov degrees.
function cam(ex, ey, ez, lx, ly, lz, fov)
  freeze(FREECAM.eye_x, "f32", ex);  freeze(FREECAM.eye_xt, "f32", ex)
  freeze(FREECAM.eye_y, "f32", ey);  freeze(FREECAM.eye_yt, "f32", ey)
  freeze(FREECAM.eye_z, "f32", ez);  freeze(FREECAM.eye_zt, "f32", ez)
  freeze(FREECAM.look_x, "f32", lx); freeze(FREECAM.look_xt, "f32", lx)
  freeze(FREECAM.look_y, "f32", ly); freeze(FREECAM.look_yt, "f32", ly)
  freeze(FREECAM.look_z, "f32", lz); freeze(FREECAM.look_zt, "f32", lz)
  if fov then freeze(FREECAM.fov, "f32", fov) end
  out(string.format("cam eye(%.0f,%.0f,%.0f) look(%.0f,%.0f,%.0f) fov=%s",
    ex, ey, ez, lx, ly, lz, tostring(fov)))
end

-- Character hide, the CORRECT way (learned the hard way 2026-07-02):
--  * The visible "box" is the OFF-SCREEN CHARACTER INDICATOR (HUD arrow/icon the
--    game shows when a tracked character leaves the view) — NOT the sprite.
--  * palette/scale/active/sprite_id edits hide the SPRITE but never the indicator.
--  * Moving chars off-screen (any direction) TRIGGERS the indicator; up also makes
--    the camera fight to follow (vibration).
--  * So: keep ALL 6 chars ON-SCREEN and invisible. PIN them to the camera's X every
--    frame (they ride along at screen-center, never off-screen -> no indicator),
--    and palette-hide the sprites. pinX is applied in vblank.
pinX = nil          -- when set, all 6 char pos_x are forced here every frame
function setPin(x) pinX = x end
local function applyPin()
  if not pinX then return end
  for _, base in pairs(SLOTS) do
    wrf(base + CS.pos_x, pinX)
    wrf(base + CS.pos_y, 0)
  end
end

-- clean the scene without touching the camera (chars/shadow/fx/timer/HUD)
function sceneClean()
  hideCharsPal()                                 -- sprites invisible (palette->0)
  setPin(pinX or 0)                              -- pin chars on-screen (default center)
  cullFx(true)                                   -- projectiles/props (birds, etc.)
  freeze(G.timer, "u16", 99)
  freeze(G.stage_anim_timer, "u8", 0)
  flycast.config.video.ModifierVolumes = false   -- kill ground shadows
  hudKill()
  out("sceneClean: sprites hidden, chars pinned on-screen, fx/shadow/HUD removed")
end

-- Capture the game's OWN default camera (call when a fresh round is at neutral,
-- BEFORE any camera freeze). Stores DEFCAM = {ey, ez, ly, lz, fov, midx}.
DEFCAM = nil
function readDefaultCam()
  DEFCAM = {
    ex = rdf(FREECAM.eye_x), ey = rdf(FREECAM.eye_y), ez = rdf(FREECAM.eye_z),
    lx = rdf(FREECAM.look_x), ly = rdf(FREECAM.look_y), lz = rdf(FREECAM.look_z),
    fov = rdf(FREECAM.fov),
  }
  out(string.format("DEFCAM eye(%.1f,%.1f,%.1f) look(%.1f,%.1f,%.1f) fov=%.1f",
    DEFCAM.ex, DEFCAM.ey, DEFCAM.ez, DEFCAM.lx, DEFCAM.ly, DEFCAM.lz, DEFCAM.fov))
  return DEFCAM
end

-- ===== smooth 60fps pan engine (runs in vblank) =====
-- panState set by startPan()/startCharPan(); vblank calls panUpdate() every frame.
-- TWO modes:
--  * freecam mode (startPan): writes the camera struct directly. Subject to the
--    engine's follow dynamics -> lag + DEAD-ZONE PARKING near the char midpoint
--    (the "pan..pause..pan" bug). Kept for stills/experiments.
--  * CHAR mode (startCharPan): slides the pinned character pair; the engine's own
--    camera tracks them natively = gameplay-smooth motion, no dead zone. Camera
--    limits must be widened first for full range. THIS is the mode for recordings.
panState = nil
panDoneCount = 0    -- increments each time a pan finishes; poll to detect completion
-- startPan: sweep camera X from x0 to x1 over `seconds`, holding the given
-- height/distance/fov. Uses DEFCAM values for any arg left nil.
function startPan(x0, x1, seconds, ey, ez, ly, lz, fov)
  local d = DEFCAM or {}
  panState = {
    x0 = x0, x1 = x1,
    n = math.max(2, math.floor((seconds or 8) * 60)),
    i = 0,
    ey = ey or d.ey or 95, ez = ez or d.ez or 812,
    ly = ly or d.ly or 95, lz = lz or d.lz or 0,
    fov = fov or d.fov or 43,
  }
  out(string.format("startPan %.0f -> %.0f over %.1fs (%d frames) ey=%.0f ez=%.0f ly=%.0f fov=%.0f",
    x0, x1, seconds or 8, panState.n, panState.ey, panState.ez, panState.ly, panState.fov))
end

function stopPan() panState = nil; out("pan stopped") end

-- char-driven pan: slide the pinned pair from x0 to x1 over `seconds`;
-- the engine's camera follows natively (smooth, gameplay-like).
function startCharPan(x0, x1, seconds)
  panState = { mode = "chars", x0 = x0, x1 = x1,
               n = math.max(2, math.floor((seconds or 8) * 60)), i = 0 }
  out(string.format("startCharPan %.0f -> %.0f over %.1fs (%d frames)",
    x0, x1, seconds or 8, panState.n))
end

local function panUpdate()
  local p = panState
  if not p then return end
  local t = p.i / (p.n - 1)
  if t > 1 then t = 1 end
  local x = p.x0 + (p.x1 - p.x0) * t
  if p.mode == "chars" then
    for _, base in pairs(SLOTS) do
      wrf(base + CS.pos_x, x)
      wrf(base + CS.pos_y, 0)
    end
  else
    wrf(FREECAM.eye_x, x);  wrf(FREECAM.eye_xt, x)
    wrf(FREECAM.eye_y, p.ey); wrf(FREECAM.eye_yt, p.ey)
    wrf(FREECAM.eye_z, p.ez); wrf(FREECAM.eye_zt, p.ez)
    wrf(FREECAM.look_x, x); wrf(FREECAM.look_xt, x)
    wrf(FREECAM.look_y, p.ly); wrf(FREECAM.look_yt, p.ly)
    wrf(FREECAM.look_z, p.lz); wrf(FREECAM.look_zt, p.lz)
    wrf(FREECAM.fov, p.fov)
  end
  if p.i % 15 == 0 then
    out(string.format("PANLOG i=%d set=%.0f rendered=%.1f", p.i, x, rdf(0x8C1F9CD8)))
  end
  p.i = p.i + 1
  if p.i >= p.n then
    panState = nil; panDoneCount = panDoneCount + 1
    -- write a flag file so the Python capturer can detect completion WITHOUT the
    -- cmd/out.log roundtrip (which is unreliable while the emulator runs slow under
    -- capture load -- pollCommands lags behind the poll's settle window).
    local f = io.open(PM_DIR .. "panflag.txt", "w")
    if f then f:write(tostring(panDoneCount)); f:close() end
    out("pan done")
  end
end

-- park the camera at a static offset from center (for stills / pan start hold)
function camHold(x, ey, ez, ly, lz, fov)
  local d = DEFCAM or {}
  cam(x, ey or d.ey or 95, ez or d.ez or 812,
      x, ly or d.ly or 95, lz or d.lz or 0, fov or d.fov or 43)
end

-- the whole photo-mode recipe (run when a VS match is live and idle)
function photoFinish(fov, camx, camy)
  sceneClean()
  freeze(CAM.fov, "f32", fov or 88)
  freeze(CAM.xrot, "f32", camx or 0)
  freeze(CAM.yrot, "f32", camy or 150)
  notify("PHOTO MODE - CLEAN")
  out("photoFinish ready")
end

-- ===== live SH4 code patching (game code runs from RAM at 0x8C...) =====
-- Early-return a routine by writing `rts; nop` at its entry (SH4 LE: rts=0x000B
-- nop=0x0009). Saves originals for restore. NOTE: Flycast dynarec may cache blocks;
-- if a patch has no effect, SMC invalidation isn't firing on Lua writes.
codePatchSave = {}
function patchRet(addr)
  if not codePatchSave[addr] then codePatchSave[addr] = { rd16(addr), rd16(addr+2) } end
  wr16(addr, 0x000B)    -- rts
  wr16(addr+2, 0x0009)  -- nop
  out(string.format("patchRet %08X (was %04X %04X)", addr,
    codePatchSave[addr][1], codePatchSave[addr][2]))
end
function unpatch(addr)
  local o = codePatchSave[addr]
  if o then wr16(addr, o[1]); wr16(addr+2, o[2]); codePatchSave[addr] = nil
    out("unpatch " .. string.format("%08X", addr)) end
end
function unpatchAll()
  for a, o in pairs(codePatchSave) do wr16(a, o[1]); wr16(a+2, o[2]) end
  codePatchSave = {}
  out("unpatchAll")
end

-- ===== MvC2 render-pass surgery (found via disassembly + live NOP testing) =====
-- Frame render loc_8c030858 draws: character sprites (Render_sprites loc_8c0308c2),
-- then per-LAYER translucent passes, then the object pool. Each layer routine =
-- jsr <setup/stage-models> ; bsr loc_8c0301ce ; bra loc_8c030410(layerId), where
-- loc_8c030410 walks that layer's linked list of render objects and draws them.
--   layer 5 (loc_8c030d12) = HUD (bars/timer/names/meters/off-screen indicator)
--   layer 6 (loc_8c030d24) = character floor SHADOWS (+ pool effect objects)
-- The setup call BEFORE loc_8c030410 also renders the stage's OWN models, so NOPing
-- the whole routine drops stage geometry. Instead patch ONLY the tail branch to an
-- early return: overwrite {mov #layer,r4 ; bra loc_8c030410 ; lds.l @r15+,pr} at
-- routine+0xC with {lds.l @r15+,pr ; rts ; nop} = 4F26 000B 0009 (SH4 little-endian).
-- Game code lives in guest RAM (0x8C..); Flycast's dynarec honors these writes.
LAYER_HUD      = 0x8C030D12   -- layer 5 (HUD; also draws stage models -> use hudKill)
LAYER_SHADOW   = 0x8C030D24   -- layer 6 (character floor shadows)
RENDER_SPRITES = 0x8C0308C2   -- character sprite draw loop (Render_sprites)
layerPatchSave = {}
function skipLayerDraw(addr)
  local p = addr + 0x0C
  if not layerPatchSave[p] then layerPatchSave[p] = { rd16(p), rd16(p+2), rd16(p+4) } end
  wr16(p, 0x4F26); wr16(p+2, 0x000B); wr16(p+4, 0x0009)
  out(string.format("skipLayerDraw %08X (patched %08X)", addr, p))
end
function restoreLayerDraw(addr)
  local p = addr + 0x0C; local o = layerPatchSave[p]
  if o then wr16(p,o[1]); wr16(p+2,o[2]); wr16(p+4,o[3]); layerPatchSave[p]=nil end
end

-- THE clean-stage recipe: removes chars+shadows+HUD, keeps stage models & animation.
-- CRITICAL: keep the match timer frozen (>0) or the match ends and ALL animation stops.
-- IMPORTANT: layer 5 (HUD) AND layer 6 (shadow) each ALSO draw animated stage models
-- in their object lists. The shadow patch (layer 6) happens to keep the models, but
-- the LAYER-5 patch removes the Factory's moving machinery -> do NOT patch layer 5.
-- Use hudKill (DM00 asset zeroing) for the HUD instead; it leaves stage models intact.
function stripStage()
  -- CHARACTERS: NOP the sprite-draw pass so they're NEVER drawn. scale=0 is unreliable
  -- (races the live AI's per-frame animation -> flicker). NOPing the draw keeps the
  -- animation CLOCK running (only the draw is skipped) so the stage still animates.
  patchRet(RENDER_SPRITES)
  skipLayerDraw(LAYER_SHADOW)    -- character floor shadows (keeps stage models)
  hudKill()                      -- HUD + 2P/1P indicator (keeps stage models)
  -- Pin the two point chars symmetric so the render camera (=freecam + k*midpoint)
  -- isn't shifted by AI drift; midpoint 0 => freecam 0 = true round-start center.
  -- Safe now: chars are never drawn, so pinning can't make a sprite appear.
  freeze(SLOTS.P1C1+CS.pos_x, "f32", -213)
  freeze(SLOTS.P2C1+CS.pos_x, "f32",  213)
  freeze(G.timer, "u16", 99)          -- keep match alive -> animation keeps running
  freeze(G.match_tracker, "u8", 4)    -- hold mid-match state
  cullFx(true)
  out("stripStage: char DRAW off, shadows+HUD off; stage+anim kept; camera centered")
end
function unstripStage()
  unpatch(RENDER_SPRITES)
  restoreLayerDraw(LAYER_SHADOW)
  unfreeze(SLOTS.P1C1+CS.pos_x); unfreeze(SLOTS.P2C1+CS.pos_x)
  unfreeze(G.timer); unfreeze(G.match_tracker); cullFx(false)
  out("unstripStage (HUD stays killed until reload)")
end

-- WARNING: do NOT call flycast.emulator.saveState/loadState from commands --
-- they deadlock when invoked from the vblank callback.

-- expose raw helpers to command chunks
PM = { rd8=rd8, rd16=rd16, rd32=rd32, rdf=rdf, wr8=wr8, wr16=wr16, wr32=wr32, wrf=wrf,
       out=out, notify=notify }

-- ============================== command polling ==============================
local lastSeq = -1
local frame = 0

local function pollCommands()
  local f = io.open(CMD_FILE, "r")
  if not f then return end
  local seqLine = f:read("l")
  local body = f:read("a")
  f:close()
  local seq = tonumber(seqLine)
  if not seq or seq == lastSeq then return end
  lastSeq = seq
  out(("== cmd %d @frame %d =="):format(seq, frame))
  local chunk, err = load(body, "cmd")
  if not chunk then
    out("PARSE ERROR: " .. tostring(err))
    return
  end
  local ok, res = pcall(chunk)
  if not ok then
    out("RUNTIME ERROR: " .. tostring(res))
  elseif res ~= nil then
    out("=> " .. tostring(res))
  end
  out(("== cmd %d done =="):format(seq))
end

-- ============================== callbacks ==============================
flycast_callbacks = {
  start = function()
    out(("harness started, game=%s system=%d"):format(
      tostring(flycast.state.gameId), flycast.state.system))
    notify("MvC2 photo-mode harness loaded")
  end,

  vblank = function()
    frame = frame + 1
    local ok, err = pcall(function()
      applyFreezes()
      if cullFx_on then applyCullFx() end
      panUpdate()          -- smooth per-frame camera pan (overrides freezes on cam)
      applyPin()           -- pin chars under the camera (after pan sets pinX)
      applyTaps()
      if frame % 6 == 0 then pollCommands() end
    end)
    if not ok and frame % 300 == 0 then out("vblank error: " .. tostring(err)) end
  end,
}

out("=== flycast.lua photo-mode harness loaded (" ..
    (hasPack and "string.pack" or "pure-lua floats") .. ") ===")
