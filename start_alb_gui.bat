@echo off
setlocal

rem Launch the ALB GUI from the repository root with the pinned ALB Python.
set "PYTHON_EXE=E:\Anaconda2023\envs\ALB\python.exe"
set "REPO_ROOT=%~dp0"

cd /d "%REPO_ROOT%"

if not exist "%PYTHON_EXE%" (
    echo Python executable not found:
    echo   %PYTHON_EXE%
    echo.
    pause
    exit /b 1
)

"%PYTHON_EXE%" -m tools.manual.alb_gui
if errorlevel 1 (
    echo.
    echo ALB GUI exited with an error.
    pause
    exit /b %errorlevel%
)

endlocal
