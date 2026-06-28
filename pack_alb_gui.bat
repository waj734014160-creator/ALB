@echo off
setlocal

rem Build a Windows executable for the ALB GUI using PyInstaller.
set "PYTHON_EXE=E:\Anaconda2023\envs\ALB\python.exe"
set "REPO_ROOT=%~dp0"
set "SPEC_FILE=%REPO_ROOT%tools\manual\alb_gui\pyinstaller\alb_gui.spec"
set "PAPER_CONFIG_DIR=%REPO_ROOT%paper_config"
set "DIST_CONFIG_DIR=%REPO_ROOT%dist\ALB_GUI\paper_config"

cd /d "%REPO_ROOT%"

if not exist "%PYTHON_EXE%" (
    echo Python executable not found:
    echo   %PYTHON_EXE%
    echo.
    pause
    exit /b 1
)

"%PYTHON_EXE%" -m PyInstaller --clean --noconfirm "%SPEC_FILE%"
if errorlevel 1 (
    echo.
    echo PyInstaller build failed.
    pause
    exit /b %errorlevel%
)

if not exist "%PAPER_CONFIG_DIR%" (
    echo.
    echo Bundled paper config directory not found:
    echo   %PAPER_CONFIG_DIR%
    pause
    exit /b 1
)

if exist "%DIST_CONFIG_DIR%" rmdir /s /q "%DIST_CONFIG_DIR%"
xcopy "%PAPER_CONFIG_DIR%" "%DIST_CONFIG_DIR%\" /E /I /Y >nul
if errorlevel 1 (
    echo.
    echo Failed to copy bundled paper config:
    echo   %PAPER_CONFIG_DIR%
    echo   %DIST_CONFIG_DIR%
    pause
    exit /b %errorlevel%
)

echo.
echo Build complete:
echo   %REPO_ROOT%dist\ALB_GUI\ALB_GUI.exe
echo   %DIST_CONFIG_DIR%
echo.
pause
endlocal
