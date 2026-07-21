"""Central configuration for the MvC2 stage photo-mode toolkit.

Edit the four values under "EDIT THESE" for your machine; everything else derives
from them. These are the ONLY paths you should need to change.
"""
import os

SRC = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(SRC)

# ============================== EDIT THESE ==============================
# Folder containing flycast.exe. Must be a Flycast build with Lua scripting
# (see README). You will copy src/flycast.lua into this folder.
FLYCAST_DIR = r"C:\path\to\flycast"

# Base disc images built from your MvC2 disc (see README -> patch_cdi.py).
# MODIFIED = your retextured stages, DEFAULTS = stock art.
MODIFIED_CDI = r"C:\path\to\MVC2_Modified_Base.cdi"
DEFAULTS_CDI = r"C:\path\to\MVC2_Defaults_Base.cdi"

# Your editable stage sources: a folder holding STG00..STG10 {POL,TEX}.BIN.
MODDIR = r"C:\path\to\MvC2_Lvls\Modified"
# =======================================================================

FLYCAST_EXE  = os.path.join(FLYCAST_DIR, "flycast.exe")
OUTPUT       = os.path.join(REPO, "output")
OUT_MODIFIED = os.path.join(OUTPUT, "modified")
OUT_DEFAULTS = os.path.join(OUTPUT, "defaults")
SITE         = os.path.join(OUTPUT, "site_mockups")
# Scratch disc rebuilt for each custom/foreign-stage capture.
CUSTOM_CDI   = os.path.join(REPO, "MVC2_Custom_Scratch.cdi")
# Scratch disc for OTHER PEOPLE's stages (guest mode) -- your own files stay untouched.
GUEST_CDI    = os.path.join(REPO, "MVC2_Guest_Scratch.cdi")

# The harness polls PM_DIR for cmd.txt and writes out.log / panflag.txt there.
# IMPORTANT: this MUST match the PM_DIR set at the top of flycast.lua.
PM_DIR = SRC
