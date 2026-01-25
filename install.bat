@echo off
echo ============================================
echo    AI Meeting Copilot Pro - Installer
echo ============================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH!
    echo.
    echo Please install Python first:
    echo   1. Go to https://www.python.org/downloads/
    echo   2. Download Python 3.11 or later
    echo   3. IMPORTANT: Check "Add Python to PATH" during install!
    echo   4. Run this installer again
    echo.
    pause
    exit /b 1
)

echo [OK] Python found:
python --version
echo.

:: Install dependencies
echo [1/3] Installing Python dependencies...
echo       This may take a few minutes...
echo.
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install dependencies!
    echo         Try running as Administrator.
    pause
    exit /b 1
)
echo.
echo [OK] Dependencies installed!
echo.

:: Install spacy model
echo [2/3] Downloading language model...
python -m spacy download en_core_web_sm
if errorlevel 1 (
    echo [WARNING] Spacy model download failed. App may still work.
)
echo.
echo [OK] Language model ready!
echo.

:: Setup .env file
echo [3/3] Setting up configuration...
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [OK] Created .env file from template
        echo.
        echo IMPORTANT: Edit .env file and add your API keys!
        echo   - Open .env in Notepad
        echo   - Add your Groq API keys
        echo   - Save the file
    ) else (
        echo [WARNING] No .env.example found. Create .env manually.
    )
) else (
    echo [OK] .env file already exists
)
echo.

:: Create data folder
if not exist "data" (
    mkdir data
    echo [OK] Created data folder
)
echo.

echo ============================================
echo    Installation Complete!
echo ============================================
echo.
echo Next steps:
echo   1. Edit .env file with your API keys
echo   2. Install Voicemeeter (for system audio)
echo      https://vb-audio.com/Voicemeeter/
echo   3. Double-click run.bat to start the app
echo.
pause
