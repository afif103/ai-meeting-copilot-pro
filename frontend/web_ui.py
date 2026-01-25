from flask import Flask
import datetime
import os

app = Flask(__name__)
suggestions_file = "suggestions.txt"


@app.route("/")
def index():
    suggestions = []
    if os.path.exists(suggestions_file):
        with open(suggestions_file, "r") as f:
            for line in f:
                if line.strip():
                    timestamp, text = line.split(" | ", 1)
                    suggestions.append({"timestamp": timestamp, "text": text})
    sorted_suggestions = sorted(suggestions, key=lambda x: x["timestamp"], reverse=True)
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>AI Meeting Copilot</title>
        <meta http-equiv="refresh" content="2">
    </head>
    <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h1>AI Meeting Copilot</h1>
        <p>Listening for audio... Suggestions will appear below.</p>
        <div style="border: 1px solid #ccc; padding: 10px; min-height: 100px;">
    """
    if sorted_suggestions:
        for sug in sorted_suggestions:
            html += f"<p><strong>{sug['timestamp']}:</strong> {sug['text']}</p>"
    else:
        html += "<p>No suggestions yet...</p>"
    html += """
        </div>
    </body>
    </html>
    """
    return html


def update_suggestion(suggestion):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(suggestions_file, "a") as f:
        f.write(f"{timestamp} | {suggestion}\n")


def update_status(new_status):
    # For now, ignore status, or add to file
    pass


def run_web_ui():
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)


def start_web_ui():
    import threading

    print("Starting web UI thread")
    threading.Thread(target=run_web_ui, daemon=True).start()
    print("Web UI thread started")


if __name__ == "__main__":
    run_web_ui()
