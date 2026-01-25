from vector_store import LocalVectorStore
from anonymizer import anonymize_transcript
from grok_client import generate_suggestion
import queue
import threading
import time


# Simulate overlay
def run_overlay(overlay_queue):
    while True:
        if not overlay_queue.empty():
            suggestion = overlay_queue.get()
            print(f"Overlay Update: {suggestion}")
        time.sleep(0.1)


if __name__ == "__main__":
    # Initialize
    vector_store = LocalVectorStore()
    vector_store.load_documents()

    overlay_queue = queue.Queue()
    overlay_thread = threading.Thread(
        target=run_overlay, args=(overlay_queue,), daemon=True
    )
    overlay_thread.start()

    # Simulate conversation transcript
    test_transcripts = [
        "How are your Ollama sample?",
        "We need to implement machine learning features.",
        "What are your thoughts on using Python for this?",
    ]

    for transcript in test_transcripts:
        print(f"Simulated Transcript: {transcript}")

        # Anonymize
        snippet = anonymize_transcript(transcript)
        print(f"Anonymized Snippet: {snippet}")

        # Get context
        context_docs = vector_store.search(snippet, k=2)
        context = " ".join([doc.page_content for doc in context_docs])
        print(f"Retrieved Context: {context}")

        # Generate suggestion
        suggestion = generate_suggestion(context, snippet)
        print(f"Generated Suggestion: {suggestion}")

        # Update overlay
        overlay_queue.put(suggestion)

        time.sleep(2)  # Simulate delay

    print("Test conversation completed.")
