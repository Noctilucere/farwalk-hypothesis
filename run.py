"""
run.py -- 《远行假设》启动入口

用法:
    python run.py                      默认 1920x1080 高画质
    python run.py --medium             中画质 (植被密度降低)
    python run.py --low                低画质 (1024 阴影 / 稀疏植被)
    python run.py --fullscreen
    python run.py --size=1280x720
"""
from __future__ import annotations

import os
import sys

ROOT = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.game.main import main  # noqa: E402

if __name__ == "__main__":
    main()
