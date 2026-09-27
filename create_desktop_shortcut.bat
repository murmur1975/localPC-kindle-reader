@echo off
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" scripts\create_shortcut.py
) else (
    uv run python scripts\create_shortcut.py
)

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Process exited with code %ERRORLEVEL%
)

echo.
echo Press any key to exit...
pause > nul
