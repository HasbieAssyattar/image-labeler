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

HAS_FFPY = False  # Disabling due to build issues on Python 3.14

# ── 3-Layer Design Token System (Light, Dark) ─────────────────────────────────
# Layer 1: Primitive Palette
PALETTE = {
    "zinc_950": "#09090B",
    "zinc_900": "#111114",
    "zinc_850": "#18181C",
    "zinc_800": "#222228",
    "zinc_700": "#32323A",
    "zinc_600": "#52525B",
    "zinc_400": "#A1A1AA",
    "zinc_300": "#D4D4D8",
    "zinc_200": "#E4E4E7",
    "zinc_100": "#F4F4F5",
    "zinc_50":  "#FAFAFA",
    "white":    "#FFFFFF",

    "indigo_600": "#4F46E5",
    "indigo_500": "#6366F1",
    "indigo_400": "#818CF8",
    "indigo_100": "#E0E7FF",
    "indigo_950": "#1E1B4B",

    "emerald_600": "#059669",
    "emerald_500": "#10B981",
    "emerald_700": "#047857",

    "amber_600": "#D97706",
    "amber_500": "#F59E0B",
    "rose_600":  "#E11D48",
}

# Layer 2: Semantic Tokens as (Light, Dark) tuples
TOKENS = {
    "bg_app":          (PALETTE["zinc_100"], PALETTE["zinc_950"]),
    "bg_sidebar":      (PALETTE["white"],    PALETTE["zinc_900"]),
    "bg_surface":      (PALETTE["white"],    PALETTE["zinc_850"]),
    "bg_surface_alt":  (PALETTE["zinc_50"],  PALETTE["zinc_800"]),
    "bg_canvas":       (PALETTE["zinc_50"],  "#0C0C0F"),
    "bg_hover":        (PALETTE["zinc_200"], PALETTE["zinc_700"]),

    "text_primary":    (PALETTE["zinc_900"], PALETTE["zinc_50"]),
    "text_secondary":  (PALETTE["zinc_600"], PALETTE["zinc_400"]),
    "text_muted":      ("#71717A",           "#71717A"),
    "text_on_accent":  (PALETTE["white"],    PALETTE["white"]),

    "border_subtle":   (PALETTE["zinc_200"], PALETTE["zinc_800"]),
    "border_strong":   (PALETTE["zinc_300"], PALETTE["zinc_700"]),

    "accent_primary":  (PALETTE["indigo_600"], PALETTE["indigo_500"]),
    "accent_hover":    ("#4338CA",             PALETTE["indigo_600"]),
    "accent_soft":     (PALETTE["indigo_100"], PALETTE["indigo_950"]),
    "accent_text":     (PALETTE["indigo_600"], PALETTE["indigo_400"]),

    "success_primary": (PALETTE["emerald_600"], PALETTE["emerald_500"]),
    "success_hover":   (PALETTE["emerald_700"], PALETTE["emerald_600"]),
    "warning_text":    (PALETTE["amber_600"],   PALETTE["amber_500"]),
    "danger_text":     (PALETTE["rose_600"],    "#FB7185"),
}

