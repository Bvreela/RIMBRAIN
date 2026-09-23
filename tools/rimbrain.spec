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
       "tkinter"]
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
    a.binaries,
    a.datas,
    [],
    name="rimbrain",
    console=True,
    upx=False,
)
