import os
import shutil
import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk
from PIL import Image, ImageTk, ImageOps
import requests
import re
import io
import gdown
import cv2
from threading import Thread, Lock
import time
import subprocess
import winsound
import tempfile
from collections import deque

try:
    import imageio_ffmpeg
    HAS_FFMPEG = True
except ImportError:
    HAS_FFMPEG = False

HAS_FFPY = False # Disabling due to build issues on Python 3.14

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
            valid_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.mp4', '.avi', '.mov', '.mkv')
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
            valid_exts = ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.mp4', '.avi', '.mov', '.mkv']
            for m in matches:
                fid, fname = m.group(1), m.group(2)
                if any(fname.lower().endswith(ext) for ext in valid_exts):
                    if fid not in seen_ids:
                        found_files.append((fname, fid, True))
                        seen_ids.add(fid)

            # Strategy 2: HTML structure (common in embedded view)
            # Pattern: <div class="flip-entry" id="entry-ID"> ... <div class="flip-entry-title">NAME</div>
            if not found_files:
                html_matches = re.finditer(r'id="entry-([a-zA-Z0-9-_]{25,})".*?class="flip-entry-title">([^<]+)</div>', raw_data, re.DOTALL)
                for m in html_matches:
                    fid, fname = m.group(1), m.group(2)
                    if any(fname.lower().endswith(ext) for ext in valid_exts):
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

        self.VERSION = "3.1"
        self.title(f"Media Labeler v{self.VERSION}")
        self.geometry("1250x850")
        
        self.manager = ImageManager()
        self.current_video_cap = None
        self.video_playing = False
        self.video_paused = False
        self.video_thread = None
        self.frame_queue = deque(maxlen=2)
        self.cap_lock = Lock()
        self.video_start_time = 0
        self.pause_start_time = 0
        self.current_frame_idx = 0
        self.total_frames = 0
        self.temp_audio_file = None
        self.media_list_visible = False
        
        self.setup_ui()
        self.load_current_media()
        self.sidebar_visible = True
        self.bind("<space>", lambda e: self.toggle_pause())
        self.bind("<Left>", lambda e: self.on_classify("back"))
        self.bind("<Right>", lambda e: self.on_classify("next"))

    def stop_video(self):
        # 1. Signal stop
        self.video_playing = False
        
        # 2. Wait a moment for thread to see the signal or use lock
        with self.cap_lock:
            if self.current_video_cap:
                self.current_video_cap.release()
                self.current_video_cap = None
        
        # 3. Stop sound
        try: winsound.PlaySound(None, winsound.SND_PURGE)
        except: pass

        # Cleanup temp audio
        if self.temp_audio_file and os.path.exists(self.temp_audio_file):
            try: os.remove(self.temp_audio_file)
            except: pass
            self.temp_audio_file = None

    def setup_ui(self):
        # Main Paned Container for Resizable Sidebar
        self.paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg="#242424", bd=0, sashwidth=4, sashpad=0)
        self.paned.pack(fill="both", expand=True)

        # --- Sidebar ---
        self.sidebar = ctk.CTkFrame(self.paned, width=300, corner_radius=0)
        # self.sidebar.grid(...) -> We use paned.add instead
        
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
        
        self.source_info_frame = ctk.CTkFrame(self.tabs.tab("Local"), fg_color="transparent")
        self.source_info_frame.pack(fill="x")
        self.source_lbl = ctk.CTkLabel(self.source_info_frame, text=f"Src: {os.path.basename(self.manager.source_dir)}", font=ctk.CTkFont(size=11), text_color="gray")
        self.source_lbl.pack(side="left", padx=5)
        self.btn_open_src = ctk.CTkButton(self.source_info_frame, text="📂", width=30, height=20, command=lambda: self.open_in_explorer(self.manager.source_dir), fg_color="gray30")
        self.btn_open_src.pack(side="right", padx=5)

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
        
        self.target_info_frame = ctk.CTkFrame(self.target_frame, fg_color="transparent")
        self.target_info_frame.pack(fill="x")
        self.target_lbl = ctk.CTkLabel(self.target_info_frame, text=f"Dst: {os.path.basename(self.manager.target_dir)}", font=ctk.CTkFont(size=11), text_color="gray")
        self.target_lbl.pack(side="left", padx=5)
        self.btn_open_dst = ctk.CTkButton(self.target_info_frame, text="📂", width=30, height=20, command=lambda: self.open_in_explorer(self.manager.target_dir), fg_color="gray30")
        self.btn_open_dst.pack(side="right", padx=5)

        # Categories Toggle
        self.cat_header = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.cat_header.pack(fill="x", padx=15, pady=(10, 0))
        self.cat_title = ctk.CTkLabel(self.cat_header, text="CATEGORIES", font=ctk.CTkFont(weight="bold"))
        self.cat_title.pack(side="left")
        self.btn_toggle_cat = ctk.CTkButton(self.cat_header, text="▼", width=30, height=20, command=self.toggle_categories, fg_color="transparent")
        self.btn_toggle_cat.pack(side="right")

        # Categories
        self.category_scroll = ctk.CTkScrollableFrame(self.sidebar, label_text="")
        self.category_scroll.pack(fill="both", expand=True, padx=15, pady=(5, 15))
        self.cats_visible = True
        self.create_category_buttons()
        
        self.refresh_btn = ctk.CTkButton(self.sidebar, text="Refresh All", command=self.refresh_app, fg_color="transparent", border_width=1)
        self.refresh_btn.pack(pady=20, padx=20)
        
        self.paned.add(self.sidebar)

        # --- Right Container (Main + Footer) ---
        self.right_container = ctk.CTkFrame(self.paned, fg_color="transparent")
        self.paned.add(self.right_container)
        
        # --- Sidebar Toggle Button (Floating in Right Container) ---
        self.btn_toggle_sidebar = ctk.CTkButton(self.right_container, text="☰", width=35, height=35, 
                                               command=self.toggle_sidebar, fg_color="gray30", hover_color="gray40")
        self.btn_toggle_sidebar.place(x=10, y=10, anchor="nw")

        # --- Footer (Pack this side=bottom FIRST to ensure visibility) ---
        self.footer = ctk.CTkFrame(self.right_container, height=100, corner_radius=15)
        self.footer.pack(fill="x", side="bottom", padx=20, pady=(0, 20))

        # --- Main Content ---
        self.main_content = ctk.CTkFrame(self.right_container, fg_color="transparent")
        self.main_content.pack(fill="both", expand=True, side="top", padx=20, pady=(20, 0))
        
        self.image_container = ctk.CTkFrame(self.main_content, fg_color="#1a1a1a", corner_radius=15)
        self.image_container.pack(fill="both", expand=True, padx=10, pady=10)
        self.image_container.update()
        
        self.image_label = ctk.CTkLabel(self.image_container, text="Ready to label...", text_color="gray")
        self.image_label.pack(fill="both", expand=True, padx=20, pady=20)
        
        # --- Video Controls ---
        self.video_ctrls = ctk.CTkFrame(self.main_content, fg_color="transparent")
        self.video_ctrls.pack(fill="x", padx=10)
        
        self.video_slider = ctk.CTkSlider(self.video_ctrls, from_=0, to=100, command=self.on_slider_move)
        self.video_slider.pack(fill="x", side="left", expand=True, padx=(5, 10))
        self.video_slider.set(0)
        
        self.btn_play_pause = ctk.CTkButton(self.video_ctrls, text="⏸", width=40, command=self.toggle_pause, fg_color="gray30")
        self.btn_play_pause.pack(side="right")
        
        self.filename_container = ctk.CTkFrame(self.main_content, fg_color="transparent")
        self.filename_container.pack(fill="x", pady=5)
        
        self.filename_label = ctk.CTkLabel(self.filename_container, text="", font=ctk.CTkFont(size=14, weight="bold"))
        self.filename_label.pack(side="left", expand=True, padx=(40, 0))
        
        self.btn_playlist = ctk.CTkButton(self.filename_container, text="📜 List", width=60, height=25, command=self.toggle_media_list, fg_color="gray30", hover_color="gray40")
        self.btn_playlist.pack(side="right", padx=10)
        
        # Move playlist to a better place to avoid push issues
        self.media_list_container = ctk.CTkScrollableFrame(self.right_container, height=0, label_text="Project Media Playlist")
        
        self.loading_progress = ctk.CTkProgressBar(self.main_content, width=400)
        self.loading_progress.pack(pady=5)
        self.loading_progress.set(0)

        # Move playlist to a better place
        self.media_list_container = ctk.CTkScrollableFrame(self.right_container, height=0, label_text="Project Media Playlist")
        
        self.loading_progress = ctk.CTkProgressBar(self.main_content, width=400)
        self.loading_progress.pack(pady=5)
        self.loading_progress.set(0)

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

    def open_in_explorer(self, path):
        if os.path.exists(path):
            os.startfile(path)

    def toggle_sidebar(self):
        self.sidebar_visible = not self.sidebar_visible
        if self.sidebar_visible:
            self.paned.add(self.sidebar, before=self.right_container)
            self.btn_toggle_sidebar.configure(text="☰")
        else:
            self.paned.forget(self.sidebar)
            self.btn_toggle_sidebar.configure(text="❱") # Arrow pointing right when closed

    def toggle_categories(self):
        self.cats_visible = not self.cats_visible
        if self.cats_visible:
            self.category_scroll.pack(fill="both", expand=True, padx=15, pady=(5, 15))
            self.btn_toggle_cat.configure(text="▼")
        else:
            self.category_scroll.pack_forget()
            self.btn_toggle_cat.configure(text="▲")

    def is_video_file(self, filename):
        return filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))

    def create_category_buttons(self):
        for widget in self.category_scroll.winfo_children(): widget.destroy()
        if not self.manager.categories:
            ctk.CTkLabel(self.category_scroll, text="No subfolders found", font=ctk.CTkFont(size=12, slant="italic")).pack(pady=20)
            return
        for category in self.manager.categories:
            ctk.CTkButton(self.category_scroll, text=category.upper(), height=50, command=lambda c=category: self.on_classify(c)).pack(fill="x", pady=5, padx=5)

    def load_current_media(self):
        self.stop_video()
        if self.media_list_visible:
            self.update_media_list()
            
        path_id, is_cloud, name = self.manager.get_current_image_data()
        total = len(self.manager.images)
        current = self.manager.current_index + 1 if total > 0 else 0
        self.stats_label.configure(text=f"{current} / {total} Media Files")
        
        if path_id:
            self.loading_progress.set(0.3)
            def task():
                try:
                    if is_cloud:
                        # For videos in GDrive, we still try to get a thumbnail
                        thumb_url = f"https://drive.google.com/thumbnail?id={path_id}&sz=w1000"
                        response = requests.get(thumb_url, timeout=10)
                        img_data = ImageOps.exif_transpose(Image.open(io.BytesIO(response.content)))
                        self.after(0, lambda: self.display_image(img_data, name))
                    else:
                        if self.is_video_file(path_id):
                            if not HAS_FFMPEG:
                                self.after(0, lambda: messagebox.showwarning("Logic Error", "Please install imageio-ffmpeg: pip install imageio-ffmpeg"))
                            self.after(0, lambda: self.start_video_playback(path_id, name))
                        else:
                            with Image.open(path_id) as img_temp:
                                img_data = ImageOps.exif_transpose(img_temp.copy())
                            self.after(0, lambda: self.display_image(img_data, name))
                except Exception as e:
                    self.after(0, lambda: self.image_label.configure(text=f"Error: {e}"))
            
            Thread(target=task).start()
        else:
            self.image_label.configure(image=None, text="Queue Empty")
            self.filename_label.configure(text="")
            self.loading_progress.set(0)

    def on_slider_move(self, value):
        if not self.video_playing or not self.current_video_cap: return
        target_frame = int((value / 100) * self.total_frames)
        with self.cap_lock:
            self.current_video_cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            self.video_start_time = time.time() - (target_frame / self.fps)
            self.current_frame_idx = target_frame
            self.frame_queue.clear()
        
        # Audio seek is hard with winsound, so we just restart it or let it be
        # For a professional feel, we just keep the sync logic handling it

    def toggle_media_list(self):
        self.media_list_visible = not self.media_list_visible
        if self.media_list_visible:
            # Show between main content and footer
            self.media_list_container.pack(fill="x", padx=20, pady=10, before=self.footer)
            self.media_list_container.configure(height=200)
            self.update_media_list()
        else:
            # Hide
            self.media_list_container.pack_forget()

    def update_media_list(self):
        for widget in self.media_list_container.winfo_children():
            widget.destroy()
            
        for i, (fname, _, _) in enumerate(self.manager.images):
            is_current = (i == self.manager.current_index)
            bg_color = "#1f538d" if is_current else "transparent"
            btn = ctk.CTkButton(self.media_list_container, text=f"{i+1}. {fname}", 
                                anchor="w", fg_color=bg_color, hover_color="#2b71ba",
                                command=lambda idx=i: self.jump_to_media(idx))
            btn.pack(fill="x", pady=2, padx=5)
            
    def jump_to_media(self, index):
        self.manager.current_index = index
        self.load_current_media()
        self.update_media_list()

    def toggle_pause(self):
        if not self.video_playing: return
        self.video_paused = not self.video_paused
        if self.video_paused:
            self.pause_start_time = time.time()
            self.btn_play_pause.configure(text="▶")
            winsound.PlaySound(None, winsound.SND_PURGE) # Stop sound
        else:
            # Resume
            self.btn_play_pause.configure(text="⏸")
            drift = time.time() - self.pause_start_time
            self.video_start_time += drift
            if self.temp_audio_file:
                # Restart sound from approx position? 
                # Winsound can't seek, so we just play from start or keep it silent
                winsound.PlaySound(self.temp_audio_file, winsound.SND_ASYNC | winsound.SND_LOOP)
            self.play_video_frame()

    def start_video_playback(self, path, name):
        self.stop_video()
        
        self.current_video_cap = cv2.VideoCapture(path)
        self.fps = self.current_video_cap.get(cv2.CAP_PROP_FPS) or 30
        self.total_frames = int(self.current_video_cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.video_playing = True
        self.video_paused = False
        self.btn_play_pause.configure(text="⏸")
        self.filename_label.configure(text=f"VIDEO: {name}")
        self.loading_progress.set(1)
        self.frame_queue.clear()
        
        # Pre-determine target size with safe margins for footer
        ret, frame = self.current_video_cap.read()
        if ret:
            fh, fw, _ = frame.shape
            # Calculate available space properly
            cw = self.right_container.winfo_width() - 40
            ch = self.right_container.winfo_height() - self.footer.winfo_height() - 150
            cw, ch = max(cw, 800), max(ch, 400)
            
            ratio = min(cw/fw, ch/fh)
            self.vid_size = (int(fw*ratio), int(fh*ratio))
            self.current_video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        else:
            self.vid_size = (800, 500)

        # Handle Audio extraction and sync start
        if HAS_FFMPEG:
            def extract_and_play():
                try:
                    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                    temp_dir = tempfile.gettempdir()
                    self.temp_audio_file = os.path.join(temp_dir, f"label_audio_{int(time.time())}.wav")
                    
                    cmd = [ffmpeg_exe, "-y", "-i", path, "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2", self.temp_audio_file]
                    subprocess.run(cmd, capture_output=True, check=True)
                    
                    if self.video_playing:
                        # AUDIO START POINT
                        winsound.PlaySound(self.temp_audio_file, winsound.SND_ASYNC | winsound.SND_LOOP)
                        self.video_start_time = time.time()
                        self.current_frame_idx = 0
                        # Start video playback
                        self.after(0, self.play_video_frame)
                except Exception as e:
                    print(f"Audio Error: {e}")
                    # Fallback to no audio video start
                    self.video_start_time = time.time()
                    self.after(0, self.play_video_frame)

            Thread(target=extract_and_play, daemon=True).start()
        else:
            self.video_start_time = time.time()
            self.play_video_frame()

        # Start reading frames in background thread
        def reader():
            while self.video_playing:
                if self.video_paused:
                    time.sleep(0.1)
                    continue

                with self.cap_lock:
                    if not self.current_video_cap: break
                    
                    # SYNC CHECK: Only jump if MORE than 60 frames behind
                    if self.video_start_time > 0:
                        elapsed = time.time() - self.video_start_time
                        target_frame = int(elapsed * self.fps)
                        current_cap_frame = self.current_video_cap.get(cv2.CAP_PROP_POS_FRAMES)
                        
                        if abs(target_frame - current_cap_frame) > 60:
                            self.current_video_cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame % self.total_frames)

                    ret, frame = self.current_video_cap.read()
                
                if not ret:
                    # Video finished
                    self.video_playing = False
                    self.after(0, self.stop_video)
                    self.after(0, lambda: self.btn_play_pause.configure(text="▶"))
                    break
                
                # Resizing and converting
                frame = cv2.resize(frame, self.vid_size, interpolation=cv2.INTER_NEAREST)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame)
                
                # Push to queue (low latency mode)
                self.frame_queue.append(img)
                time.sleep(max(0.001, 1/self.fps * 0.4))

        self.video_thread = Thread(target=reader, daemon=True)
        self.video_thread.start()

    def play_video_frame(self):
        if not self.video_playing or self.video_paused:
            return

        if self.video_start_time == 0:
            self.after(10, self.play_video_frame)
            return

        elapsed = time.time() - self.video_start_time
        target_frame = int(elapsed * self.fps)
        
        # Update Slider
        if self.total_frames > 0:
            progress = (min(self.current_frame_idx, self.total_frames) / self.total_frames) * 100
            self.video_slider.set(progress)

        # Drop/Sync
        while len(self.frame_queue) > 1 and self.current_frame_idx < target_frame:
            self.frame_queue.popleft()
            self.current_frame_idx += 1
        
        if self.frame_queue:
            img_data = self.frame_queue.popleft()
            self.current_frame_idx = max(self.current_frame_idx + 1, target_frame)
            
            self.tk_img = ImageTk.PhotoImage(img_data)
            self.image_label._label.configure(image=self.tk_img)
            self.image_label._label.image = self.tk_img
        
        # Scheduling
        next_target_time = (self.current_frame_idx + 1) / self.fps
        current_elapsed = time.time() - self.video_start_time
        delay = int(max(1, (next_target_time - current_elapsed) * 1000))
        
        self.after(delay, self.play_video_frame)

    def display_image(self, img_data, name):
        w, h = img_data.size
        # Calculate available space properly (window size - footer - margins)
        try:
            cw = self.right_container.winfo_width() - 40
            ch = self.right_container.winfo_height() - self.footer.winfo_height() - 150
            cw, ch = max(cw, 800), max(ch, 400)
        except:
            cw, ch = 800, 500
        
        ratio = min(cw/w, ch/h)
        new_size = (int(w*ratio), int(h*ratio))
        
        self.filename_label.configure(text=f"IMAGE: {name}")
        img_ctk = ctk.CTkImage(light_image=img_data, dark_image=img_data, size=new_size)
        self.image_label.configure(image=img_ctk, text="")
        self.loading_progress.set(1)

    def refresh_app(self):
        self.manager.refresh_state()
        self.create_category_buttons()
        self.load_current_media()

    def on_classify(self, category):
        self.image_label.configure(text="Processing...")
        def task():
            success, msg = self.manager.move_or_download_to_category(category)
            self.after(0, lambda: self.finish_action(success, msg))
        Thread(target=task).start()

    def finish_action(self, success, msg):
        if not success: messagebox.showerror("Error", msg)
        self.load_current_media()

    def on_next(self):
        if self.manager.next_image(): self.load_current_media()
        else: messagebox.showinfo("End", "No more media.")

    def on_back(self):
        if self.manager.prev_image(): self.load_current_media()
        else: messagebox.showinfo("Start", "First image.")

if __name__ == "__main__":
    app = DataLabelerApp()
    app.mainloop()
