# Complete Installation Guide

This guide is for people who have **never installed Python before**. Follow every step carefully.

---

## STEP 1: Install Python

### 1.1 Download Python

1. Open your web browser
2. Go to: **https://www.python.org/downloads/**
3. Click the big yellow button that says **"Download Python 3.x.x"**
4. Wait for the file to download (it's about 25 MB)

### 1.2 Install Python

1. Find the downloaded file (usually in your Downloads folder)
   - It's called something like `python-3.12.0-amd64.exe`
2. **Double-click** to run the installer
3. **IMPORTANT - DO THIS FIRST:**
   - At the bottom of the installer window, you'll see a checkbox:
   - `[ ] Add Python to PATH`
   - **CHECK THIS BOX!** Click on it so it shows: `[✓] Add Python to PATH`
   - This is the most important step! Without this, the app won't work.
4. Click **"Install Now"**
5. Wait for installation to complete
6. Click **"Close"**

### 1.3 Verify Python is Installed

1. Press **Windows key + R** on your keyboard
2. Type `cmd` and press Enter
3. In the black window that opens, type: `python --version`
4. Press Enter
5. You should see something like: `Python 3.12.0`
   - If you see this, Python is installed correctly!
   - If you see "command not found", you forgot to check "Add to PATH". Uninstall Python and try again.

---

## STEP 2: Download the App

### Option A: Download as ZIP (Easier)

1. Go to: **https://github.com/afif103/ai-meeting-copilot-pro**
2. Click the green **"Code"** button
3. Click **"Download ZIP"**
4. Wait for download to complete
5. Find the ZIP file in your Downloads folder
6. **Right-click** the ZIP file → **"Extract All..."**
7. Choose where to extract (Desktop is fine)
8. Click **"Extract"**
9. You now have a folder called `ai-meeting-copilot-pro-main`

### Option B: Using Git (If you know Git)

```
git clone https://github.com/afif103/ai-meeting-copilot-pro.git
```

---

## STEP 3: Install App Dependencies

1. Open the extracted folder (`ai-meeting-copilot-pro-main`)
2. Find the file called **`install.bat`**
3. **Double-click** `install.bat`
4. A black window will open and start installing things
5. **Wait patiently** - this can take 5-10 minutes
6. You'll see lots of text scrolling - this is normal
7. When it's done, you'll see: **"Installation Complete!"**
8. Press any key to close the window

**If you see an error:**
- Make sure you checked "Add Python to PATH" in Step 1
- Try running `install.bat` as Administrator (right-click → Run as administrator)

---

## STEP 4: Install Ollama (The Local AI)

The app generates suggestions using AI that runs **on your own computer**. It's free, private, and works offline. No account or API key needed.

### 4.1 Install Ollama

1. Go to: **https://ollama.com/download**
2. Click **"Download for Windows"**
3. Run the downloaded installer (`OllamaSetup.exe`)
4. Follow the installer steps (just click Next/Install)
5. Ollama now runs in the background automatically

### 4.2 Download the AI Models

1. Press **Windows key + R**, type `cmd`, press Enter
2. In the black window, type this and press Enter:
   ```
   ollama pull qwen2.5-coder:7b
   ```
3. Wait for the download to finish (about 4.7 GB - be patient)
4. Then type this and press Enter:
   ```
   ollama pull llama3.2:3b
   ```
5. Wait again (about 2 GB)

### 4.3 Verify the Models

1. In the same black window, type: `ollama list`
2. Press Enter
3. You should see both `qwen2.5-coder:7b` and `llama3.2:3b` in the list
   - If you see them, the AI is ready!

---

## STEP 5: Configure the App

### 5.1 Create the Configuration File

1. Open the app folder (`ai-meeting-copilot-pro-main`)
2. Find the file called **`.env.example`**
   - If you don't see it, enable "Show hidden files" in Windows Explorer
   - View → Show → Hidden items
3. **Right-click** `.env.example` → **Copy**
4. **Right-click** in empty space → **Paste**
5. You now have a file called `.env.example - Copy`
6. **Rename** this file to just `.env` (remove everything except `.env`)
   - Windows might warn you about changing the extension - click Yes

### 5.2 You're Done (No Keys Needed!)

The default configuration already uses your local Ollama AI. You don't need to edit anything.

### 5.3 (Optional) Use Groq Cloud Instead

Only do this if you prefer cloud AI over local AI:

1. Create a free account at **https://console.groq.com** and create an API key
   (it looks like `gsk_abc123xyz...` - copy it immediately, you only see it once)
2. **Right-click** the `.env` file → **Open with** → **Notepad**
3. Paste your key after the `=` on these three lines:
   ```
   GROQ_API_KEY_REFINE=gsk_abc123xyz...
   GROQ_API_KEY_QUICK=gsk_abc123xyz...
   GROQ_API_KEY_SUGGEST=gsk_abc123xyz...
   ```
4. Change the provider line to:
   ```
   LLM_PROVIDER=groq
   ```
5. **Save the file** (Ctrl+S or File → Save)
6. Close Notepad

---

## STEP 6: Install Voicemeeter (For System Audio)

**Skip this step** if you only want to use your microphone (not capture meeting audio).

### 6.1 Download Voicemeeter

1. Go to: **https://vb-audio.com/Voicemeeter/**
2. Scroll down and click **"Download"** next to "Voicemeeter" (the standard version)
3. Wait for download (it's a ZIP file)

### 6.2 Install Voicemeeter

1. Find the downloaded ZIP file
2. **Right-click** → **Extract All** → **Extract**
3. Open the extracted folder
4. Find **`VoicemeeterSetup.exe`** and **double-click** it
5. Click **Yes** to allow installation
6. Click **Install**
7. When done, click **Restart** to restart your computer

### 6.3 Configure Windows Sound Settings

After your computer restarts:

1. **Right-click** the speaker icon in your taskbar (bottom right)
2. Click **"Sound settings"** or **"Open Sound settings"**
3. Under **"Output"** (or "Choose your output device"):
   - Select **"VoiceMeeter Input"** as your output/playback device
4. Under **"Input"** (or "Choose your input device"):
   - Select **"VoiceMeeter Output (VB-Audio VoiceMeeter VAIO)"**

### 6.4 Configure Voicemeeter

1. Open **Voicemeeter** (search for it in Start menu)
2. In the top right, click **"A1"** under "HARDWARE OUT"
3. Select your actual speakers/headphones from the list
4. In the first column, make sure **"A1"** button is lit (so you can hear audio)
5. In the first column, also turn on **"B1"** button (so the app can capture audio)
6. **Keep Voicemeeter open** while using the Meeting Copilot app

### 6.5 Test Audio

1. Play some audio on your computer (YouTube, music, etc.)
2. You should see the level meters moving in Voicemeeter
3. You should hear the audio through your speakers/headphones
4. If you can't hear anything, check that A1 is selected and lit

---

## STEP 7: Run the App

1. Open the app folder (`ai-meeting-copilot-pro-main`)
2. **Double-click** `run.bat`
3. A window will open - this is the AI Meeting Copilot!
4. If using Voicemeeter, make sure it's running in the background

### First Time Setup

1. The app will ask for a username - type your name and press Enter
2. The app window will open
3. Check the top of the window:
   - **Audio: Good** (green) = audio is being captured
   - **Audio: --** = no audio detected (check Voicemeeter)

---

## Troubleshooting

### "Python is not recognized"
- You forgot to check "Add Python to PATH" during installation
- Uninstall Python, reinstall, and make sure to check the PATH box

### "install.bat shows errors"
- Try running as Administrator (right-click → Run as administrator)
- Make sure you have internet connection
- Try running install.bat again

### "No audio detected"
- Make sure Voicemeeter is running
- Check Windows sound settings (Step 6.3)
- Make sure B1 is enabled in Voicemeeter (Step 6.4)

### "No AI suggestions appear"
- Make sure Ollama is installed (Step 4) - type `ollama list` in Command Prompt to check
- Make sure both models are downloaded (Step 4.2)
- Restart your computer - Ollama starts automatically with Windows

### "API error" (only if using optional Groq cloud mode)
- Check that your .env file has the correct API key
- Make sure the key starts with `gsk_`
- Try creating a new API key on Groq

### "App won't start"
- Run install.bat again
- Make sure the .env file exists (install.bat creates it from .env.example)
- Check for error messages in the black window

---

## Quick Reference

After setup, to use the app daily:

1. Start **Voicemeeter** (if using system audio)
2. Double-click **`run.bat`**
3. That's it!

---

## Need Help?

If you're stuck, check:
1. The error message in the black window
2. The README.md file for more details
3. Create an issue on GitHub: https://github.com/afif103/ai-meeting-copilot-pro/issues
