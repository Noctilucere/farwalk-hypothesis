# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for 《远行假设》 Demo

用法:
    python -m PyInstaller build.spec --clean --noconfirm
输出:
    dist/远行假设/远行假设.exe
"""
from PyInstaller.building.build_main import Analysis, PYZ, EXE
import os

ROOT = os.getcwd()

run_py = os.path.join(ROOT, "run.py")
icon = os.path.join(ROOT, "assets", "icon.ico")
fonts_dir = os.path.join(ROOT, "assets", "fonts")

# glfw 使用 ctypes 加载 dll, PyInstaller 不会自动收集, 需显式打包
glfw_dll = os.path.join(os.path.dirname(os.__file__), "site-packages", "glfw", "glfw3.dll")
if not os.path.isfile(glfw_dll):
    # 备选: 取 glfw 包安装路径
    import importlib.util
    spec = importlib.util.find_spec("glfw")
    if spec and spec.origin:
        glfw_dll = os.path.join(os.path.dirname(spec.origin), "glfw3.dll")

added_files = [(icon, "assets")]
# 若项目自带字体则一并打包; 默认空目录不打包
if os.path.isdir(fonts_dir) and os.listdir(fonts_dir):
    added_files.append((fonts_dir, os.path.join("assets", "fonts")))
# 外部 AI 生成的 3D 模型 (assets/models/*.glb)
models_dir = os.path.join(ROOT, "assets", "models")
if os.path.isdir(models_dir) and os.listdir(models_dir):
    added_files.append((models_dir, os.path.join("assets", "models")))
# 角色参考图 (assets/refs/*.png, 随 exe 一起打包)
refs_dir = os.path.join(ROOT, "assets", "refs")
if os.path.isdir(refs_dir) and os.listdir(refs_dir):
    added_files.append((refs_dir, os.path.join("assets", "refs")))
# 源码作为数据目录, 运行时 sys._MEIPASS/src 可被 import
added_files.append((os.path.join(ROOT, "src"), "src"))

a = Analysis(
    [run_py],
    pathex=[ROOT],
    binaries=[(glfw_dll, ".")] if os.path.isfile(glfw_dll) else [],
    datas=added_files,
    hiddenimports=[
        "numpy",
        "PIL",
        "PIL._imagingft",
        "glfw",
        "glfw.library",
        "moderngl",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "unittest",
        "pytest",
        "sphinx",
        "pydoc",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="远行假设",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)
