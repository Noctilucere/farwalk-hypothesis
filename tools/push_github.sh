#!/bin/sh
# 《远行假设》 一键推送到 GitHub (macOS / Linux / Git Bash)
# 目标: https://github.com/Noctilucere/farwalk-hypothesis
set -e
echo "[1/3] 检查远程仓库..."
git remote remove origin 2>/dev/null || true
git remote add origin git@github.com:Noctilucere/farwalk-hypothesis.git
echo "[2/3] 推送 main 分支..."
git push -u origin main
echo "[3/3] 完成 → https://github.com/Noctilucere/farwalk-hypothesis"