# ── CustomTkinter Global Setup ────────────────────────────────────────────────
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class ImageManager:
    def __init__(self, source_dir=None, target_dir=None):
        self.source_dir = source_dir or "temp"
        self.target_dir = target_dir or "hasil"
        self.images = []  # List of (filename, file_id/path, is_cloud)
        self.current_index = -1
        self.categories = []
        self.category_counts = {}
        self.is_cloud_mode = False
        self.undo_stack = []  # List of (src_moved_path, original_path, filename)

        self.ensure_directories()
        self.refresh_state()

    def ensure_directories(self):
        for d in (self.source_dir, self.target_dir):
            if not os.path.exists(d):
                try:
                    os.makedirs(d)
                except Exception:
                    pass

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

        self._scan_categories()

    def _scan_categories(self):
        self.categories = []
        self.category_counts = {}
        try:
            if os.path.exists(self.target_dir):
                dirs = [
                    d for d in os.listdir(self.target_dir)
                    if os.path.isdir(os.path.join(self.target_dir, d))
                ]
                dirs.sort(key=str.lower)
                self.categories = dirs
                for d in dirs:
                    cat_path = os.path.join(self.target_dir, d)
                    try:
                        self.category_counts[d] = sum(
                            1 for f in os.listdir(cat_path)
                            if os.path.isfile(os.path.join(cat_path, f))
                        )
                    except Exception:
                        self.category_counts[d] = 0
        except Exception:
            self.categories = []
            self.category_counts = {}

    def create_category(self, name):
        clean = name.strip()
        if not clean:
            return False, "Category name cannot be empty."
        new_path = os.path.join(self.target_dir, clean)
        if os.path.exists(new_path):
            return False, f"Category '{clean}' already exists."
        try:
            os.makedirs(new_path)
            self._scan_categories()
            return True, clean
        except Exception as e:
            return False, str(e)

    def fetch_gdrive_files(self, folder_url):
        """Attempts to list files from a public GDrive folder using improved scraping."""
        try:
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

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }

            view_url = f"https://drive.google.com/drive/folders/{folder_id}"
            response = requests.get(view_url, headers=headers, timeout=15)
            raw_data = response.text
            found_files = []

            if "window['_initialData']" not in raw_data:
                view_url = f"https://drive.google.com/embeddedfolderview?id={folder_id}"
                response = requests.get(view_url, headers=headers, timeout=15)
                raw_data = response.text

            matches = re.finditer(r'\["([a-zA-Z0-9-_]{25,})","([^"]+)"', raw_data)
            seen_ids = set()
            valid_exts = ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.mp4', '.avi', '.mov', '.mkv']
            for m in matches:
                fid, fname = m.group(1), m.group(2)
                if any(fname.lower().endswith(ext) for ext in valid_exts):
                    if fid not in seen_ids:
                        found_files.append((fname, fid, True))
                        seen_ids.add(fid)

            if not found_files:
                html_matches = re.finditer(
                    r'id="entry-([a-zA-Z0-9-_]{25,})".*?class="flip-entry-title">([^<]+)</div>',
                    raw_data, re.DOTALL
                )
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
            return True, f"Success! Found {len(self.images)} items in GDrive."
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
            return False, "No media selected"

        filename, path_id, is_cloud = self.images[self.current_index]
        dst_dir = os.path.join(self.target_dir, category_name)
        if not os.path.exists(dst_dir):
            os.makedirs(dst_dir)

        dst = os.path.join(dst_dir, filename)

        try:
            if is_cloud:
                url = f"https://drive.google.com/uc?id={path_id}"
                gdown.download(url, dst, quiet=True)
            else:
                shutil.move(path_id, dst)
                self.undo_stack.append((dst, path_id, filename, category_name))

            self.images.pop(self.current_index)
            if self.current_index >= len(self.images):
                self.current_index = len(self.images) - 1
            elif self.current_index < 0 and len(self.images) > 0:
                self.current_index = 0

            self._scan_categories()
            return True, "Success"
        except Exception as e:
            return False, str(e)

    def undo_last_move(self):
        if not self.undo_stack:
            return False, "Nothing to undo."
        moved_path, orig_path, filename, category_name = self.undo_stack.pop()
        if not os.path.exists(moved_path):
            return False, f"File '{filename}' no longer exists at destination."
        try:
            shutil.move(moved_path, orig_path)
            self.refresh_state()
            for idx, (fname, _, _) in enumerate(self.images):
                if fname == filename:
                    self.current_index = idx
                    break
            return True, f"Restored '{filename}' from '{category_name}'"
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

        self.VERSION = "3.2"
        self.title(f"Media Labeler Studio v{self.VERSION}")
        self.geometry("1340x880")
        self.minsize(980, 660)
        self.configure(fg_color=TOKENS["bg_app"])

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
        self.sidebar_visible = True
        self.cats_visible = True
        self.is_dark_mode = True
        self.video_ctrls_visible = False

        self.setup_ui()
        self.load_current_media()
        self._bind_shortcuts()

    # ── Keyboard Shortcuts ────────────────────────────────────────────────────

    def _is_typing_in_entry(self, event):
        widget = event.widget
        return isinstance(widget, (tk.Entry, tk.Text)) or "entry" in str(widget).lower()

    def _bind_shortcuts(self):
        self.bind("<space>", lambda e: None if self._is_typing_in_entry(e) else self.toggle_pause())
        self.bind("<Left>", lambda e: None if self._is_typing_in_entry(e) else self.on_back())
        self.bind("<Right>", lambda e: None if self._is_typing_in_entry(e) else self.on_next())
        self.bind("<Control-z>", lambda e: self.on_undo())
        self.bind("<Control-Z>", lambda e: self.on_undo())

        for num in range(1, 10):
            self.bind(
                str(num),
                lambda e, idx=num - 1: None if self._is_typing_in_entry(e) else self._on_hotkey_category(idx)
            )

    def _on_hotkey_category(self, idx):
        if 0 <= idx < len(self.manager.categories):
            self.on_classify(self.manager.categories[idx])

    # ── Video Cleanup ─────────────────────────────────────────────────────────

    def stop_video(self):
        self.video_playing = False

        with self.cap_lock:
            if self.current_video_cap:
                self.current_video_cap.release()
                self.current_video_cap = None

        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass

        if self.temp_audio_file and os.path.exists(self.temp_audio_file):
            try:
                os.remove(self.temp_audio_file)
            except Exception:
                pass
            self.temp_audio_file = None

    # ── UI Helpers ────────────────────────────────────────────────────────────

    def _font(self, size=12, weight="normal", family="Segoe UI", slant="roman"):
        return ctk.CTkFont(family=family, size=size, weight=weight, slant=slant)

    def _sidebar_divider(self):
        ctk.CTkFrame(self.sidebar, height=1, fg_color=TOKENS["border_subtle"]).pack(
            fill="x", padx=16, pady=8
        )

    def _sidebar_section_label(self, text, parent=None, pack=True):
        lbl = ctk.CTkLabel(
            parent or self.sidebar,
            text=text,
            font=self._font(size=10, weight="bold"),
            text_color=TOKENS["text_muted"]
        )
        if pack:
            lbl.pack(anchor="w", padx=18, pady=(2, 6))
        return lbl

    def _set_video_controls_visible(self, visible):
        if visible and not self.video_ctrls_visible:
            self.video_ctrls.pack(fill="x", padx=4, pady=(8, 0), before=self.loading_progress)
            self.video_ctrls_visible = True
        elif not visible and self.video_ctrls_visible:
            self.video_ctrls.pack_forget()
            self.video_ctrls_visible = False

    # ── UI Setup ──────────────────────────────────────────────────────────────

    def setup_ui(self):
        sash_bg = PALETTE["zinc_800"] if self.is_dark_mode else PALETTE["zinc_200"]
        self.paned = tk.PanedWindow(
            self, orient=tk.HORIZONTAL,
            bg=sash_bg, bd=0, sashwidth=4, sashpad=0
        )
        self.paned.pack(fill="both", expand=True)

        # ══════════════════════════════════════════════════════════════════════
        # SIDEBAR — Clean Studio Panel
        # ══════════════════════════════════════════════════════════════════════
        self.sidebar = ctk.CTkFrame(
            self.paned, width=296, corner_radius=0,
            fg_color=TOKENS["bg_sidebar"]
        )

        # Brand Header
        logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo_frame.pack(fill="x", padx=18, pady=(18, 6))

        brand_mark = ctk.CTkLabel(
            logo_frame, text="LBL",
            width=36, height=32,
            fg_color=TOKENS["accent_primary"],
            text_color=TOKENS["text_on_accent"],
            corner_radius=8,
            font=self._font(size=11, weight="bold", family="Consolas")
        )
        brand_mark.pack(side="left", padx=(0, 10))

        title_col = ctk.CTkFrame(logo_frame, fg_color="transparent")
        title_col.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            title_col, text="Media Labeler",
            font=self._font(size=15, weight="bold"),
            text_color=TOKENS["text_primary"]
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_col, text=f"Studio v{self.VERSION}",
            font=self._font(size=11),
            text_color=TOKENS["text_muted"]
        ).pack(anchor="w")

        self._sidebar_divider()

        # ── SOURCE ────────────────────────────────────────────────────────────
        self._sidebar_section_label("SOURCE")

        self.tabs = ctk.CTkTabview(
            self.sidebar,
            fg_color=TOKENS["bg_surface_alt"],
            segmented_button_fg_color=TOKENS["bg_app"],
            segmented_button_selected_color=TOKENS["accent_primary"],
            segmented_button_selected_hover_color=TOKENS["accent_hover"],
            segmented_button_unselected_color=TOKENS["bg_app"],
            segmented_button_unselected_hover_color=TOKENS["bg_hover"],
            text_color=TOKENS["text_primary"],
            text_color_disabled=TOKENS["text_muted"],
            border_width=1,
            border_color=TOKENS["border_subtle"],
            corner_radius=10,
            height=124,
        )
        self.tabs.pack(fill="x", padx=14, pady=(0, 4))
        self.tabs.add("Local")
        self.tabs.add("GDrive")

        # Local Tab
        local_tab = self.tabs.tab("Local")
        ctk.CTkButton(
            local_tab, text="Select Source Folder", command=self.select_source,
            height=34, fg_color=TOKENS["accent_primary"], hover_color=TOKENS["accent_hover"],
            text_color=TOKENS["text_on_accent"], font=self._font(size=12, weight="bold"),
            corner_radius=8
        ).pack(fill="x", pady=(4, 8))

        self.source_info_frame = ctk.CTkFrame(local_tab, fg_color="transparent")
        self.source_info_frame.pack(fill="x")
        self.source_lbl = ctk.CTkLabel(
            self.source_info_frame,
            text=f"Folder: {os.path.basename(self.manager.source_dir)}",
            font=self._font(size=11), text_color=TOKENS["text_secondary"]
        )
        self.source_lbl.pack(side="left", padx=2)
        ctk.CTkButton(
            self.source_info_frame, text="Open", width=52, height=24,
            command=lambda: self.open_in_explorer(self.manager.source_dir),
            fg_color=TOKENS["bg_surface"], hover_color=TOKENS["bg_hover"],
            text_color=TOKENS["text_secondary"], border_width=1, border_color=TOKENS["border_subtle"],
            font=self._font(size=11), corner_radius=6
        ).pack(side="right")

        # GDrive Tab
        gdrive_tab = self.tabs.tab("GDrive")
        self.gdrive_entry = ctk.CTkEntry(
            gdrive_tab,
            placeholder_text="Paste public folder link or ID",
            fg_color=TOKENS["bg_surface"], border_color=TOKENS["border_strong"], border_width=1,
            text_color=TOKENS["text_primary"], placeholder_text_color=TOKENS["text_muted"],
            corner_radius=8, height=34, font=self._font(size=12)
        )
        self.gdrive_entry.pack(fill="x", pady=(4, 8))
        ctk.CTkButton(
            gdrive_tab, text="Connect GDrive", command=self.connect_gdrive,
            height=34, fg_color=TOKENS["success_primary"], hover_color=TOKENS["success_hover"],
            text_color=TOKENS["text_on_accent"], font=self._font(size=12, weight="bold"),
            corner_radius=8
        ).pack(fill="x")

        # ── DESTINATION ───────────────────────────────────────────────────────
        self._sidebar_divider()
        self._sidebar_section_label("DESTINATION")

        dest_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        dest_frame.pack(fill="x", padx=14, pady=(0, 4))

        ctk.CTkButton(
            dest_frame, text="Select Target Folder", command=self.select_target,
            height=34, fg_color=TOKENS["bg_surface_alt"], hover_color=TOKENS["bg_hover"],
            text_color=TOKENS["text_primary"], border_width=1, border_color=TOKENS["border_strong"],
            font=self._font(size=12, weight="bold"), corner_radius=8
        ).pack(fill="x", pady=(0, 6))

        dst_info = ctk.CTkFrame(dest_frame, fg_color="transparent")
        dst_info.pack(fill="x")
        self.target_lbl = ctk.CTkLabel(
            dst_info,
            text=f"Target: {os.path.basename(self.manager.target_dir)}",
            font=self._font(size=11), text_color=TOKENS["text_secondary"]
        )
        self.target_lbl.pack(side="left", padx=2)
        ctk.CTkButton(
            dst_info, text="Open", width=52, height=24,
            command=lambda: self.open_in_explorer(self.manager.target_dir),
            fg_color=TOKENS["bg_surface_alt"], hover_color=TOKENS["bg_hover"],
            text_color=TOKENS["text_secondary"], border_width=1, border_color=TOKENS["border_subtle"],
            font=self._font(size=11), corner_radius=6
        ).pack(side="right")

        # ── CATEGORIES ────────────────────────────────────────────────────────
        self._sidebar_divider()

        cat_header = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        cat_header.pack(fill="x", padx=16, pady=(0, 6))
        self._sidebar_section_label("CATEGORIES (KEYS 1–9)", parent=cat_header, pack=False).pack(side="left")

        cat_actions = ctk.CTkFrame(cat_header, fg_color="transparent")
        cat_actions.pack(side="right")

        ctk.CTkButton(
            cat_actions, text="+ New", width=48, height=24,
            fg_color=TOKENS["accent_soft"], hover_color=TOKENS["bg_hover"],
            text_color=TOKENS["accent_text"], font=self._font(size=11, weight="bold"),
            corner_radius=6, command=self.prompt_new_category
        ).pack(side="left", padx=(0, 4))

        self.btn_toggle_cat = ctk.CTkButton(
            cat_actions, text="▾", width=26, height=24,
            fg_color="transparent", hover_color=TOKENS["bg_hover"],
            text_color=TOKENS["text_secondary"], corner_radius=6,
            command=self.toggle_categories
        )
        self.btn_toggle_cat.pack(side="left")

        self.category_scroll = ctk.CTkScrollableFrame(
            self.sidebar,
            fg_color="transparent",
            scrollbar_button_color=TOKENS["border_strong"],
            scrollbar_button_hover_color=TOKENS["text_muted"],
            label_text=""
        )
        self.category_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.create_category_buttons()

        # Bottom Refresh
        self._sidebar_divider()
        ctk.CTkButton(
            self.sidebar, text="↺  Refresh Workspace", command=self.refresh_app,
            height=34, fg_color="transparent", hover_color=TOKENS["bg_hover"],
            text_color=TOKENS["text_secondary"], border_width=1, border_color=TOKENS["border_strong"],
            font=self._font(size=12), corner_radius=8
        ).pack(padx=16, pady=(4, 16), fill="x")

        self.paned.add(self.sidebar)

        # ══════════════════════════════════════════════════════════════════════
        # RIGHT CONTAINER — Main Studio Workspace
        # ══════════════════════════════════════════════════════════════════════
        self.right_container = ctk.CTkFrame(self.paned, fg_color=TOKENS["bg_app"], corner_radius=0)
        self.paned.add(self.right_container)

        # ── Top Studio Bar ────────────────────────────────────────────────────
        self.topbar = ctk.CTkFrame(
            self.right_container, height=52, corner_radius=0,
            fg_color=TOKENS["bg_sidebar"],
            border_width=0
        )
        self.topbar.pack(fill="x", side="top")
        self.topbar.pack_propagate(False)

        # Subtle bottom border for topbar
        ctk.CTkFrame(self.right_container, height=1, fg_color=TOKENS["border_subtle"]).pack(fill="x", side="top")

        self.btn_toggle_sidebar = ctk.CTkButton(
            self.topbar, text="◧", width=34, height=32,
            fg_color=TOKENS["bg_surface_alt"], hover_color=TOKENS["bg_hover"],
            text_color=TOKENS["text_primary"], border_width=1, border_color=TOKENS["border_subtle"],
            corner_radius=8, font=self._font(size=14),
            command=self.toggle_sidebar
        )
        self.btn_toggle_sidebar.pack(side="left", padx=(14, 10))

        self.mode_badge = ctk.CTkLabel(
            self.topbar, text="LOCAL",
            fg_color=TOKENS["accent_soft"], text_color=TOKENS["accent_text"],
            corner_radius=6, padx=8, height=24,
            font=self._font(size=10, weight="bold", family="Consolas")
        )
        self.mode_badge.pack(side="left", padx=(0, 8))

        self.media_type_badge = ctk.CTkLabel(
            self.topbar, text="IDLE",
            fg_color=TOKENS["bg_surface_alt"], text_color=TOKENS["text_secondary"],
            corner_radius=6, padx=8, height=24,
            font=self._font(size=10, weight="bold", family="Consolas")
        )
        self.media_type_badge.pack(side="left", padx=(0, 10))

        self.filename_label = ctk.CTkLabel(
            self.topbar, text="No media loaded",
            font=self._font(size=13, weight="bold"),
            text_color=TOKENS["text_primary"]
        )
        self.filename_label.pack(side="left")

        self.media_meta_label = ctk.CTkLabel(
            self.topbar, text="",
            font=self._font(size=11, family="Consolas"),
            text_color=TOKENS["text_muted"]
        )
        self.media_meta_label.pack(side="left", padx=(10, 0))

        # Topbar Right Actions
        self.btn_theme = ctk.CTkButton(
            self.topbar, text="Light", width=60, height=30,
            fg_color=TOKENS["bg_surface_alt"], hover_color=TOKENS["bg_hover"],
            text_color=TOKENS["text_secondary"], border_width=1, border_color=TOKENS["border_subtle"],
            corner_radius=8, font=self._font(size=11, weight="bold"),
            command=self.toggle_theme
        )
        self.btn_theme.pack(side="right", padx=(6, 14))

        ctk.CTkButton(
            self.topbar, text="?", width=30, height=30,
            fg_color=TOKENS["bg_surface_alt"], hover_color=TOKENS["bg_hover"],
            text_color=TOKENS["text_secondary"], border_width=1, border_color=TOKENS["border_subtle"],
            corner_radius=8, font=self._font(size=12, weight="bold"),
            command=self.show_shortcuts_dialog
        ).pack(side="right", padx=4)

        self.btn_playlist = ctk.CTkButton(
            self.topbar, text="Queue", width=68, height=30,
            command=self.toggle_media_list,
            fg_color=TOKENS["bg_surface_alt"], hover_color=TOKENS["bg_hover"],
            text_color=TOKENS["text_primary"], border_width=1, border_color=TOKENS["border_subtle"],
            corner_radius=8, font=self._font(size=11, weight="bold")
        )
        self.btn_playlist.pack(side="right", padx=4)

        # ── Footer / Action Bar ───────────────────────────────────────────────
        self.footer = ctk.CTkFrame(
            self.right_container,
            height=74,
            corner_radius=12,
            fg_color=TOKENS["bg_surface"],
            border_width=1,
            border_color=TOKENS["border_subtle"]
        )
        self.footer.pack(fill="x", side="bottom", padx=16, pady=(0, 14))
        self.footer.pack_propagate(False)

        # ── Main Content Stage ────────────────────────────────────────────────
        self.main_content = ctk.CTkFrame(self.right_container, fg_color="transparent")
        self.main_content.pack(fill="both", expand=True, side="top", padx=16, pady=(12, 8))

        self.image_container = ctk.CTkFrame(
            self.main_content,
            fg_color=TOKENS["bg_canvas"],
            corner_radius=14,
            border_width=1,
            border_color=TOKENS["border_subtle"]
        )
        self.image_container.pack(fill="both", expand=True)
        self.image_container.update()

        self.image_label = ctk.CTkLabel(
            self.image_container,
            text="Select a source folder to start labeling.",
            font=self._font(size=14),
            text_color=TOKENS["text_secondary"]
        )
        self.image_label.pack(fill="both", expand=True, padx=16, pady=16)

        # Video Controls (hidden by default; shown only for videos)
        self.video_ctrls = ctk.CTkFrame(
            self.main_content, fg_color=TOKENS["bg_surface"],
            corner_radius=10, border_width=1, border_color=TOKENS["border_subtle"],
            height=44
        )
        self.video_slider = ctk.CTkSlider(
            self.video_ctrls,
            from_=0, to=100,
            command=self.on_slider_move,
            button_color=TOKENS["accent_primary"],
            button_hover_color=TOKENS["accent_hover"],
            progress_color=TOKENS["accent_primary"],
            fg_color=TOKENS["border_strong"],
        )
        self.video_slider.pack(fill="x", side="left", expand=True, padx=(12, 10), pady=10)
        self.video_slider.set(0)

        self.btn_play_pause = ctk.CTkButton(
            self.video_ctrls, text="⏸", width=40, height=28,
            command=self.toggle_pause,
            fg_color=TOKENS["bg_surface_alt"], hover_color=TOKENS["bg_hover"],
            text_color=TOKENS["text_primary"], border_width=1, border_color=TOKENS["border_subtle"],
            corner_radius=6
        )
        self.btn_play_pause.pack(side="right", padx=(0, 8), pady=6)

        # Thin Loading Progress Bar
        self.loading_progress = ctk.CTkProgressBar(
            self.main_content,
            progress_color=TOKENS["accent_primary"],
            fg_color=TOKENS["border_subtle"],
            corner_radius=3,
            height=4,
        )
        self.loading_progress.pack(fill="x", pady=(8, 0))
        self.loading_progress.set(0)

        # Playlist Drawer (collapsed initially)
        self.media_list_container = ctk.CTkScrollableFrame(
            self.right_container, height=180,
            label_text="Media Queue",
            fg_color=TOKENS["bg_surface"],
            label_fg_color=TOKENS["bg_surface_alt"],
            label_text_color=TOKENS["text_primary"],
            border_width=1,
            border_color=TOKENS["border_subtle"],
            scrollbar_button_color=TOKENS["border_strong"],
            scrollbar_button_hover_color=TOKENS["text_muted"],
        )

        # ── Footer Controls ───────────────────────────────────────────────────
        self.nav_container = ctk.CTkFrame(self.footer, fg_color="transparent")
        self.nav_container.pack(fill="both", expand=True, padx=14, pady=10)

        self.btn_back = ctk.CTkButton(
            self.nav_container, text="←  Back", command=self.on_back,
            width=118, height=40,
            fg_color=TOKENS["bg_surface_alt"], hover_color=TOKENS["bg_hover"],
            text_color=TOKENS["text_primary"], border_width=1, border_color=TOKENS["border_strong"],
            font=self._font(size=13, weight="bold"),
            corner_radius=9
        )
        self.btn_back.pack(side="left")

        center_cluster = ctk.CTkFrame(self.nav_container, fg_color="transparent")
        center_cluster.pack(side="left", expand=True)

        self.stats_label = ctk.CTkLabel(
            center_cluster, text="0 / 0 Files",
            font=self._font(size=14, weight="bold", family="Consolas"),
            text_color=TOKENS["text_primary"]
        )
        self.stats_label.pack(side="left", padx=(0, 12))

        self.btn_undo = ctk.CTkButton(
            center_cluster, text="↺ Undo", command=self.on_undo,
            width=82, height=32,
            fg_color=TOKENS["bg_surface_alt"], hover_color=TOKENS["bg_hover"],
            text_color=TOKENS["text_secondary"], border_width=1, border_color=TOKENS["border_subtle"],
            font=self._font(size=11, weight="bold"),
            corner_radius=8,
            state="disabled"
        )
        self.btn_undo.pack(side="left")

        self.btn_next = ctk.CTkButton(
            self.nav_container, text="Skip  →", command=self.on_next,
            width=118, height=40,
            fg_color=TOKENS["bg_surface_alt"], hover_color=TOKENS["bg_hover"],
            text_color=TOKENS["text_primary"], border_width=1, border_color=TOKENS["border_strong"],
            font=self._font(size=13, weight="bold"),
            corner_radius=9
        )
        self.btn_next.pack(side="right")

    # ── Theme & Dialogs ───────────────────────────────────────────────────────

    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        mode = "Dark" if self.is_dark_mode else "Light"
        ctk.set_appearance_mode(mode)
        self.btn_theme.configure(text="Light" if self.is_dark_mode else "Dark")
        self.paned.configure(bg=PALETTE["zinc_800"] if self.is_dark_mode else PALETTE["zinc_200"])

    def show_shortcuts_dialog(self):
        messagebox.showinfo(
            "Keyboard Shortcuts",
            "1 – 9 : Classify current media into category 1–9\n"
            "← / → : Previous / Skip media\n"
            "Space : Play / Pause video\n"
            "Ctrl + Z : Undo last local classification"
        )

    def prompt_new_category(self):
        dialog = ctk.CTkInputDialog(
            text="Enter new category folder name:",
            title="New Category"
        )
        name = dialog.get_input()
        if name:
            ok, res = self.manager.create_category(name)
            if ok:
                self.create_category_buttons()
            else:
                messagebox.showerror("Cannot Create Category", res)

    # ── UI Logic ──────────────────────────────────────────────────────────────

    def connect_gdrive(self):
        url = self.gdrive_entry.get().strip()
        if not url:
            return

        confirm = messagebox.askokcancel(
            "GDrive Connection",
            "Connecting to Google Drive may take a moment. The app will access the public folder and prepare the file list. Continue?"
        )
        if not confirm:
            return

        self.image_label.configure(image=None, text="Connecting to Google Drive…")

        def task():
            success, msg = self.manager.fetch_gdrive_files(url)
            self.after(0, lambda: self.finish_connect(success, msg))

        Thread(target=task, daemon=True).start()

    def finish_connect(self, success, msg):
        if success:
            self.mode_badge.configure(text="GDRIVE")
            messagebox.showinfo("Connected", msg)
            self.refresh_app()
        else:
            messagebox.showerror("Connection Failed", msg)
            self.image_label.configure(text="Connection failed. Check the folder link and try again.")

    def select_source(self):
        folder = filedialog.askdirectory()
        if folder:
            self.manager.is_cloud_mode = False
            self.manager.source_dir = folder
            self.mode_badge.configure(text="LOCAL")
            self.source_lbl.configure(text=f"Folder: {os.path.basename(folder)}")
            self.refresh_app()

    def select_target(self):
        folder = filedialog.askdirectory()
        if folder:
            self.manager.target_dir = folder
            self.target_lbl.configure(text=f"Target: {os.path.basename(folder)}")
            self.refresh_app()

    def open_in_explorer(self, path):
        if os.path.exists(path):
            os.startfile(path)

    def toggle_sidebar(self):
        self.sidebar_visible = not self.sidebar_visible
        if self.sidebar_visible:
            self.paned.add(self.sidebar, before=self.right_container)
            self.btn_toggle_sidebar.configure(text="◧")
        else:
            self.paned.forget(self.sidebar)
            self.btn_toggle_sidebar.configure(text="▸")

    def toggle_categories(self):
        self.cats_visible = not self.cats_visible
        if self.cats_visible:
            self.category_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 8))
            self.btn_toggle_cat.configure(text="▾")
        else:
            self.category_scroll.pack_forget()
            self.btn_toggle_cat.configure(text="▴")

    def is_video_file(self, filename):
        return filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))

    def create_category_buttons(self):
        for widget in self.category_scroll.winfo_children():
            widget.destroy()

        if not self.manager.categories:
            ctk.CTkLabel(
                self.category_scroll,
                text="No category folders yet.\nClick '+ New' above to create one.",
                font=self._font(size=12),
                text_color=TOKENS["text_muted"],
                justify="center"
            ).pack(pady=24)
            return

        for idx, category in enumerate(self.manager.categories):
            count = self.manager.category_counts.get(category, 0)
            key_hint = f"[{idx + 1}] " if idx < 9 else ""
            row_frame = ctk.CTkFrame(self.category_scroll, fg_color="transparent")
            row_frame.pack(fill="x", pady=3, padx=4)

            btn = ctk.CTkButton(
                row_frame,
                text=f"{key_hint}{category}",
                anchor="w",
                height=42,
                command=lambda c=category: self.on_classify(c),
                fg_color=TOKENS["bg_surface_alt"],
                hover_color=TOKENS["accent_primary"],
                text_color=TOKENS["text_primary"],
                font=self._font(size=12, weight="bold"),
                corner_radius=9,
                border_width=1,
                border_color=TOKENS["border_subtle"],
            )
            btn.pack(side="left", fill="x", expand=True)

            ctk.CTkLabel(
                row_frame,
                text=str(count),
                width=34, height=26,
                fg_color=TOKENS["bg_app"],
                text_color=TOKENS["text_secondary"],
                corner_radius=6,
                font=self._font(size=11, weight="bold", family="Consolas")
            ).pack(side="right", padx=(6, 0))

    def _update_undo_button(self):
        if self.manager.undo_stack and not self.manager.is_cloud_mode:
            self.btn_undo.configure(state="normal", text_color=TOKENS["text_primary"])
        else:
            self.btn_undo.configure(state="disabled", text_color=TOKENS["text_muted"])

    def load_current_media(self):
        self.stop_video()
        self._update_undo_button()
        if self.media_list_visible:
            self.update_media_list()

        path_id, is_cloud, name = self.manager.get_current_image_data()
        total = len(self.manager.images)
        current = self.manager.current_index + 1 if total > 0 else 0
        self.stats_label.configure(text=f"{current} / {total} Files")

        if path_id:
            self.loading_progress.set(0.35)

            def task():
                try:
                    if is_cloud:
                        thumb_url = f"https://drive.google.com/thumbnail?id={path_id}&sz=w1000"
                        response = requests.get(thumb_url, timeout=10)
                        img_data = ImageOps.exif_transpose(Image.open(io.BytesIO(response.content)))
                        self.after(0, lambda: self.display_image(img_data, name))
                    else:
                        if self.is_video_file(path_id):
                            if not HAS_FFMPEG:
                                self.after(0, lambda: messagebox.showwarning(
                                    "Missing Dependency",
                                    "Please install imageio-ffmpeg: pip install imageio-ffmpeg"
                                ))
                            self.after(0, lambda: self.start_video_playback(path_id, name))
                        else:
                            with Image.open(path_id) as img_temp:
                                img_data = ImageOps.exif_transpose(img_temp.copy())
                            self.after(0, lambda: self.display_image(img_data, name))
                except Exception as e:
                    self.after(0, lambda err=e: self.image_label.configure(image=None, text=f"Error loading media: {err}"))

            Thread(target=task, daemon=True).start()
        else:
            self._set_video_controls_visible(False)
            self.media_type_badge.configure(text="DONE")
            self.filename_label.configure(text="Queue empty")
            self.media_meta_label.configure(text="")
            self.image_label.configure(
                image=None,
                text="All media in this queue has been labeled.\nSelect another folder or click Refresh."
            )
            self.loading_progress.set(0)

    def on_slider_move(self, value):
        if not self.video_playing or not self.current_video_cap:
            return
        target_frame = int((value / 100) * self.total_frames)
        with self.cap_lock:
            self.current_video_cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            self.video_start_time = time.time() - (target_frame / self.fps)
            self.current_frame_idx = target_frame
            self.frame_queue.clear()

    def toggle_media_list(self):
        self.media_list_visible = not self.media_list_visible
        if self.media_list_visible:
            self.media_list_container.pack(fill="x", padx=16, pady=(0, 8), before=self.footer)
            self.btn_playlist.configure(fg_color=TOKENS["accent_soft"], text_color=TOKENS["accent_text"])
            self.update_media_list()
        else:
            self.media_list_container.pack_forget()
            self.btn_playlist.configure(fg_color=TOKENS["bg_surface_alt"], text_color=TOKENS["text_primary"])

    def update_media_list(self):
        for widget in self.media_list_container.winfo_children():
            widget.destroy()

        if not self.manager.images:
            ctk.CTkLabel(
                self.media_list_container,
                text="Queue is empty",
                font=self._font(size=11),
                text_color=TOKENS["text_muted"]
            ).pack(pady=12)
            return

        for i, (fname, _, _) in enumerate(self.manager.images):
            is_current = (i == self.manager.current_index)
            bg_color = TOKENS["accent_primary"] if is_current else "transparent"
            txt_color = TOKENS["text_on_accent"] if is_current else TOKENS["text_primary"]
            btn = ctk.CTkButton(
                self.media_list_container,
                text=f"{i + 1:02d}.  {fname}",
                anchor="w",
                height=30,
                fg_color=bg_color,
                hover_color=TOKENS["bg_hover"],
                text_color=txt_color,
                font=self._font(size=11, weight="bold" if is_current else "normal"),
                corner_radius=6,
                command=lambda idx=i: self.jump_to_media(idx)
            )
            btn.pack(fill="x", pady=1, padx=4)

    def jump_to_media(self, index):
        self.manager.current_index = index
        self.load_current_media()
        self.update_media_list()

    def toggle_pause(self):
        if not self.video_playing:
            return
        self.video_paused = not self.video_paused
        if self.video_paused:
            self.pause_start_time = time.time()
            self.btn_play_pause.configure(text="▶")
            winsound.PlaySound(None, winsound.SND_PURGE)
        else:
            self.btn_play_pause.configure(text="⏸")
            drift = time.time() - self.pause_start_time
            self.video_start_time += drift
            if self.temp_audio_file:
                winsound.PlaySound(self.temp_audio_file, winsound.SND_ASYNC | winsound.SND_LOOP)
            self.play_video_frame()

    def start_video_playback(self, path, name):
        self.stop_video()
        self._set_video_controls_visible(True)

        self.current_video_cap = cv2.VideoCapture(path)
        self.fps = self.current_video_cap.get(cv2.CAP_PROP_FPS) or 30
        self.total_frames = int(self.current_video_cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.video_playing = True
        self.video_paused = False
        self.btn_play_pause.configure(text="⏸")
        self.media_type_badge.configure(text="VIDEO")
        self.filename_label.configure(text=name)
        self.media_meta_label.configure(text=f"{int(self.fps)} fps")
        self.loading_progress.set(1)
        self.frame_queue.clear()

        ret, frame = self.current_video_cap.read()
        if ret:
            fh, fw, _ = frame.shape
            cw = max(self.image_container.winfo_width() - 32, 640)
            ch = max(self.image_container.winfo_height() - 32, 360)
            ratio = min(cw / fw, ch / fh)
            self.vid_size = (max(1, int(fw * ratio)), max(1, int(fh * ratio)))
            self.media_meta_label.configure(text=f"{fw}×{fh} · {int(self.fps)} fps")
            self.current_video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        else:
            self.vid_size = (800, 500)

        if HAS_FFMPEG:
            def extract_and_play():
                try:
                    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                    temp_dir = tempfile.gettempdir()
                    self.temp_audio_file = os.path.join(temp_dir, f"label_audio_{int(time.time())}.wav")

                    cmd = [
                        ffmpeg_exe, "-y", "-i", path, "-vn",
                        "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
                        self.temp_audio_file
                    ]
                    subprocess.run(cmd, capture_output=True, check=True)

                    if self.video_playing:
                        winsound.PlaySound(self.temp_audio_file, winsound.SND_ASYNC | winsound.SND_LOOP)
                        self.video_start_time = time.time()
                        self.current_frame_idx = 0
                        self.after(0, self.play_video_frame)
                except Exception as e:
                    print(f"Audio Error: {e}")
                    self.video_start_time = time.time()
                    self.after(0, self.play_video_frame)

            Thread(target=extract_and_play, daemon=True).start()
        else:
            self.video_start_time = time.time()
            self.play_video_frame()

        def reader():
            while self.video_playing:
                if self.video_paused:
                    time.sleep(0.1)
                    continue

                with self.cap_lock:
                    if not self.current_video_cap:
                        break

                    if self.video_start_time > 0:
                        elapsed = time.time() - self.video_start_time
                        target_frame = int(elapsed * self.fps)
                        current_cap_frame = self.current_video_cap.get(cv2.CAP_PROP_POS_FRAMES)

                        if abs(target_frame - current_cap_frame) > 60 and self.total_frames > 0:
                            self.current_video_cap.set(
                                cv2.CAP_PROP_POS_FRAMES, target_frame % self.total_frames
                            )

                    ret, frame = self.current_video_cap.read()

                if not ret:
                    self.video_playing = False
                    self.after(0, self.stop_video)
                    self.after(0, lambda: self.btn_play_pause.configure(text="▶"))
                    break

                frame = cv2.resize(frame, self.vid_size, interpolation=cv2.INTER_NEAREST)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame)

                self.frame_queue.append(img)
                time.sleep(max(0.001, 1 / self.fps * 0.4))

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

        if self.total_frames > 0:
            progress = (min(self.current_frame_idx, self.total_frames) / self.total_frames) * 100
            self.video_slider.set(progress)

        while len(self.frame_queue) > 1 and self.current_frame_idx < target_frame:
            self.frame_queue.popleft()
            self.current_frame_idx += 1

        if self.frame_queue:
            img_data = self.frame_queue.popleft()
            self.current_frame_idx = max(self.current_frame_idx + 1, target_frame)

            self.tk_img = ImageTk.PhotoImage(img_data)
            self.image_label._label.configure(image=self.tk_img)
            self.image_label._label.image = self.tk_img

        next_target_time = (self.current_frame_idx + 1) / self.fps
        current_elapsed = time.time() - self.video_start_time
        delay = int(max(1, (next_target_time - current_elapsed) * 1000))

        self.after(delay, self.play_video_frame)

    def display_image(self, img_data, name):
        self._set_video_controls_visible(False)
        w, h = img_data.size
        try:
            cw = max(self.image_container.winfo_width() - 32, 640)
            ch = max(self.image_container.winfo_height() - 32, 360)
        except Exception:
            cw, ch = 800, 500

        ratio = min(cw / w, ch / h)
        new_size = (max(1, int(w * ratio)), max(1, int(h * ratio)))

        self.media_type_badge.configure(text="IMAGE")
        self.filename_label.configure(text=name)
        self.media_meta_label.configure(text=f"{w}×{h}")
        img_ctk = ctk.CTkImage(light_image=img_data, dark_image=img_data, size=new_size)
        self.image_label.configure(image=img_ctk, text="")
        self.loading_progress.set(1)

    def refresh_app(self):
        self.manager.refresh_state()
        self.create_category_buttons()
        self.load_current_media()

    def on_classify(self, category):
        self.image_label.configure(image=None, text=f"Moving to '{category}'…")

        def task():
            success, msg = self.manager.move_or_download_to_category(category)
            self.after(0, lambda: self.finish_action(success, msg))

        Thread(target=task, daemon=True).start()

    def finish_action(self, success, msg):
        if not success:
            messagebox.showerror("Error", f"Failed to move file:\n{msg}")
        self.create_category_buttons()
        self.load_current_media()

    def on_undo(self):
        if self.manager.is_cloud_mode:
            return
        ok, msg = self.manager.undo_last_move()
        if ok:
            self.create_category_buttons()
            self.load_current_media()
        else:
            messagebox.showinfo("Undo", msg)

    def on_next(self):
        if self.manager.next_image():
            self.load_current_media()
        else:
            messagebox.showinfo("End of Queue", "No more media files to label.")

    def on_back(self):
        if self.manager.prev_image():
            self.load_current_media()
        else:
            messagebox.showinfo("Start of Queue", "This is already the first file.")


if __name__ == "__main__":
    app = DataLabelerApp()
    app.mainloop()
