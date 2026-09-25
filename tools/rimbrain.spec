# PyInstaller spec — rimbrain.exe (UR-ARC-009)
# One binary: runtime loop + dashboard overlay + all read-only data.
# Writable dirs (state/, packs/, profiles/) resolve beside the exe, not inside it.

import os
from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [
    (os.path.join(ROOT, "components", "contracts", "schemas"),
     "components/contracts/schemas"),
    (os.path.join(ROOT, "components", "contracts", "registry"),
     "components/contracts/registry"),
    (os.path.join(ROOT, "baselines", "upstream-85cb050", "rpc-inventory.json"),
     "baselines/upstream-85cb050"),
    (os.path.join(ROOT, "components", "rimbrain", "packs"),
     "components/rimbrain/packs"),
    (os.path.join(ROOT, "profiles"), "profiles"),
]

hiddenimports = (
    collect_submodules("runtime")
    + collect_submodules("dashboard")
    + collect_submodules("contracts")
    + ["yaml", "jsonschema", "referencing", "referencing.jsonschema",
       "tkinter", "encodings.idna"]   # getaddrinfo needs the codec;
                                     # PyInstaller misses it (runtime ref)
)

a = Analysis(
    [os.path.join(ROOT, "rimbrain.py")],
    pathex=[
        os.path.join(ROOT, "components", "runtime", "src"),
        os.path.join(ROOT, "components", "contracts", "src"),
        os.path.join(ROOT, "components", "dashboard", "src"),
    ],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "tests"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,      # onedir: no _MEI extraction at launch —
    name="rimbrain",            # onefile's temp-dir unpack raced AV locks
    console=True,               # and died mid-import; onedir removes the
    upx=False,                  # whole failure class (and starts faster)
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="rimbrain",            # dist/rimbrain/rimbrain.exe + _internal/
)
