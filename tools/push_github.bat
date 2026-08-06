@echo off
REM ============================================================
REM Farwalk Hypothesis - one-click push to GitHub
REM Usage: double-click this file, or run: tools\push_github.bat
REM Target: https://github.com/Noctilucere/farwalk-hypothesis
REM NOTE: keep this file ASCII-only (no CJK) to avoid cmd encoding issues
REM ============================================================

echo [1/3] configure remote...
git remote remove origin 2>nul
git remote add origin git@github.com:Noctilucere/farwalk-hypothesis.git

echo [2/3] push main branch...
git push -u origin main

echo [3/3] done. https://github.com/Noctilucere/farwalk-hypothesis
pause