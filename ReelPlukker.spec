# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

APP_NAME = "ReelPlukker"
APP_VERSION = "1.0.1"
APP_ID = "be.lnnt.reelplukker"

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
BIN_EXT = ".exe" if IS_WIN else ""

ICON_PATH = "assets/icon.ico" if IS_WIN else "assets/icon.icns"
if not Path(ICON_PATH).exists():
    ICON_PATH = None

# ffmpeg/ffprobe must be downloaded to ./bin/ before running pyinstaller.
BIN_DIR = Path("bin")
binaries = []
for name in ("ffmpeg", "ffprobe"):
    src = BIN_DIR / f"{name}{BIN_EXT}"
    if src.exists():
        binaries.append((str(src), "."))

hiddenimports = (
    collect_submodules("gallery_dl")
    + collect_submodules("yt_dlp")
)

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["test", "tests", "unittest"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=ICON_PATH,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)

if IS_MAC:
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=ICON_PATH,
        bundle_identifier=APP_ID,
        version=APP_VERSION,
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_NAME,
            "CFBundleShortVersionString": APP_VERSION,
            "CFBundleVersion": APP_VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
