# AI Meeting Copilot Pro

Real-time AI assistant that listens to your meetings and suggests intelligent responses.

**Perfect for:**
- Job interviews (get AI-powered answer suggestions)
- Call center training
- Meeting assistance
- English practice

---

## New to This?

**If you've never installed Python before**, read the detailed guide: **[INSTALL_GUIDE.md](INSTALL_GUIDE.md)**

It has step-by-step instructions with pictures for everything.

---

## Features

- Real-time audio capture (system audio or microphone)
- Automatic speech transcription (offline, using Whisper)
- AI-powered response suggestions (using Groq API)
- Multiple personas (Interview mode, Call Center mode, etc.)
- Custom persona support (paste your own prompts)
- Session save/load
- Export to PDF/TXT
- Document upload for context (resume, notes)
- Multi-user support with isolated data

---

## Quick Start (5 minutes)

### Step 1: Install Python

1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Download **Python 3.11** or later
3. Run the installer
4. **IMPORTANT:** Check the box that says **"Add Python to PATH"**
5. Click "Install Now"

### Step 2: Download This App

**Option A: Download ZIP**
1. Click the green **"Code"** button above
2. Click **"Download ZIP"**
3. Extract the ZIP to a folder (e.g., Desktop)

**Option B: Git Clone**
```bash
git clone https://github.com/afif103/ai-meeting-copilot-pro.git
```

### Step 3: Install Dependencies

1. Open the extracted folder
2. Double-click **`install.bat`**
3. Wait for installation to complete (may take a few minutes)

### Step 4: Get API Keys (Free)

1. Go to [console.groq.com](https://console.groq.com)
2. Sign up for free
3. Go to "API Keys" and create a new key
4. Copy the key (starts with `gsk_...`)

### Step 5: Configure API Keys

1. In the app folder, find the file **`.env.example`**
2. Make a copy and rename it to **`.env`**
3. Open `.env` with Notepad
4. Replace `gsk_your_api_key_here` with your actual key
5. Save the file

### Step 6: Install Voicemeeter (for System Audio)

To capture audio from meetings/calls, you need Voicemeeter:

1. Go to [vb-audio.com/Voicemeeter](https://vb-audio.com/Voicemeeter/)
2. Download and install **Voicemeeter** (the free version is fine)
3. Restart your computer
4. Set Voicemeeter as your default audio device

**Skip this step** if you only need microphone input - use "Mic" mode in the app.

### Step 7: Run the App

Double-click **`run.bat`**

---

## How to Use

### Basic Usage

1. Start the app with `run.bat`
2. Select audio source:
   - **System** - Captures meeting audio (requires Voicemeeter)
   - **Mic** - Captures your microphone (for video interviews)
3. Select a persona (e.g., "Rami - AI Interview")
4. Start your meeting/interview
5. Watch the AI suggestions appear in real-time!

### For Job Interviews (Video Recording)

1. Switch to **"Mic"** mode
2. Select **"Rami - AI Interview"** persona
3. Read the interview question out loud
4. Wait for AI suggestion
5. Use the suggestion in your answer

### Personas

| Persona | Use For |
|---------|---------|
| Rami - AI Engineer | Technical discussions |
| Rami - AI Interview | Job interviews |
| Call Center Pro | Customer service (experienced) |
| Call Center Learner | Customer service (beginner) |
| Custom | Paste your own prompt |

---

## Voicemeeter Setup (Detailed)

For capturing system audio (Zoom, Teams, Meet calls):

1. Download Voicemeeter from [vb-audio.com/Voicemeeter](https://vb-audio.com/Voicemeeter/)
2. Install and restart PC
3. Set **"Voicemeeter Input"** as default playback in Windows Sound Settings
4. Open Voicemeeter:
   - Select your speakers in **Hardware Out (A1)**
   - Turn **B1 ON** for the input channel
   - Turn **A1 ON** to hear audio
5. In Windows Recording devices, select **"Voicemeeter Out B1"**
6. Keep Voicemeeter running while using the app

---

## Buttons

| Button | What it does |
|--------|--------------|
| Finalize | Manually trigger AI suggestion |
| Pause | Pause/resume recording |
| Upload | Add documents for context (resume, etc.) |
| User | Change username |
| Save | Save current session |
| Load | Load previous session |
| Export | Export to PDF or TXT |
| Stats | View performance metrics |

---

## Hotkeys

| Hotkey | Action |
|--------|--------|
| Ctrl+Shift+G | Show/focus window |
| Ctrl+Shift+P | Pause/resume |

---

## Troubleshooting

### "Python is not installed"
- Make sure you checked "Add Python to PATH" during installation
- Try restarting your computer

### "No audio detected"
- Check that Voicemeeter is installed and set as default
- Make sure the audio quality indicator shows "Good" (green)
- Try switching between System/Mic modes

### "API error" or "Rate limit"
- Check your `.env` file has valid API keys
- Groq free tier has rate limits - wait a minute and try again

### App crashes on startup
- Run `install.bat` again to reinstall dependencies
- Make sure `.env` file exists with valid keys

### Transcription is slow
- Edit `.env` and change `WHISPER_DEVICE=cpu` to `WHISPER_DEVICE=cuda` if you have an NVIDIA GPU

---

## Requirements

- Windows 10/11
- Python 3.10 or later
- Internet connection (for Groq API)
- Voicemeeter (for system audio capture)
- 4GB+ RAM recommended
- NVIDIA GPU optional (speeds up transcription)

---

## File Structure

```
ai-meeting-copilot-pro/
├── desktop_app.py      # Main application
├── backend/            # Core modules
│   ├── audio_capture.py
│   ├── transcription.py
│   ├── grok_client.py
│   ├── vector_store.py
│   └── anonymizer.py
├── data/               # User data (created at runtime)
│   ├── personas.json   # Persona configurations
│   └── sessions/       # Saved sessions
├── install.bat         # One-click installer
├── run.bat             # One-click launcher
├── requirements.txt    # Python dependencies
├── .env.example        # API key template
└── README.md           # This file
```

---

## Credits

Built with:
- [Faster-Whisper](https://github.com/guillaumekln/faster-whisper) - Speech recognition
- [Groq](https://groq.com) - Fast AI inference
- [ChromaDB](https://www.trychroma.com) - Vector database
- [LangChain](https://langchain.com) - LLM orchestration

---

## License

MIT License - Feel free to use and modify!
