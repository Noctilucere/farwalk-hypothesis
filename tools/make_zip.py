"""打包纯净源码 zip (远行假设 v1.2.0)."""
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "远行假设_完整纯净源码_v1.2.0.zip")
SKIP_DIRS = {"__pycache__", ".venv", "build", "dist",
             ".pytest_cache", "tools/shots"}
SKIP_SUFFIX = (".pyc", ".tmp")

include = []
for base, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS
               and not (d.startswith(".") and d != ".workbuddy")]
    rel = os.path.relpath(base, ROOT)
    for f in files:
        if f.endswith(SKIP_SUFFIX):
            continue
        p = os.path.join(base, f)
        relp = os.path.relpath(p, ROOT)
        if relp.startswith(os.path.join("tools", "shots") + os.sep) \
           or os.sep + "tools" + os.sep + "shots" + os.sep in p:
            continue
        include.append(relp)

include = sorted(set(include))
with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for f in include:
        if os.path.exists(f):
            zf.write(f, f)
print(f"packaged {OUT}")
print(f"  {len(include)} files, {os.path.getsize(OUT) / 1024:.1f} KB")