import sys
import os
import datetime
import time
import signal

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from audio_capture import AudioCapture

# from transcription import TranscriptionService
# from vector_store import LocalVectorStore
# from anonymizer import anonymize_transcript
# from grok_client import generate_suggestion

print("Starting AI Meeting Copilot...")


def update_suggestion(suggestion):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("suggestions.txt", "a") as f:
        f.write(f"{timestamp} | {suggestion}\n")


print("Loading modules...")
print("Modules loaded.")
print("Starting web UI...")


def signal_handler(sig, frame):
    print("Stopping...")
    capture.stop_capture()
    # transcriber.stop_transcription()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)

if __name__ == "__main__":
    print("Main started")
    print("Initializing components...")
    # Initialize components
    # vector_store = LocalVectorStore()
    print("Loading documents...")
    # vector_store.load_documents()
    print("Documents loaded.")
    print("Components initialized.")

    capture = AudioCapture()

    capture.start_capture()

    # start_web_ui()

    # transcriber = TranscriptionService()
    # print("Starting transcription...")
    # transcriber.start_transcription()
    # print("Transcription started.")

    print("AI Meeting Copilot started. Listening for audio... Press Ctrl+C to stop")
    print("Open http://127.0.0.1:5000 in your browser for the UI.")
    # Demo suggestions commented
    # Start clean, no demo

    last_transcript = ""
    counter = 0
    while True:
        audio_chunk = capture.get_audio_chunk()
        if audio_chunk:
            print("Audio chunk received.")
            # update_status("Audio detected")
            # transcriber.add_audio_chunk(audio_chunk)

        # transcript = transcriber.get_transcript()
        # if transcript and transcript != last_transcript:
        #     last_transcript = transcript
        #     print(f"Live Transcript: {transcript}")

        #     # Update UI with transcript
        #     # update_suggestion(f"Transcript: {transcript}")

        #     # Anonymize
        #     # snippet = anonymize_transcript(transcript)
        #     # print(f"Anonymized Snippet: {snippet}")
        #     snippet = transcript

        #     # Get context
        #     # context_docs = vector_store.search(snippet, k=2)
        #     # context = " ".join([doc.page_content for doc in context_docs])
        #     # print(f"Retrieved Context: {context}")
        #     context = "No context"

        #     # Generate suggestion
        #     # suggestion = generate_suggestion(context, snippet)
        #     # print(f"Generated Suggestion: {suggestion}")
        #     # update_status("Suggestion ready")
        #     suggestion = "No LLM suggestion"

        #     # Update web UI with suggestion
        #     # update_suggestion(f"Suggestion: {suggestion}")

        counter += 1
        if counter % 100 == 0:  # Every 10 seconds
            print("Still listening... Speak to test.")
        time.sleep(0.1)
