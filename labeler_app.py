import os
import shutil
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from PIL import Image

# Set appearance and theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class ImageManager:
    """
    Handles the logic for file scanning, index management, and file operations (move/skip).
    """
    def __init__(self, temp_dir="temp", hasil_dir="hasil"):
        self.temp_dir = temp_dir
        self.hasil_dir = hasil_dir
        self.images = []
        self.current_index = -1
        self.categories = []
        
        # Initialize folders and internal state
        self.ensure_directories()
        self.refresh_state()

    def ensure_directories(self):
        """Creates the required root directories if they do not exist."""
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
        if not os.path.exists(self.hasil_dir):
            os.makedirs(self.hasil_dir)

    def refresh_state(self):
        """Scans the source and destination folders for images and categories."""
        # Supported image formats
        valid_extensions = ('.jpg', '.jpeg', '.png', '.webp')
        try:
            if os.path.exists(self.temp_dir):
                # Filter and sort files in the source folder
                self.images = [f for f in os.listdir(self.temp_dir) 
                               if f.lower().endswith(valid_extensions)]
                self.images.sort()
            else:
                self.images = []
        except Exception:
            self.images = []
        
        # Reset current index if it's currently invalid but images exist
        if self.images and self.current_index == -1:
            self.current_index = 0
        elif not self.images:
            self.current_index = -1

        # Scan for existing subfolders in the results directory (used as classification labels)
        try:
            if os.path.exists(self.hasil_dir):
                self.categories = [d for d in os.listdir(self.hasil_dir) 
                                   if os.path.isdir(os.path.join(self.hasil_dir, d))]
            else:
                self.categories = []
        except Exception:
            self.categories = []

    def get_current_image_path(self):
        """Returns the full path of the image at the current index."""
        if 0 <= self.current_index < len(self.images):
            return os.path.join(self.temp_dir, self.images[self.current_index])
        return None

    def move_to_category(self, category_name):
        """
        Moves the current active image from the source folder to the selected category folder.
        Returns (success_status, message).
        """
        if self.current_index < 0 or self.current_index >= len(self.images):
            return False, "No image selected"

        filename = self.images[self.current_index]
        src = os.path.join(self.temp_dir, filename)
        dst_dir = os.path.join(self.hasil_dir, category_name)
        dst = os.path.join(dst_dir, filename)

        try:
            # Ensure the target subfolder exists before moving
            if not os.path.exists(dst_dir):
                os.makedirs(dst_dir)
                
            shutil.move(src, dst)
            
            # Remove the moved image from the internal list and adjust index
            self.images.pop(self.current_index)
            if self.current_index >= len(self.images):
                self.current_index = len(self.images) - 1
            elif self.current_index < 0 and len(self.images) > 0:
                self.current_index = 0
            
            return True, "Success"
        except Exception as e:
            return False, str(e)

    def next_image(self):
        """Increments the current index to the next image."""
        if self.current_index < len(self.images) - 1:
            self.current_index += 1
            return True
        return False

    def prev_image(self):
        """Decrements the current index to the previous image."""
        if self.current_index > 0:
            self.current_index -= 1
            return True
        return False

