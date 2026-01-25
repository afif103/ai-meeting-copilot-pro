import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import datetime


class OverlayUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()  # Hide until ready
        self.root.attributes("-topmost", True)  # Always on top
        self.root.attributes("-alpha", 0.85)  # Semi-transparent
        # self.root.overrideredirect(True)  # Commented out for resizable window
        self.root.configure(bg="lightblue")

        self.history_window = None
        self.suggestion_history = []

        # Feedback buttons - centered
        self.button_frame = tk.Frame(self.root, bg="lightblue")
        self.button_frame.pack(fill=tk.X, padx=10, pady=5)

        self.label = tk.Label(
            self.root,
            text="Waiting for suggestions...",
            font=("Arial", 12),
            bg="lightblue",
            fg="black",
            wraplength=620,
            justify="left",
        )
        self.label.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)

        # Buttons in center_frame
        self.center_frame = tk.Frame(self.button_frame, bg="lightblue")
        self.center_frame.pack()

        self.thumbs_up = tk.Button(
            self.center_frame, text="👍", command=self.thumbs_up_feedback
        )
        self.thumbs_up.pack(side=tk.TOP, pady=2)
        self.thumbs_down = tk.Button(
            self.center_frame, text="👎", command=self.thumbs_down_feedback
        )
        self.thumbs_down.pack(side=tk.TOP, pady=2)
        self.finalize_button = tk.Button(
            self.center_frame, text="Finalize", command=self.finalize_suggestion
        )
        self.finalize_button.pack(side=tk.TOP, pady=2)
        self.pause_resume_button = tk.Button(
            self.center_frame, text="Pause Recording", command=self.toggle_recording
        )
        self.pause_resume_button.pack(side=tk.TOP, pady=2)
        self.history_button = tk.Button(
            self.center_frame, text="History", command=self.show_history
        )
        self.history_button.pack(side=tk.TOP, pady=2)
        self.export_button = tk.Button(
            self.center_frame, text="Export", command=self.export_suggestions
        )
        self.export_button.pack(side=tk.TOP, pady=2)
        self.test_speaker_button = tk.Button(
            self.center_frame, text="Test Speaker", command=self.test_speaker
        )
        self.test_speaker_button.pack(side=tk.TOP, pady=2)
        self.change_user_button = tk.Button(
            self.center_frame, text="Change User", command=self.change_user
        )
        self.change_user_button.pack(side=tk.TOP, pady=2)
        self.upload_button = tk.Button(
            self.center_frame, text="Upload Documents", command=self.upload_document
        )
        self.upload_button.pack(side=tk.TOP, pady=2)

        # Make draggable and resizable
        self.root.bind("<Button-1>", self.start_move)
        self.root.bind("<B1-Motion>", self.do_move)
        self.root.bind("<Configure>", self.on_resize)

        # Final setup with proper centering
        self.root.after(100, self.final_setup)

    def final_setup(self):
        width = 640
        height = 900
        # Use virtual screen for accurate centering
        sw = self.root.winfo_vrootwidth()
        sh = self.root.winfo_vrootheight()
        vx = self.root.winfo_vrootx()
        vy = self.root.winfo_vrooty()
        x = vx + (sw - width) // 2
        y = vy + 40  # Nice position near top
        print(
            f"Final setup: virtual screen {sw}x{sh} at ({vx},{vy}), window {width}x{height}, position +{x}+{y}"
        )
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.deiconify()  # Now show it centered
        # Verify window position and size
        self.root.after(20, lambda: self.verify_window(x, y, width, height))
        # Fallback centering if geometry fails
        self.root.after(
            10,
            lambda: self.root.place(relx=0.5, y=40, anchor="n")
            if abs(self.root.winfo_x() - x) > 50
            else None,
        )

    def verify_window(self, expected_x, expected_y, expected_width, expected_height):
        actual_x = self.root.winfo_x()
        actual_y = self.root.winfo_y()
        actual_width = self.root.winfo_width()
        actual_height = self.root.winfo_height()
        centered = abs(actual_x - expected_x) <= 10  # Allow small deviation
        correct_size = (
            actual_width == expected_width and actual_height == expected_height
        )
        print(
            f"Window verification: Expected position +{expected_x}+{expected_y}, size {expected_width}x{expected_height}"
        )
        print(
            f"Actual: position +{actual_x}+{actual_y}, size {actual_width}x{actual_height}"
        )
        print(f"Centered: {centered}, Correct size: {correct_size}")

    def start_move(self, event):
        self.x = event.x
        self.y = event.y

    def do_move(self, event):
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")

    def on_resize(self, event):
        # Update wraplength on resize
        new_width = event.width
        self.label.config(wraplength=new_width - 20)
        print(f"Window resized to {event.width}x{event.height}")

    def update_suggestion(self, text):
        self.label.config(text=text)

    def hide(self):
        self.root.withdraw()

    def show(self):
        self.root.deiconify()

    def thumbs_up_feedback(self):
        self.log_feedback("positive")

    def thumbs_down_feedback(self):
        self.log_feedback("negative")

    def log_feedback(self, feedback_type):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open("data/feedback_log.txt", "a") as f:
            f.write(
                f"{timestamp} | {feedback_type} | Suggestion: {self.label.cget('text')}\n"
            )
        print(f"Feedback logged: {feedback_type}")

    def add_to_history(self, suggestion):
        import datetime

        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.suggestion_history.append(f"[{timestamp}] {suggestion}")
        if len(self.suggestion_history) > 20:  # Limit to 20
            self.suggestion_history.pop(0)

    def show_history(self):
        if self.history_window and self.history_window.winfo_exists():
            self.history_window.lift()
            return
        self.history_window = tk.Toplevel(self.root)
        self.history_window.title("Suggestion History")
        self.history_window.geometry("500x300")
        self.history_window.configure(bg="lightblue")
        history_text = tk.scrolledtext.ScrolledText(
            self.history_window, wrap=tk.WORD, bg="white", fg="black"
        )
        history_text.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)
        history_text.insert(tk.END, "\n".join(self.suggestion_history))
        history_text.config(state=tk.DISABLED)

    def export_suggestions(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title="Export Suggestions",
        )
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write("AI Meeting Copilot Suggestions\n\n")
                    f.write("\n".join(self.suggestion_history))
                messagebox.showinfo(
                    "Export Successful", f"Suggestions exported to {file_path}"
                )
            except Exception as e:
                messagebox.showerror("Export Failed", f"Error: {str(e)}")

    def adjust_window_size(self, suggestion=""):
        # Calculate required size based on text
        text = self.label.cget("text")
        lines = text.count("\n") + 1
        char_count = len(text)
        width = min(600, max(400, char_count // 2))  # Dynamic width
        height = min(400, max(150, 100 + lines * 20))  # Dynamic height
        self.root.geometry(f"{width}x{height}")
        self.label.config(wraplength=width - 20)  # Adjust wrap

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    overlay = OverlayUI()
    overlay.update_suggestion("This is a test suggestion for the meeting.")
    overlay.run()
