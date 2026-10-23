@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
title 麦麦积分止损官 - 一键上传 GitHub

echo.
echo  ============================================================
echo     麦麦积分止损官 · 一键上传 GitHub
echo  ============================================================
echo.
echo   正在检测电脑上的 Python，请稍候...
echo.

set "PY="
where py >nul 2>&1
if %errorlevel%==0 set "PY=py"

if not defined PY (
  where python >nul 2>&1
  if %errorlevel%==0 set "PY=python"
)

if not defined PY (
  where python3 >nul 2>&1
  if %errorlevel%==0 set "PY=python3"
)

if not defined PY (
  echo.
  echo  ============================================================
  echo     没找到 Python
  echo  ============================================================
  echo.
  echo   这台电脑还没装 Python，需要先装一下（免费，两分钟）。
  echo.
  echo   下面会自动打开下载页面，请：
  echo     1. 点页面中间的大按钮下载
  echo     2. 运行安装包，务必勾选 "Add Python to PATH"
  echo     3. 装完后，重新双击本文件
  echo.
  echo  ============================================================
  echo.
  start https://www.python.org/downloads/
  pause
  exit /b 1
)

echo   Python 已找到，开始运行...
echo.
echo  ============================================================
echo.

%PY% github_setup.py

echo.
echo  ============================================================
echo     运行结束
echo  ============================================================
echo.
pause
