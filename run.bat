@echo off
echo Starting AI Meeting Copilot Pro...
echo.

:: Check if .env exists
if not exist ".env" (
    echo [ERROR] .env file not found!
    echo         Run install.bat first, then edit .env with your API keys.
    echo.
    pause
    exit /b 1
)

:: Run the app
python desktop_app.py

:: If app crashes, keep window open
if errorlevel 1 (
    echo.
    echo [ERROR] App crashed! Check the error message above.
    pause
)
