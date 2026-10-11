@echo off
REM 打包成 Windows 单文件 exe（在 Windows 上运行）
REM 用法：双击本文件，或在 cmd 里执行 build.bat
setlocal
cd /d "%~dp0"

set NAME=RAWMatcher

python -m pip install --upgrade -r requirements.txt || goto :fail

set ICON=
if exist icon.ico set ICON=--icon icon.ico

python -m PyInstaller ^
  --noconfirm --clean --onefile --windowed ^
  --name %NAME% ^
  --collect-all tkinterdnd2 ^
  %ICON% ^
  --add-data "icon.png;." ^
  --add-data "icon.ico;." ^
  main.py || goto :fail

echo.
echo 打包完成：dist\%NAME%.exe
goto :eof

:fail
echo.
echo 打包失败，请检查上面的报错信息。
exit /b 1