class DataLabelerApp(ctk.CTk):
    """
    Main UI Application class built with CustomTkinter.
    """
    def __init__(self):
        super().__init__()

        # Window settings
        self.title("Image Labeler")
        self.geometry("1100x750")
        
        # Core logic controller
        self.manager = ImageManager()
        
        # Build UI layout
        self.setup_ui()
        self.load_current_image()
        
        # Inform user about initial setup requirements
        self.check_initial_state()

    def check_initial_state(self):
        """Checks for common configuration issues on startup."""
        if not os.path.exists("hasil"):
            messagebox.showwarning("Folder Missing", "Folder 'hasil/' was not found and has been created. Add subfolders there to create categories.")
        elif not self.manager.categories:
            messagebox.showinfo("No Categories", "No subfolders found in 'hasil/'. Please create folders (e.g., 'dog', 'cat') inside 'hasil/' to see category buttons.")
        
        if not self.manager.images:
            messagebox.showinfo("Empty Queue", "No images found in 'temp/'. Add images to the 'temp/' folder to begin.")

    def setup_ui(self):
        """Initializes all UI components and layouts."""
        # Grid weight configuration
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- Sidebar Navigation & Category Buttons ---
        self.sidebar = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=0, pady=0)
        
        self.logo_label = ctk.CTkLabel(self.sidebar, text="IMAGE LABELER", font=ctk.CTkFont(size=22, weight="bold"))
        self.logo_label.pack(pady=(30, 20))

        # Scrollable area for dynamically generated buttons
        self.category_scroll = ctk.CTkScrollableFrame(self.sidebar, label_text="Categories")
        self.category_scroll.pack(fill="both", expand=True, padx=15, pady=15)
        
        self.create_category_buttons()
        
        self.refresh_btn = ctk.CTkButton(self.sidebar, text="Refresh Folders", command=self.refresh_app, fg_color="transparent", border_width=1)
        self.refresh_btn.pack(pady=20, padx=20)

        # --- Main Image Display Section ---
        self.main_content = ctk.CTkFrame(self, fg_color="transparent")
        self.main_content.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        
        # Dark container for the image preview
        self.image_container = ctk.CTkFrame(self.main_content, fg_color="#1a1a1a", corner_radius=15)
        self.image_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.image_label = ctk.CTkLabel(self.image_container, text="No images found in temp/", text_color="gray")
        self.image_label.pack(fill="both", expand=True, padx=20, pady=20)
        
        self.filename_label = ctk.CTkLabel(self.main_content, text="", font=ctk.CTkFont(size=14, weight="bold"))
        self.filename_label.pack(pady=(0, 10))

        # --- Bottom Navigation Bar ---
        self.footer = ctk.CTkFrame(self, height=100, corner_radius=15)
        self.footer.grid(row=1, column=1, sticky="ew", padx=20, pady=(0, 20))
        
        self.nav_container = ctk.CTkFrame(self.footer, fg_color="transparent")
        self.nav_container.pack(fill="x", expand=True, padx=20, pady=15)

        self.btn_back = ctk.CTkButton(self.nav_container, text="← BACK", command=self.on_back, 
                                     fg_color="gray25", hover_color="gray35", width=120, height=45)
        self.btn_back.pack(side="left")
        
        self.stats_label = ctk.CTkLabel(self.nav_container, text="0 / 0 images", font=ctk.CTkFont(size=16, weight="bold"))
        self.stats_label.pack(side="left", expand=True)
        
        self.btn_next = ctk.CTkButton(self.nav_container, text="SKIP NEXT →", command=self.on_next, 
                                     fg_color="gray25", hover_color="gray35", width=120, height=45)
        self.btn_next.pack(side="right")

    def create_category_buttons(self):
        """Generates classification buttons based on subdirectories found in 'hasil/'."""
        # Clear existing buttons
        for widget in self.category_scroll.winfo_children():
            widget.destroy()

        if not self.manager.categories:
            lbl = ctk.CTkLabel(self.category_scroll, text="Add subfolders to 'hasil/'\nto see buttons", 
                             font=ctk.CTkFont(size=12, slant="italic"), text_color="gray")
            lbl.pack(pady=20)
            return

        # Create a button for each category found
        for category in self.manager.categories:
            btn = ctk.CTkButton(
                self.category_scroll, 
                text=category.upper(),
                command=lambda c=category: self.on_classify(c),
                height=50,
                corner_radius=10,
                font=ctk.CTkFont(weight="bold")
            )
            btn.pack(fill="x", pady=6, padx=5)

    def load_current_image(self):
        """Loads and scales the current image to the display area."""
        path = self.manager.get_current_image_path()
        total = len(self.manager.images)
        current = self.manager.current_index + 1 if total > 0 else 0
        
        # Update progress label
        self.stats_label.configure(text=f"{current} / {total} Images")
        
        if path:
            try:
                # Open with context manager to ensure the file handle is released immediately
                # This prevents WinError 32 (file used by another process) during move
                with Image.open(path) as img_temp:
                    img_data = img_temp.copy()
                
                # Calculate new dimensions while keeping aspect ratio
                w, h = img_data.size
                canvas_w = self.image_container.winfo_width()
                canvas_h = self.image_container.winfo_height()
                
                # Default sizes if window isn't rendered yet
                if canvas_w < 100: canvas_w = 800 
                if canvas_h < 100: canvas_h = 500 
                
                ratio = min((canvas_w-40)/w, (canvas_h-40)/h)
                new_size = (int(w*ratio), int(h*ratio))
                
                # Render the image in the UI
                ctk_img = ctk.CTkImage(light_image=img_data, dark_image=img_data, size=new_size)
                self.image_label.configure(image=ctk_img, text="")
                self.filename_label.configure(text=os.path.basename(path))
            except Exception as e:
                self.image_label.configure(image=None, text=f"Error loading image: {e}")
        else:
            self.image_label.configure(image=None, text="No images to display")
            self.filename_label.configure(text="Queue Finished")

    def refresh_app(self):
        """Refreshes the folders and UI state."""
        self.manager.refresh_state()
        self.create_category_buttons()
        self.load_current_image()

    def on_classify(self, category):
        """Event handler for classification button clicks."""
        success, msg = self.manager.move_to_category(category)
        if success:
            self.load_current_image()
        else:
            messagebox.showerror("Error", f"Failed to move file: {msg}")

    def on_next(self):
        """Event handler for 'SKIP NEXT' button."""
        if not self.manager.next_image():
            messagebox.showinfo("End", "No more images in queue.")
        self.load_current_image()

    def on_back(self):
        """Event handler for 'BACK' button."""
        if not self.manager.prev_image():
            messagebox.showinfo("Start", "This is the first image.")
        self.load_current_image()

if __name__ == "__main__":
    app = DataLabelerApp()
    # Slight delay before initial load to allow UI dimensions to be calculated correctly
    app.after(100, app.load_current_image)
    app.mainloop()
