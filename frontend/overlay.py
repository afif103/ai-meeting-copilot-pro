import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import datetime
import os


class OverlayUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()  # Hide until ready
        self.root.attributes("-topmost", True)  # Always on top
        self.root.attributes("-alpha", 0.85)  # Semi-transparent
        self.root.configure(bg="lightblue")
        
        self.history_window = None
        self.suggestion_history = []
        self.is_recording = True
        
        # Main container - fixes layout issues
        main_container = tk.Frame(self.root, bg="lightblue")
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Label for suggestions at the top
        self.label = tk.Label(
            main_container,
            text="Waiting for suggestions...",
            font=("Arial", 12),
            bg="lightblue",
            fg="black",
            wraplength=600,
            justify="left",
        )
        self.label.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # Button frame below the label
        self.button_frame = tk.Frame(main_container, bg="lightblue")
        self.button_frame.pack(fill=tk.X)
        
        # Center frame for buttons
        self.center_frame = tk.Frame(self.button_frame, bg="lightblue")
        self.center_frame.pack(anchor="center")
        
        # All buttons with consistent styling
        button_style = {"width": 18, "font": ("Arial", 10), "bg": "#e0e0e0", "activebackground": "#d0d0d0"}
        
        self.thumbs_up = tk.Button(
            self.center_frame, 
            text="👍 Like", 
            command=self.thumbs_up_feedback,
            **button_style
        )
        self.thumbs_up.pack(pady=3)
        
        self.thumbs_down = tk.Button(
            self.center_frame, 
            text="👎 Dislike", 
            command=self.thumbs_down_feedback,
            **button_style
        )
        self.thumbs_down.pack(pady=3)
        
        self.finalize_button = tk.Button(
            self.center_frame, 
            text="✓ Finalize", 
            command=self.finalize_suggestion,
            **button_style
        )
        self.finalize_button.pack(pady=3)
        
        self.pause_resume_button = tk.Button(
            self.center_frame, 
            text="⏸ Pause Recording", 
            command=self.toggle_recording,
            **button_style
        )
        self.pause_resume_button.pack(pady=3)
        
        self.history_button = tk.Button(
            self.center_frame, 
            text="📜 History", 
            command=self.show_history,
            **button_style
        )
        self.history_button.pack(pady=3)
        
        self.export_button = tk.Button(
            self.center_frame, 
            text="💾 Export", 
            command=self.export_suggestions,
            **button_style
        )
        self.export_button.pack(pady=3)
        
        self.test_speaker_button = tk.Button(
            self.center_frame, 
            text="🔊 Test Speaker", 
            command=self.test_speaker,
            **button_style
        )
        self.test_speaker_button.pack(pady=3)
        
        self.change_user_button = tk.Button(
            self.center_frame, 
            text="👤 Change User", 
            command=self.change_user,
            **button_style
        )
        self.change_user_button.pack(pady=3)
        
        self.upload_button = tk.Button(
            self.center_frame, 
            text="📁 Upload Documents", 
            command=self.upload_document,
            **button_style
        )
        self.upload_button.pack(pady=3)
        
        # Make draggable - only from label area
        self.label.bind("<Button-1>", self.start_move)
        self.label.bind("<B1-Motion>", self.do_move)
        
        # Bind resize event
        self.root.bind("<Configure>", self.on_resize)
        
        # Final setup with proper centering
        self.root.after(100, self.final_setup)
    
    def final_setup(self):
        width = 640
        height = 580  # Increased to fit all buttons comfortably
        
        # Get screen dimensions
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        
        # Calculate center position
        x = (sw - width) // 2
        y = (sh - height) // 2
        
        print(f"Screen: {sw}x{sh}, Window: {width}x{height}, Position: +{x}+{y}")
        
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(width, 500)
        self.root.maxsize(width, 800)
        self.root.resizable(False, True)  # Allow vertical resize only
        
        self.root.deiconify()  # Show window
        
        # Verify after a short delay
        self.root.after(200, lambda: self.verify_window(x, y, width, height))
    
    def verify_window(self, expected_x, expected_y, expected_width, expected_height):
        actual_x = self.root.winfo_x()
        actual_y = self.root.winfo_y()
        actual_width = self.root.winfo_width()
        actual_height = self.root.winfo_height()
        
        centered = abs(actual_x - expected_x) <= 10
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
        if hasattr(self, 'x') and hasattr(self, 'y'):
            deltax = event.x - self.x
            deltay = event.y - self.y
            x = self.root.winfo_x() + deltax
            y = self.root.winfo_y() + deltay
            self.root.geometry(f"+{x}+{y}")
    
    def on_resize(self, event):
        # Update wraplength on resize
        if event.widget == self.root:
            new_width = event.width
            self.label.config(wraplength=new_width - 40)
    
    def update_suggestion(self, text):
        self.label.config(text=text)
        self.add_to_history(text)
    
    def hide(self):
        self.root.withdraw()
    
    def show(self):
        self.root.deiconify()
    
    def thumbs_up_feedback(self):
        self.log_feedback("positive")
        print("👍 Positive feedback recorded")
    
    def thumbs_down_feedback(self):
        self.log_feedback("negative")
        print("👎 Negative feedback recorded")
    
    def log_feedback(self, feedback_type):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Create data directory if it doesn't exist
        os.makedirs("data", exist_ok=True)
        
        try:
            with open("data/feedback_log.txt", "a", encoding="utf-8") as f:
                f.write(
                    f"{timestamp} | {feedback_type} | Suggestion: {self.label.cget('text')}\n"
                )
            print(f"Feedback logged: {feedback_type}")
        except Exception as e:
            print(f"Error logging feedback: {e}")
    
    def add_to_history(self, suggestion):
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
        self.history_window.geometry("600x400")
        self.history_window.configure(bg="lightblue")
        self.history_window.attributes("-topmost", True)
        
        # Add a label at the top
        header = tk.Label(
            self.history_window,
            text="Suggestion History",
            font=("Arial", 14, "bold"),
            bg="lightblue",
            fg="black"
        )
        header.pack(pady=10)
        
        # Scrolled text widget
        history_text = scrolledtext.ScrolledText(
            self.history_window, 
            wrap=tk.WORD, 
            bg="white", 
            fg="black",
            font=("Arial", 10)
        )
        history_text.pack(expand=True, fill=tk.BOTH, padx=10, pady=(0, 10))
        
        # Insert history
        if self.suggestion_history:
            history_text.insert(tk.END, "\n\n".join(self.suggestion_history))
        else:
            history_text.insert(tk.END, "No suggestions recorded yet.")
        
        history_text.config(state=tk.DISABLED)
        
        # Close button
        close_btn = tk.Button(
            self.history_window,
            text="Close",
            command=self.history_window.destroy,
            width=15
        )
        close_btn.pack(pady=(0, 10))
    
    def export_suggestions(self):
        if not self.suggestion_history:
            messagebox.showwarning("No Data", "No suggestions to export yet.")
            return
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title="Export Suggestions",
        )
        
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write("=" * 60 + "\n")
                    f.write("AI Meeting Copilot - Suggestion Export\n")
                    f.write(f"Exported on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("=" * 60 + "\n\n")
                    f.write("\n\n".join(self.suggestion_history))
                    f.write("\n\n" + "=" * 60 + "\n")
                    f.write(f"Total suggestions: {len(self.suggestion_history)}\n")
                
                messagebox.showinfo(
                    "Export Successful", 
                    f"Suggestions exported to:\n{file_path}"
                )
                print(f"Exported {len(self.suggestion_history)} suggestions to {file_path}")
            except Exception as e:
                messagebox.showerror("Export Failed", f"Error: {str(e)}")
                print(f"Export error: {e}")
    
    def finalize_suggestion(self):
        current_text = self.label.cget("text")
        if current_text and current_text != "Waiting for suggestions...":
            response = messagebox.askyesno(
                "Finalize Suggestion",
                f"Finalize this suggestion?\n\n{current_text[:100]}..."
            )
            if response:
                # Create data directory if needed
                os.makedirs("data", exist_ok=True)
                
                # Save to finalized suggestions
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open("data/finalized_suggestions.txt", "a", encoding="utf-8") as f:
                    f.write(f"\n{'='*60}\n")
                    f.write(f"Finalized at: {timestamp}\n")
                    f.write(f"{current_text}\n")
                
                messagebox.showinfo("Success", "Suggestion finalized and saved!")
                print("Suggestion finalized")
        else:
            messagebox.showinfo("No Suggestion", "No active suggestion to finalize.")
    
    def toggle_recording(self):
        self.is_recording = not self.is_recording
        
        if self.is_recording:
            self.pause_resume_button.config(text="⏸ Pause Recording")
            print("Recording resumed")
        else:
            self.pause_resume_button.config(text="▶ Resume Recording")
            print("Recording paused")
    
    def test_speaker(self):
        try:
            import winsound
            winsound.Beep(800, 500)  # Frequency 800Hz, duration 500ms
            messagebox.showinfo(
                "Test Speaker", 
                "Beep played successfully. Speaker is working."
            )
        except Exception as e:
            messagebox.showerror("Test Speaker Failed", f"Error: {str(e)}")
    
    def change_user(self):
        from tkinter import simpledialog
        
        new_user = simpledialog.askstring(
            "Change User",
            "Enter username:",
            parent=self.root
        )
        
        if new_user:
            messagebox.showinfo("User Changed", f"User changed to: {new_user}")
            print(f"User changed to: {new_user}")
        else:
            print("User change cancelled")
    
    def upload_document(self):
        file_paths = filedialog.askopenfilenames(
            title="Select Documents",
            filetypes=[
                ("All files", "*.*"),
                ("PDF files", "*.pdf"),
                ("Text files", "*.txt"),
                ("Word documents", "*.docx"),
                ("Excel files", "*.xlsx")
            ]
        )
        
        if file_paths:
            file_count = len(file_paths)
            file_names = "\n".join([os.path.basename(f) for f in file_paths])
            messagebox.showinfo(
                "Upload Successful",
                f"{file_count} file(s) selected:\n\n{file_names}"
            )
            print(f"Uploaded {file_count} document(s)")
            for path in file_paths:
                print(f"  - {path}")
        else:
            print("Upload cancelled")
    
    def adjust_window_size(self, suggestion=""):
        """
        Optional method to dynamically adjust window size based on content.
        Not used by default but available if needed.
        """
        text = self.label.cget("text")
        lines = text.count("\n") + 1
        char_count = len(text)
        
        width = min(640, max(400, char_count // 2))
        height = min(800, max(500, 150 + lines * 20 + 450))  # Account for buttons
        
        self.root.geometry(f"{width}x{height}")
        self.label.config(wraplength=width - 40)
    
    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    overlay = OverlayUI()
    overlay.update_suggestion(
        "This is a test suggestion for the meeting. "
        "The AI has detected that the discussion is focusing on Q4 budget allocation. "
        "Consider reviewing the financial projections document before making final decisions."
    )
    overlay.run()