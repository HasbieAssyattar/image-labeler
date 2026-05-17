import os
import shutil
import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk
from PIL import Image
import requests
import re
import io
import gdown
from threading import Thread

# Set appearance and theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class ImageManager:
    def __init__(self, source_dir=None, target_dir=None):
        self.source_dir = source_dir or "temp"
        self.target_dir = target_dir or "hasil"
        self.images = [] # List of (filename, file_id/path, is_cloud)
        self.current_index = -1
        self.categories = []
        self.is_cloud_mode = False
        
        self.ensure_directories()
        self.refresh_state()

    def ensure_directories(self):
        if not os.path.exists(self.source_dir):
            try: os.makedirs(self.source_dir)
            except: pass
        if not os.path.exists(self.target_dir):
            try: os.makedirs(self.target_dir)
            except: pass

    def refresh_state(self):
        """Scans local folders. Cloud state is handled separately via fetch_gdrive_files."""
        if not self.is_cloud_mode:
            valid_extensions = ('.jpg', '.jpeg', '.png', '.webp')
            try:
                if os.path.exists(self.source_dir):
                    files = [f for f in os.listdir(self.source_dir) if f.lower().endswith(valid_extensions)]
                    files.sort()
                    self.images = [(f, os.path.join(self.source_dir, f), False) for f in files]
                else:
                    self.images = []
            except Exception:
                self.images = []
        
        if self.images:
            if self.current_index == -1 or self.current_index >= len(self.images):
                self.current_index = 0
        else:
            self.current_index = -1

        # Scan categories
        try:
            if os.path.exists(self.target_dir):
                self.categories = [d for d in os.listdir(self.target_dir) 
                                   if os.path.isdir(os.path.join(self.target_dir, d))]
            else:
                self.categories = []
        except Exception:
            self.categories = []

    def fetch_gdrive_files(self, folder_url):
        """Attempts to list files from a public GDrive folder using improved scraping."""
        try:
            # Extract folder ID using more flexible regex
            folder_id = None
            id_patterns = [
                r'folders/([a-zA-Z0-9-_]+)',
                r'id=([a-zA-Z0-9-_]+)',
                r'^([a-zA-Z0-9-_]+)$'
            ]
            for pattern in id_patterns:
                match = re.search(pattern, folder_url)
                if match:
                    folder_id = match.group(1)
                    break
            
            if not folder_id:
                return False, "Invalid Folder Link or ID."

            # Headers to mimic a real browser
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }

            # Use the main folder view which often contains a JSON blob of files
            view_url = f"https://drive.google.com/drive/folders/{folder_id}"
            response = requests.get(view_url, headers=headers, timeout=15)
            
            # Look for the JSON data block that contains file info
            # We look for file IDs (usually 33 chars) and filenames
            # This regex is designed to find file entries in the initial data blob
            raw_data = response.text
            
            # Pattern for finding [file_id, filename, mimetype, ...]
            # We specifically target images
            found_files = []
            
            # Strategy 2: Look for the 'embeddedfolderview' if main fails
            if "window['_initialData']" not in raw_data:
                view_url = f"https://drive.google.com/embeddedfolderview?id={folder_id}"
                response = requests.get(view_url, headers=headers, timeout=15)
                raw_data = response.text

            # Extracting file IDs and Names
            # Strategy 1: GDrive JS data structure (common in main view)
            # Pattern: ["ID", "Name", ... "image/...]
            matches = re.finditer(r'\["([a-zA-Z0-9-_]{25,})","([^"]+)"', raw_data)
            seen_ids = set()
            for m in matches:
                fid, fname = m.group(1), m.group(2)
                if any(fname.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp', '.bmp']):
                    if fid not in seen_ids:
                        found_files.append((fname, fid, True))
                        seen_ids.add(fid)

            # Strategy 2: HTML structure (common in embedded view)
            # Pattern: <div class="flip-entry" id="entry-ID"> ... <div class="flip-entry-title">NAME</div>
            if not found_files:
                html_matches = re.finditer(r'id="entry-([a-zA-Z0-9-_]{25,})".*?class="flip-entry-title">([^<]+)</div>', raw_data, re.DOTALL)
                for m in html_matches:
                    fid, fname = m.group(1), m.group(2)
                    if any(fname.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp', '.bmp']):
                        if fid not in seen_ids:
                            found_files.append((fname, fid, True))
                            seen_ids.add(fid)

            if not found_files:
                return False, "No images detected. Make sure the folder is public and contains images."

            self.images = found_files
            self.is_cloud_mode = True
            self.current_index = 0
            return True, f"Success! Found {len(self.images)} images in GDrive."
        except Exception as e:
            return False, f"Connection error: {str(e)}"

    def get_current_image_data(self):
        """Returns (path_or_id, is_cloud, filename)"""
        if 0 <= self.current_index < len(self.images):
            name, path_id, is_cloud = self.images[self.current_index]
            return path_id, is_cloud, name
        return None, False, None

    def move_or_download_to_category(self, category_name):
        if self.current_index < 0 or self.current_index >= len(self.images):
            return False, "No image selected"

        filename, path_id, is_cloud = self.images[self.current_index]
        dst_dir = os.path.join(self.target_dir, category_name)
        if not os.path.exists(dst_dir):
            os.makedirs(dst_dir)
        
        dst = os.path.join(dst_dir, filename)

        try:
            if is_cloud:
                # Download from GDrive
                url = f"https://drive.google.com/uc?id={path_id}"
                gdown.download(url, dst, quiet=True)
            else:
                # Local move
                shutil.move(path_id, dst)
            
            self.images.pop(self.current_index)
            if self.current_index >= len(self.images):
                self.current_index = len(self.images) - 1
            elif self.current_index < 0 and len(self.images) > 0:
                self.current_index = 0
            
            return True, "Success"
        except Exception as e:
            return False, str(e)

    def next_image(self):
        if self.current_index < len(self.images) - 1:
            self.current_index += 1
            return True
        return False

    def prev_image(self):
        if self.current_index > 0:
            self.current_index -= 1
            return True
        return False

class DataLabelerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Image Labeler Cloud")
        self.geometry("1250x850")
        
        self.manager = ImageManager()
        
        self.setup_ui()
        self.load_current_image()

    def setup_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- Sidebar ---
        self.sidebar = ctk.CTkFrame(self, width=300, corner_radius=0)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")
        
        self.logo_label = ctk.CTkLabel(self.sidebar, text="IMAGE LABELER", font=ctk.CTkFont(size=22, weight="bold"))
        self.logo_label.pack(pady=(25, 10))

        # Tabs for Source Selection
        self.tabs = ctk.CTkTabview(self.sidebar, height=200)
        self.tabs.pack(fill="x", padx=10, pady=5)
        self.tabs.add("Local")
        self.tabs.add("GDrive")

        # Local Tab
        self.btn_source = ctk.CTkButton(self.tabs.tab("Local"), text="Select Local Folder", command=self.select_source)
        self.btn_source.pack(fill="x", pady=5)
        self.source_lbl = ctk.CTkLabel(self.tabs.tab("Local"), text=f"Src: {os.path.basename(self.manager.source_dir)}", font=ctk.CTkFont(size=11), text_color="gray")
        self.source_lbl.pack()

        # GDrive Tab
        self.gdrive_entry = ctk.CTkEntry(self.tabs.tab("GDrive"), placeholder_text="Paste Folder Link/ID")
        self.gdrive_entry.pack(fill="x", pady=5)
        self.btn_gdrive = ctk.CTkButton(self.tabs.tab("GDrive"), text="Connect GDrive", command=self.connect_gdrive, fg_color="#1db954", hover_color="#19a34a")
        self.btn_gdrive.pack(fill="x", pady=5)

        # Target Folder
        self.target_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.target_frame.pack(fill="x", padx=15, pady=5)
        self.btn_target = ctk.CTkButton(self.target_frame, text="Select Destination", command=self.select_target, fg_color="gray30")
        self.btn_target.pack(fill="x", pady=5)
        self.target_lbl = ctk.CTkLabel(self.target_frame, text=f"Dst: {os.path.basename(self.manager.target_dir)}", font=ctk.CTkFont(size=11), text_color="gray")
        self.target_lbl.pack()

        # Categories
        self.category_scroll = ctk.CTkScrollableFrame(self.sidebar, label_text="Category Labels")
        self.category_scroll.pack(fill="both", expand=True, padx=15, pady=15)
        self.create_category_buttons()
        
        self.refresh_btn = ctk.CTkButton(self.sidebar, text="Refresh All", command=self.refresh_app, fg_color="transparent", border_width=1)
        self.refresh_btn.pack(pady=20, padx=20)

        # --- Main Content ---
        self.main_content = ctk.CTkFrame(self, fg_color="transparent")
        self.main_content.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        
        self.image_container = ctk.CTkFrame(self.main_content, fg_color="#1a1a1a", corner_radius=15)
        self.image_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.image_label = ctk.CTkLabel(self.image_container, text="Ready to label...", text_color="gray")
        self.image_label.pack(fill="both", expand=True, padx=20, pady=20)
        
        self.filename_label = ctk.CTkLabel(self.main_content, text="", font=ctk.CTkFont(size=14, weight="bold"))
        self.filename_label.pack(pady=(0, 5))
        
        self.loading_progress = ctk.CTkProgressBar(self.main_content, width=400)
        self.loading_progress.pack(pady=5)
        self.loading_progress.set(0)

        # --- Footer ---
        self.footer = ctk.CTkFrame(self, height=100, corner_radius=15)
        self.footer.grid(row=1, column=1, sticky="ew", padx=20, pady=(0, 20))
        
        self.nav_container = ctk.CTkFrame(self.footer, fg_color="transparent")
        self.nav_container.pack(fill="x", expand=True, padx=20, pady=15)

        self.btn_back = ctk.CTkButton(self.nav_container, text="← BACK", command=self.on_back, width=120)
        self.btn_back.pack(side="left")
        
        self.stats_label = ctk.CTkLabel(self.nav_container, text="0 / 0 Images", font=ctk.CTkFont(size=16, weight="bold"))
        self.stats_label.pack(side="left", expand=True)
        
        self.btn_next = ctk.CTkButton(self.nav_container, text="SKIP NEXT →", command=self.on_next, width=120)
        self.btn_next.pack(side="right")

    def connect_gdrive(self):
        url = self.gdrive_entry.get().strip()
        if not url: return
        
        # Warning about potential slowness
        confirm = messagebox.askokcancel("GDrive Connection", 
            "Menghubungkan ke Google Drive mungkin akan sedikit lambat karena aplikasi perlu mengakses folder publik dan menyiapkan sinkronisasi data. Lanjutkan?")
        if not confirm:
            return
        
        self.image_label.configure(text="Connecting to GDrive...")
        def task():
            success, msg = self.manager.fetch_gdrive_files(url)
            self.after(0, lambda: self.finish_connect(success, msg))
        
        Thread(target=task).start()

    def finish_connect(self, success, msg):
        if success:
            messagebox.showinfo("Success", msg)
            self.refresh_app()
        else:
            messagebox.showerror("Error", msg)
            self.image_label.configure(text="Connection failed.")

    def select_source(self):
        folder = filedialog.askdirectory()
        if folder:
            self.manager.is_cloud_mode = False
            self.manager.source_dir = folder
            self.source_lbl.configure(text=f"Src: {os.path.basename(folder)}")
            self.refresh_app()

    def select_target(self):
        folder = filedialog.askdirectory()
        if folder:
            self.manager.target_dir = folder
            self.target_lbl.configure(text=f"Dst: {os.path.basename(folder)}")
            self.refresh_app()

    def create_category_buttons(self):
        for widget in self.category_scroll.winfo_children(): widget.destroy()
        if not self.manager.categories:
            ctk.CTkLabel(self.category_scroll, text="No subfolders found", font=ctk.CTkFont(size=12, slant="italic")).pack(pady=20)
            return
        for category in self.manager.categories:
            ctk.CTkButton(self.category_scroll, text=category.upper(), height=50, command=lambda c=category: self.on_classify(c)).pack(fill="x", pady=5, padx=5)

    def load_current_image(self):
        path_id, is_cloud, name = self.manager.get_current_image_data()
        total = len(self.manager.images)
        current = self.manager.current_index + 1 if total > 0 else 0
        self.stats_label.configure(text=f"{current} / {total} Images")
        
        if path_id:
            self.loading_progress.set(0.3)
            def task():
                try:
                    if is_cloud:
                        # Fetch thumbnail from GDrive (faster than full download)
                        thumb_url = f"https://drive.google.com/thumbnail?id={path_id}&sz=w1000"
                        response = requests.get(thumb_url, timeout=10)
                        img_data = Image.open(io.BytesIO(response.content))
                    else:
                        with Image.open(path_id) as img_temp:
                            img_data = img_temp.copy()
                    
                    self.after(0, lambda: self.display_image(img_data, name))
                except Exception as e:
                    self.after(0, lambda: self.image_label.configure(text=f"Error: {e}"))
            
            Thread(target=task).start()
        else:
            self.image_label.configure(image=None, text="Queue Empty")
            self.filename_label.configure(text="")
            self.loading_progress.set(0)

    def display_image(self, img_data, name):
        w, h = img_data.size
        cw, ch = max(self.image_container.winfo_width(), 800), max(self.image_container.winfo_height(), 500)
        ratio = min((cw-40)/w, (ch-40)/h)
        ctk_img = ctk.CTkImage(light_image=img_data, dark_image=img_data, size=(int(w*ratio), int(h*ratio)))
        self.image_label.configure(image=ctk_img, text="")
        self.filename_label.configure(text=name)
        self.loading_progress.set(1)

    def refresh_app(self):
        self.manager.refresh_state()
        self.create_category_buttons()
        self.load_current_image()

    def on_classify(self, category):
        self.image_label.configure(text="Processing...")
        def task():
            success, msg = self.manager.move_or_download_to_category(category)
            self.after(0, lambda: self.finish_action(success, msg))
        Thread(target=task).start()

    def finish_action(self, success, msg):
        if not success: messagebox.showerror("Error", msg)
        self.load_current_image()

    def on_next(self):
        if self.manager.next_image(): self.load_current_image()
        else: messagebox.showinfo("End", "No more images.")

    def on_back(self):
        if self.manager.prev_image(): self.load_current_image()
        else: messagebox.showinfo("Start", "First image.")

if __name__ == "__main__":
    app = DataLabelerApp()
    app.mainloop()
