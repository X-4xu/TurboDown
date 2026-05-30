import os
import sys
import time
import json
import queue
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import pyperclip

# Try importing optional packages
try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

# Import local modules
from downloader import DownloadJob
from video_grabber import get_video_info, download_video_format

# ============================================================
# CONFIG
# ============================================================
APP_NAME = "TurboDown - Download Manager"
APP_VERSION = "3.0.0"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads.json")
DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads")
MAX_SIMULTANEOUS = 8  # Max concurrent downloads
DEFAULT_CONNECTIONS = 32  # Connections per download

# ============================================================
# THEME COLORS (Professional dark look)
# ============================================================
COLORS = {
    "bg_dark": "#ffffff",         # White background for main table
    "bg_medium": "#f1f2f6",       # Light gray for headers
    "bg_light": "#dfe6e9",        # Mid gray for hover
    "accent": "#0984e3",          # Blue accent
    "accent_hover": "#0770c2",
    "green": "#2ed573",           # Bright green for downloads/progress
    "green_hover": "#26af5f",
    "blue": "#0984e3",            # IDM Blue
    "blue_hover": "#0770c2",
    "orange": "#ffa502",          # Orange for paused
    "red": "#ff4757",             # Red for failed
    "red_hover": "#e03d4b",
    "text": "#2f3542",            # Dark gray/black for text (extremely readable)
    "text_dim": "#747d8c",        # Soft gray for subtext
    "row_hover": "#e3f2fd",       # Light blue row hover (IDM style)
    "row_selected": "#b3e5fc",    # Blue selected row (IDM style)
    "toolbar_bg": "#f1f2f6",      # Light gray toolbar background
    "sidebar_bg": "#f1f2f6",      # Light gray sidebar background
    "progress_bg": "#f1f2f6",      # Background of progress bar
    "progress_fill": "#2ed573",    # Green progress bar (IDM style)
    "completed": "#2ed573",
    "downloading": "#0984e3",
    "paused": "#ffa502",
    "failed": "#ff4757",
    "queued": "#747d8c",
}



def create_tray_image():
    """Create a 64x64 tray icon with a download arrow."""
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    # Background circle
    dc.ellipse([2, 2, 62, 62], fill=(9, 132, 227, 255))
    # Arrow body
    dc.rectangle([26, 14, 38, 38], fill=(255, 255, 255, 255))
    # Arrow head
    dc.polygon([(16, 38), (48, 38), (32, 52)], fill=(255, 255, 255, 255))
    return image


class TurboDownApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # ---- Theme ----
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        # ---- Window Setup ----
        self.title(APP_NAME)
        self.geometry("1100x650")
        self.minsize(950, 550)

        # ---- State ----
        self.downloads = {}       # id -> download_dict
        self.active_jobs = {}     # id -> DownloadJob or YtJob
        self.selected_download_id = None
        self.current_category = "All"
        self.global_speed_limit = None
        self.row_widgets = {}
        self.max_simultaneous = MAX_SIMULTANEOUS
        self.default_connections = DEFAULT_CONNECTIONS

        # ---- Queues ----
        self.browser_queue = queue.Queue()
        self.youtube_queue = queue.Queue()
        self.clipboard_queue = queue.Queue()

        # ---- Flags ----
        self.clipboard_monitor_active = tk.BooleanVar(value=True)
        self.last_clipboard_url = ""
        self.last_scheduler_check = 0
        self._destroying = False

        # ---- Window close -> tray ----
        self.protocol("WM_DELETE_WINDOW", self.hide_window)

        # ---- Load data ----
        self.load_database()

        # ---- Build UI ----
        self.setup_ui()

        # ---- Start services ----
        self.start_integration_server()
        self.start_clipboard_monitor()
        if HAS_TRAY:
            self.setup_tray()

        # ---- Periodic update ----
        self.update_loop()

    # ============================================================
    # DATABASE
    # ============================================================
    def load_database(self):
        if os.path.exists(DB_PATH):
            try:
                with open(DB_PATH, 'r', encoding='utf-8') as f:
                    self.downloads = json.load(f)
                for dl_id, dl in self.downloads.items():
                    if dl.get("status") in ("Downloading", "Queued"):
                        dl["status"] = "Paused"
                        dl["speed"] = "0 KB/s"
            except Exception as e:
                print(f"Error loading DB: {e}")
                self.downloads = {}
        else:
            self.downloads = {}

    def save_database(self):
        try:
            with open(DB_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.downloads, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving DB: {e}")

    # ============================================================
    # UI SETUP
    # ============================================================
    def setup_ui(self):
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # ---- Menu Bar ----
        self.setup_menubar()

        # ---- Toolbar ----
        self.setup_toolbar()

        # ---- Sidebar ----
        self.setup_sidebar()

        # ---- Main Table ----
        self.setup_table()

        # ---- Status Bar ----
        self.setup_statusbar()

        # ---- Initial category ----
        self.select_category("All")

    def setup_menubar(self):
        """Create professional menu bar."""
        self.menu_bar = tk.Menu(self, bg="#ffffff", fg="#2f3542",
                                activebackground="#0984e3", activeforeground="white")

        # Tasks menu
        tasks_menu = tk.Menu(self.menu_bar, tearoff=0, bg="#ffffff", fg="#2f3542",
                              activebackground="#0984e3", activeforeground="white")
        tasks_menu.add_command(label="Add New Download (إضافة رابط)    Ctrl+N", command=self.show_add_url_dialog)
        tasks_menu.add_command(label="Add YouTube Download (يوتيوب)    Ctrl+Y", command=self.show_youtube_dialog)
        tasks_menu.add_command(label="Batch Download from File (تحميل دفعي)", command=self.show_batch_import_dialog)
        tasks_menu.add_separator()
        tasks_menu.add_command(label="Resume All (استئناف الكل)", command=self.resume_all)
        tasks_menu.add_command(label="Pause All (إيقاف الكل)", command=self.pause_all)
        tasks_menu.add_separator()
        tasks_menu.add_command(label="Exit (خروج)", command=self.quit_application)
        self.menu_bar.add_cascade(label="Tasks", menu=tasks_menu)

        # Downloads menu
        dl_menu = tk.Menu(self.menu_bar, tearoff=0, bg="#ffffff", fg="#2f3542",
                           activebackground="#0984e3", activeforeground="white")
        dl_menu.add_command(label="Resume (استئناف)", command=self.resume_selected)
        dl_menu.add_command(label="Pause (إيقاف)", command=self.pause_selected)
        dl_menu.add_command(label="Delete (حذف)", command=self.delete_selected)
        dl_menu.add_separator()
        dl_menu.add_command(label="Open File (فتح)", command=lambda: self.open_downloaded_file(self.selected_download_id) if self.selected_download_id else None)
        dl_menu.add_command(label="Open Folder (فتح المجلد)", command=self.open_containing_folder)
        dl_menu.add_separator()
        dl_menu.add_command(label="Copy URL (نسخ الرابط)", command=self.copy_url)
        dl_menu.add_command(label="Schedule (جدولة)", command=self.show_schedule_dialog)
        self.menu_bar.add_cascade(label="Downloads", menu=dl_menu)

        # Options menu
        opt_menu = tk.Menu(self.menu_bar, tearoff=0, bg="#ffffff", fg="#2f3542",
                            activebackground="#0984e3", activeforeground="white")
        opt_menu.add_command(label="Settings (إعدادات)", command=self.show_settings_dialog)
        opt_menu.add_command(label="Clear Finished (حذف المكتمل)", command=self.clear_finished)
        self.menu_bar.add_cascade(label="Options", menu=opt_menu)

        # Help menu
        help_menu = tk.Menu(self.menu_bar, tearoff=0, bg="#ffffff", fg="#2f3542",
                             activebackground="#0984e3", activeforeground="white")
        help_menu.add_command(label=f"About {APP_NAME}", command=self.show_about)
        self.menu_bar.add_cascade(label="Help", menu=help_menu)

        self.configure(menu=self.menu_bar)

        # Keyboard shortcuts
        self.bind("<Control-n>", lambda e: self.show_add_url_dialog())
        self.bind("<Control-N>", lambda e: self.show_add_url_dialog())
        self.bind("<Control-y>", lambda e: self.show_youtube_dialog())
        self.bind("<Control-Y>", lambda e: self.show_youtube_dialog())
        self.bind("<Delete>", lambda e: self.delete_selected())

    def setup_toolbar(self):
        """Create toolbar with all action buttons."""
        self.toolbar = ctk.CTkFrame(self, height=55, corner_radius=0,
                                     fg_color=COLORS["toolbar_bg"])
        self.toolbar.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.toolbar.grid_propagate(False)

        buttons = [
            ("➕ Add URL\nإضافة رابط", COLORS["blue"], COLORS["blue_hover"], self.show_add_url_dialog),
            ("▶ YouTube\nيوتيوب", "#c4302b", "#a8221d", self.show_youtube_dialog),
            ("📁 Batch\nتحميل دفعي", COLORS["green"], COLORS["green_hover"], self.show_batch_import_dialog),
            (None, None, None, None),  # separator
            ("▶ Resume\nاستئناف", COLORS["blue"], COLORS["blue_hover"], self.resume_selected),
            ("⏸ Pause\nإيقاف", COLORS["orange"], "#e6b85e", self.pause_selected),
            ("▶▶ Resume All\nاستئناف الكل", COLORS["green"], COLORS["green_hover"], self.resume_all),
            ("⏸⏸ Pause All\nإيقاف الكل", "#e17055", "#c0563d", self.pause_all),
            (None, None, None, None),  # separator
            ("📅 Schedule\nجدولة", "#a29bfe", "#8c7ae6", self.show_schedule_dialog),
            ("🗑 Delete\nحذف", COLORS["red"], COLORS["red_hover"], self.delete_selected),
            ("🧹 Clear Done\nحذف المكتمل", "#636e72", "#4a5459", self.clear_finished),
        ]

        for item in buttons:
            text, fg, hover, cmd = item
            if text is None:
                # Separator
                sep = ctk.CTkFrame(self.toolbar, width=2, height=35, fg_color="#2d3436")
                sep.pack(side="left", padx=6, pady=8)
                continue

            btn = ctk.CTkButton(
                self.toolbar, text=text, width=90, height=45,
                fg_color=fg, hover_color=hover,
                font=ctk.CTkFont(size=11, weight="bold"),
                command=cmd,
                corner_radius=6
            )
            btn.pack(side="left", padx=3, pady=5)

    def setup_sidebar(self):
        """Create category sidebar."""
        self.sidebar = ctk.CTkFrame(self, width=175, corner_radius=0,
                                     fg_color=COLORS["sidebar_bg"])
        self.sidebar.grid(row=1, column=0, rowspan=2, sticky="nsew", pady=(0, 0))
        self.sidebar.grid_propagate(False)

        # Logo area
        logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo_frame.pack(fill="x", padx=10, pady=(15, 5))

        logo_label = ctk.CTkLabel(logo_frame, text="⬇ TurboDown",
                                   font=ctk.CTkFont(size=18, weight="bold"),
                                   text_color=COLORS["blue"])
        logo_label.pack()

        version_label = ctk.CTkLabel(logo_frame, text=f"v{APP_VERSION}",
                                      font=ctk.CTkFont(size=10),
                                      text_color=COLORS["text_dim"])
        version_label.pack()

        # Divider
        div = ctk.CTkFrame(self.sidebar, height=1, fg_color="#2d3436")
        div.pack(fill="x", padx=15, pady=10)

        # Category title
        cat_title = ctk.CTkLabel(self.sidebar, text="📂 Categories",
                                  font=ctk.CTkFont(size=13, weight="bold"),
                                  text_color=COLORS["text"])
        cat_title.pack(padx=15, pady=(5, 10), anchor="w")

        categories = [
            ("📋 All Downloads", "All"),
            ("⏳ Unfinished", "Unfinished"),
            ("✅ Finished", "Finished"),
            ("─────────────", None),
            ("💿 Programs", "Programs"),
            ("🎬 Video", "Video"),
            ("📦 Compressed", "Compressed"),
            ("📄 Documents", "Documents"),
            ("🎵 Music", "Music"),
            ("📁 Other", "Other"),
        ]

        self.category_buttons = {}
        for text, cat_id in categories:
            if cat_id is None:
                sep = ctk.CTkLabel(self.sidebar, text=text, font=ctk.CTkFont(size=9),
                                    text_color="#2d3436")
                sep.pack(fill="x", padx=15, pady=2)
                continue

            btn = ctk.CTkButton(
                self.sidebar, text=text, anchor="w", height=30,
                fg_color="transparent",
                text_color=COLORS["text"],
                hover_color=COLORS["row_hover"],
                font=ctk.CTkFont(size=12),
                command=lambda c=cat_id: self.select_category(c),
                corner_radius=4
            )
            btn.pack(fill="x", padx=8, pady=1)
            self.category_buttons[cat_id] = btn

    def setup_table(self):
        """Create download table."""
        self.table_container = ctk.CTkFrame(self, corner_radius=0, fg_color=COLORS["bg_dark"])
        self.table_container.grid(row=1, column=1, rowspan=2, sticky="nsew")
        self.table_container.grid_rowconfigure(1, weight=1)
        self.table_container.grid_columnconfigure(0, weight=1)

        # Table header
        self.table_header = ctk.CTkFrame(self.table_container, height=28,
                                          corner_radius=0, fg_color=COLORS["bg_medium"])
        self.table_header.grid(row=0, column=0, sticky="ew")
        self.table_header.grid_propagate(False)

        headers = [
            ("📁 File Name", 0.32),
            ("📊 Size", 0.08),
            ("Progress", 0.22),
            ("⚡ Speed", 0.10),
            ("Status", 0.10),
            ("⏱ ETA", 0.08),
            ("📅 Sched", 0.10),
        ]

        for text, weight in headers:
            lbl = ctk.CTkLabel(self.table_header, text=text,
                                font=ctk.CTkFont(size=11, weight="bold"),
                                text_color="#b2bec3", anchor="w")
            lbl.pack(side="left", fill="x", expand=True, padx=4)

        # Scrollable download list
        self.scroll_frame = ctk.CTkScrollableFrame(self.table_container, corner_radius=0,
                                                    fg_color=COLORS["bg_dark"])
        self.scroll_frame.grid(row=1, column=0, sticky="nsew")

    def setup_statusbar(self):
        """Create status bar with speed limiter."""
        self.status_bar = ctk.CTkFrame(self, height=38, corner_radius=0,
                                        fg_color=COLORS["toolbar_bg"])
        self.status_bar.grid(row=3, column=0, columnspan=2, sticky="nsew")
        self.status_bar.grid_propagate(False)

        # Download counter
        self.lbl_counter = ctk.CTkLabel(self.status_bar, text="Downloads: 0 | Active: 0",
                                         font=ctk.CTkFont(size=11),
                                         text_color=COLORS["text"])
        self.lbl_counter.pack(side="left", padx=15, pady=5)

        # Clipboard toggle
        self.chk_clipboard = ctk.CTkCheckBox(
            self.status_bar, text="📋 Clipboard Monitor",
            variable=self.clipboard_monitor_active,
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text"],
            checkbox_width=18, checkbox_height=18
        )
        self.chk_clipboard.pack(side="left", padx=15, pady=5)

        # Speed limit section (right side)
        self.lbl_limit_val = ctk.CTkLabel(self.status_bar, text="Unlimited",
                                           font=ctk.CTkFont(size=11, weight="bold"),
                                           text_color=COLORS["green"])
        self.lbl_limit_val.pack(side="right", padx=10, pady=5)

        self.slider_limit = ctk.CTkSlider(self.status_bar, from_=50, to=10000,
                                           number_of_steps=200, width=140,
                                           command=self.change_speed_limit,
                                           progress_color=COLORS["blue"],
                                           button_color=COLORS["blue"])
        self.slider_limit.set(1000)
        self.slider_limit.pack(side="right", padx=5, pady=5)
        self.slider_limit.configure(state="disabled")

        self.chk_limit = ctk.CTkCheckBox(
            self.status_bar, text="⚡ Speed Limit",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text"],
            command=self.toggle_speed_limit,
            checkbox_width=18, checkbox_height=18
        )
        self.chk_limit.pack(side="right", padx=10, pady=5)

    # ============================================================
    # CATEGORY SELECTION
    # ============================================================
    def select_category(self, cat_id):
        self.current_category = cat_id
        for c, btn in self.category_buttons.items():
            if c == cat_id:
                btn.configure(fg_color=COLORS["blue"], text_color="white")
            else:
                btn.configure(fg_color="transparent", text_color=COLORS["text"])
        self.refresh_downloads_list()

    def get_category_by_extension(self, filename):
        ext = os.path.splitext(filename)[1].lower()
        cat_map = {
            "Compressed": (".zip", ".rar", ".7z", ".tar", ".gz", ".iso", ".bz2", ".xz"),
            "Programs": (".exe", ".msi", ".apk", ".bat", ".cmd", ".dmg", ".deb", ".rpm", ".app"),
            "Documents": (".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".epub", ".rtf", ".doc", ".xls", ".ppt", ".odt"),
            "Music": (".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".wma"),
            "Video": (".mp4", ".mkv", ".avi", ".webm", ".flv", ".mov", ".3gp", ".wmv", ".m4v", ".ts"),
        }
        for cat, exts in cat_map.items():
            if ext in exts:
                return cat
        return "Other"

    # ============================================================
    # DOWNLOAD LIST (TABLE)
    # ============================================================
    def refresh_downloads_list(self):
        for row in self.row_widgets.values():
            for widget in row.values():
                try:
                    widget.destroy()
                except Exception:
                    pass
        self.row_widgets.clear()

        filtered = []
        for dl_id, dl in self.downloads.items():
            cat = self.current_category
            if cat == "All":
                pass
            elif cat == "Unfinished" and dl["status"] == "Completed":
                continue
            elif cat == "Finished" and dl["status"] != "Completed":
                continue
            elif cat not in ("All", "Unfinished", "Finished") and dl.get("category") != cat:
                continue
            filtered.append((dl_id, dl))

        filtered.sort(key=lambda x: x[1].get("date", 0), reverse=True)

        for dl_id, dl in filtered:
            self.create_row_ui(dl_id, dl)

        active_count = len(self.active_jobs)
        self.lbl_counter.configure(
            text=f"Downloads: {len(self.downloads)} | Active: {active_count} / {self.max_simultaneous}"
        )

    def create_row_ui(self, dl_id, dl):
        row_frame = ctk.CTkFrame(self.scroll_frame, height=34, corner_radius=4,
                                  fg_color="transparent")
        row_frame.pack(fill="x", padx=3, pady=1)
        row_frame.pack_propagate(False)

        # Bind events
        for event_name in ("<Button-1>",):
            row_frame.bind(event_name, lambda e, d=dl_id: self.select_row(d))
        row_frame.bind("<Double-Button-1>", lambda e, d=dl_id: self.open_downloaded_file(d))
        row_frame.bind("<Button-3>", lambda e, d=dl_id: self.show_context_menu(e, d))

        # Status icon
        status = dl.get("status", "Paused")
        icon_map = {"Completed": "✅", "Downloading": "⬇", "Paused": "⏸",
                     "Failed": "❌", "Queued": "⏳"}
        status_icon = icon_map.get(status, "❓")

        # 1. Filename with icon
        name_text = f"{status_icon} {dl['filename']}"
        lbl_name = ctk.CTkLabel(row_frame, text=name_text, font=ctk.CTkFont(size=11),
                                 anchor="w", text_color=COLORS["text"])
        lbl_name.pack(side="left", fill="both", expand=True, padx=5)
        lbl_name.bind("<Button-1>", lambda e, d=dl_id: self.select_row(d))
        lbl_name.bind("<Double-Button-1>", lambda e, d=dl_id: self.open_downloaded_file(d))
        lbl_name.bind("<Button-3>", lambda e, d=dl_id: self.show_context_menu(e, d))

        # 2. Size
        size_bytes = dl.get("size", 0)
        lbl_size = ctk.CTkLabel(row_frame, text=self.format_size(size_bytes),
                                 font=ctk.CTkFont(size=10), width=65, anchor="w",
                                 text_color=COLORS["text_dim"])
        lbl_size.pack(side="left", padx=3)
        lbl_size.bind("<Button-1>", lambda e, d=dl_id: self.select_row(d))

        # 3. Progress bar + percent
        progress_val = 0
        if size_bytes > 0:
            progress_val = min(1.0, dl.get("downloaded", 0) / size_bytes)

        progress_bar = ctk.CTkProgressBar(row_frame, width=140, height=14,
                                           corner_radius=3,
                                           fg_color=COLORS["progress_bg"])
        # Color based on status
        if status == "Completed":
            progress_bar.configure(progress_color=COLORS["completed"])
        elif status == "Downloading":
            progress_bar.configure(progress_color=COLORS["downloading"])
        elif status == "Failed":
            progress_bar.configure(progress_color=COLORS["failed"])
        else:
            progress_bar.configure(progress_color=COLORS["paused"])
        progress_bar.set(progress_val)
        progress_bar.pack(side="left", padx=5)

        percent = int(progress_val * 100)
        lbl_percent = ctk.CTkLabel(row_frame, text=f"{percent}%",
                                    font=ctk.CTkFont(size=10, weight="bold"),
                                    width=35, anchor="w", text_color=COLORS["text"])
        lbl_percent.pack(side="left", padx=2)

        # 4. Speed
        speed_text = dl.get("speed", "0 KB/s")
        speed_color = COLORS["green"] if status == "Downloading" else COLORS["text_dim"]
        lbl_speed = ctk.CTkLabel(row_frame, text=speed_text,
                                  font=ctk.CTkFont(size=10), width=80, anchor="w",
                                  text_color=speed_color)
        lbl_speed.pack(side="left", padx=3)

        # 5. Status text
        status_colors = {
            "Completed": COLORS["completed"],
            "Downloading": COLORS["downloading"],
            "Paused": COLORS["paused"],
            "Failed": COLORS["failed"],
            "Queued": COLORS["queued"],
        }
        lbl_status = ctk.CTkLabel(row_frame, text=status,
                                   font=ctk.CTkFont(size=10, weight="bold"),
                                   width=75, anchor="w",
                                   text_color=status_colors.get(status, COLORS["text_dim"]))
        lbl_status.pack(side="left", padx=3)

        # 6. ETA
        lbl_eta = ctk.CTkLabel(row_frame, text=dl.get("eta", "--:--"),
                                font=ctk.CTkFont(size=10), width=55, anchor="w",
                                text_color=COLORS["text_dim"])
        lbl_eta.pack(side="left", padx=3)

        # 7. Schedule
        sched_text = ""
        if dl.get("schedule_start") or dl.get("schedule_stop"):
            sched_text = f"⏰ {dl.get('schedule_start', '')}"
        lbl_sched = ctk.CTkLabel(row_frame, text=sched_text,
                                  font=ctk.CTkFont(size=9), width=70, anchor="w",
                                  text_color=COLORS["orange"])
        lbl_sched.pack(side="left", padx=3)

        self.row_widgets[dl_id] = {
            "frame": row_frame,
            "lbl_name": lbl_name,
            "lbl_size": lbl_size,
            "progress_bar": progress_bar,
            "lbl_percent": lbl_percent,
            "lbl_speed": lbl_speed,
            "lbl_status": lbl_status,
            "lbl_eta": lbl_eta,
            "lbl_sched": lbl_sched,
        }

        if self.selected_download_id == dl_id:
            row_frame.configure(fg_color=COLORS["row_selected"])

    def select_row(self, dl_id):
        # Deselect old
        if self.selected_download_id and self.selected_download_id in self.row_widgets:
            self.row_widgets[self.selected_download_id]["frame"].configure(fg_color="transparent")
        self.selected_download_id = dl_id
        # Select new
        if dl_id in self.row_widgets:
            self.row_widgets[dl_id]["frame"].configure(fg_color=COLORS["row_selected"])

    # ============================================================
    # RIGHT-CLICK CONTEXT MENU
    # ============================================================
    def show_context_menu(self, event, dl_id):
        self.select_row(dl_id)
        dl = self.downloads.get(dl_id)
        if not dl:
            return

        menu = tk.Menu(self, tearoff=0, bg="#1a1a2e", fg="white",
                        activebackground="#0f3460", activeforeground="white",
                        font=("Segoe UI", 10))

        if dl["status"] in ("Paused", "Queued", "Failed"):
            menu.add_command(label="▶ Resume (استئناف)", command=lambda: self.resume_download(dl_id))
        if dl["status"] == "Downloading":
            menu.add_command(label="⏸ Pause (إيقاف)", command=lambda: self.pause_download(dl_id))

        menu.add_separator()

        if dl["status"] == "Completed":
            menu.add_command(label="📂 Open File (فتح الملف)", command=lambda: self.open_downloaded_file(dl_id))
        menu.add_command(label="📁 Open Folder (فتح المجلد)", command=self.open_containing_folder)
        menu.add_separator()
        menu.add_command(label="📋 Copy URL (نسخ الرابط)", command=self.copy_url)
        menu.add_command(label="🔄 Retry Download (إعادة المحاولة)", command=lambda: self.retry_download(dl_id))
        menu.add_separator()
        menu.add_command(label="📅 Schedule (جدولة)", command=self.show_schedule_dialog)
        menu.add_separator()
        menu.add_command(label="🗑 Delete (حذف)", command=self.delete_selected)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # ============================================================
    # FORMATTING
    # ============================================================
    def format_size(self, size_bytes):
        if not size_bytes or size_bytes <= 0:
            return "Unknown"
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 ** 2:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 ** 3:
            return f"{size_bytes / (1024 ** 2):.1f} MB"
        else:
            return f"{size_bytes / (1024 ** 3):.2f} GB"

    def format_speed(self, speed_bytes_sec):
        if not speed_bytes_sec or speed_bytes_sec <= 0:
            return "0 KB/s"
        if speed_bytes_sec < 1024:
            return f"{speed_bytes_sec} B/s"
        elif speed_bytes_sec < 1024 ** 2:
            return f"{speed_bytes_sec / 1024:.1f} KB/s"
        else:
            return f"{speed_bytes_sec / (1024 ** 2):.1f} MB/s"

    def format_eta(self, eta_seconds):
        if not eta_seconds or eta_seconds >= 999999:
            return "--:--"
        eta_seconds = int(eta_seconds)
        if eta_seconds < 60:
            return f"{eta_seconds}s"
        elif eta_seconds < 3600:
            return f"{eta_seconds // 60}m {eta_seconds % 60}s"
        else:
            return f"{eta_seconds // 3600}h {(eta_seconds % 3600) // 60}m"

    # ============================================================
    # SPEED LIMITER
    # ============================================================
    def toggle_speed_limit(self):
        if self.chk_limit.get() == 1:
            self.slider_limit.configure(state="normal")
            self.change_speed_limit(self.slider_limit.get())
        else:
            self.slider_limit.configure(state="disabled")
            self.global_speed_limit = None
            self.lbl_limit_val.configure(text="Unlimited", text_color=COLORS["green"])
            for job in self.active_jobs.values():
                if hasattr(job, 'update_speed_limit'):
                    job.update_speed_limit(None)

    def change_speed_limit(self, value):
        limit_kb = int(value)
        self.global_speed_limit = limit_kb * 1024
        self.lbl_limit_val.configure(text=f"{limit_kb} KB/s", text_color=COLORS["orange"])
        for job in self.active_jobs.values():
            if hasattr(job, 'update_speed_limit'):
                job.update_speed_limit(self.global_speed_limit)

    # ============================================================
    # CLIPBOARD MONITOR
    # ============================================================
    def start_clipboard_monitor(self):
        def worker():
            while not self._destroying:
                time.sleep(1.0)
                if not self.clipboard_monitor_active.get():
                    continue
                try:
                    text = pyperclip.paste().strip()
                    if text and text != self.last_clipboard_url:
                        if text.startswith("http://") or text.startswith("https://") or text.startswith("magnet:"):
                            downloadable_exts = (
                                ".zip", ".rar", ".exe", ".msi", ".pdf", ".mp4", ".mp3",
                                ".mkv", ".7z", ".iso", ".tar", ".gz", ".avi", ".flv",
                                ".mov", ".dmg", ".apk", ".torrent", ".doc", ".docx",
                                ".xls", ".xlsx", ".ppt", ".pptx", ".webm"
                            )
                            is_media = any(text.lower().endswith(ext) for ext in downloadable_exts)
                            is_yt = "youtube.com" in text or "youtu.be" in text
                            is_magnet = text.startswith("magnet:")

                            if is_media or is_yt or is_magnet:
                                self.last_clipboard_url = text
                                self.clipboard_queue.put(text)
                except Exception:
                    pass
        threading.Thread(target=worker, daemon=True).start()

    # ============================================================
    # BROWSER INTEGRATION SERVER
    # ============================================================
    def start_integration_server(self):
        import integration_server
        threading.Thread(
            target=integration_server.start_server,
            args=(self.browser_queue, self.youtube_queue, self),
            daemon=True
        ).start()

    # ============================================================
    # SYSTEM TRAY
    # ============================================================
    def setup_tray(self):
        if not HAS_TRAY:
            return
        self.tray_menu = pystray.Menu(
            pystray.MenuItem("Show / Hide (إظهار / إخفاء)", self.tray_toggle_visibility),
            pystray.MenuItem("Resume All (استئناف الكل)", lambda: self.after(0, self.resume_all)),
            pystray.MenuItem("Pause All (إيقاف الكل)", lambda: self.after(0, self.pause_all)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit (خروج)", self.quit_application)
        )
        self.tray_icon = pystray.Icon("TurboDown", create_tray_image(), APP_NAME, menu=self.tray_menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def hide_window(self):
        self.withdraw()
        if HAS_TRAY:
            try:
                self.tray_icon.notify(
                    "TurboDown is running in background.\nالبرنامج يعمل في الخلفية",
                    "Right-click tray icon to show."
                )
            except Exception:
                pass

    def tray_toggle_visibility(self):
        self.after(0, self._tray_toggle_main)

    def _tray_toggle_main(self):
        if self.winfo_viewable():
            self.withdraw()
        else:
            self.deiconify()
            self.focus_force()

    def quit_application(self, *args):
        self._destroying = True
        self.pause_all()
        self.save_database()
        if HAS_TRAY:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.after(100, self._force_quit)

    def _force_quit(self):
        try:
            self.destroy()
        except Exception:
            pass
        os._exit(0)

    # ============================================================
    # DIALOG WINDOWS
    # ============================================================
    def show_add_url_dialog(self, initial_url=""):
        if not initial_url:
            try:
                clip = pyperclip.paste().strip()
                if clip.startswith("http://") or clip.startswith("https://"):
                    initial_url = clip
            except Exception:
                pass

        dialog = AddUrlDialog(self, initial_url)
        self.wait_window(dialog)

        if dialog.result:
            url, dest_path, immediate = dialog.result
            self.add_download(url, dest_path, immediate)

    def show_youtube_dialog(self, initial_url=""):
        if not initial_url:
            try:
                clip = pyperclip.paste().strip()
                if "youtube.com" in clip or "youtu.be" in clip:
                    initial_url = clip
            except Exception:
                pass
        dialog = YoutubeDialog(self, initial_url)
        self.wait_window(dialog)

    def show_batch_import_dialog(self):
        file_path = filedialog.askopenfilename(
            title="Import URLs from File (تحميل روابط دفعة واحدة)",
            filetypes=[("Text files", "*.txt"), ("CSV files", "*.csv"), ("All", "*.*")]
        )
        if not file_path:
            return

        try:
            urls = []
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("http://") or line.startswith("https://"):
                        urls.append(line)

            if not urls:
                messagebox.showinfo("Batch Import", "No valid URLs found in file.")
                return

            folder = filedialog.askdirectory(title="Choose download folder for batch files")
            if not folder:
                return

            for url in urls:
                mock = DownloadJob(url, "temp")
                fn = mock.get_filename_from_url()
                if "?" in fn:
                    fn = fn.split("?")[0]
                self.add_download(url, os.path.join(folder, fn), immediate=False)

            messagebox.showinfo("Batch Import", f"Successfully queued {len(urls)} links.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to import: {e}")

    def show_schedule_dialog(self):
        if not self.selected_download_id:
            messagebox.showinfo("Scheduler", "Please select a download task first.\nاختر تحميل أولاً")
            return
        dl = self.downloads.get(self.selected_download_id)
        if not dl:
            return
        if dl["status"] == "Completed":
            messagebox.showinfo("Scheduler", "Task is already completed.\nالتحميل مكتمل")
            return
        dialog = ScheduleDialog(self, dl)
        self.wait_window(dialog)
        self.save_database()
        self.refresh_row_ui(self.selected_download_id)

    def show_settings_dialog(self):
        dialog = SettingsDialog(self)
        self.wait_window(dialog)

    def show_about(self):
        messagebox.showinfo(
            f"About {APP_NAME}",
            f"{APP_NAME} v{APP_VERSION}\n\n"
            "A powerful, free, open-source download manager.\n"
            "The ultimate multi-threaded download accelerator.\n\n"
            "Features:\n"
            "• Multi-threaded downloads (up to 128 connections)\n"
            "• YouTube video downloads\n"
            "• Browser integration (Chrome/Brave/Firefox)\n"
            "• Pause/Resume/Schedule\n"
            "• Speed limiter\n"
            "• Clipboard monitoring\n\n"
            "Made with ❤ in Python"
        )

    # ============================================================
    # DOWNLOAD ACTIONS
    # ============================================================
    def add_download(self, url, dest_path, immediate=True):
        dl_id = str(int(time.time() * 1000))
        filename = os.path.basename(dest_path)
        category = self.get_category_by_extension(filename)

        self.downloads[dl_id] = {
            "id": dl_id,
            "url": url,
            "filename": filename,
            "dest_path": dest_path,
            "size": 0,
            "downloaded": 0,
            "status": "Queued",
            "speed": "0 KB/s",
            "eta": "--:--",
            "date": time.time(),
            "category": category,
            "is_youtube": False,
            "yt_format_id": None,
            "schedule_start": None,
            "schedule_stop": None,
            "error_msg": "",
        }

        self.save_database()
        self.refresh_downloads_list()

        if immediate:
            self.selected_download_id = dl_id
            self.resume_download(dl_id)

    def resume_selected(self):
        if self.selected_download_id:
            self.resume_download(self.selected_download_id)

    def resume_all(self):
        count = 0
        for dl_id, dl in list(self.downloads.items()):
            if dl["status"] in ("Queued", "Paused", "Failed") and dl_id not in self.active_jobs:
                if len(self.active_jobs) >= self.max_simultaneous:
                    break
                self.resume_download(dl_id)
                count += 1
        if count > 0:
            print(f"[TurboDown] Resumed {count} downloads")

    def resume_download(self, dl_id):
        dl = self.downloads.get(dl_id)
        if not dl:
            return
        if dl["status"] == "Completed":
            return
        if dl_id in self.active_jobs:
            return
        if len(self.active_jobs) >= self.max_simultaneous:
            dl["status"] = "Queued"
            self.save_database()
            self.refresh_row_ui(dl_id)
            return

        dl["status"] = "Downloading"
        dl["speed"] = "0 KB/s"
        dl["error_msg"] = ""
        self.save_database()
        self.refresh_row_ui(dl_id)

        if dl.get("is_youtube", False):
            t = threading.Thread(target=self._run_youtube_download, args=(dl_id,), daemon=True)
            t.start()
        else:
            limit = self.global_speed_limit if self.chk_limit.get() == 1 else None
            job = DownloadJob(dl["url"], dl["dest_path"],
                              num_threads=self.default_connections,
                              speed_limit=limit)
            self.active_jobs[dl_id] = job
            t = threading.Thread(target=self._run_http_download, args=(dl_id, job), daemon=True)
            t.start()

    def _run_http_download(self, dl_id, job):
        """Background thread for HTTP downloads."""
        try:
            if not job.initialize():
                self.downloads[dl_id]["status"] = "Failed"
                self.downloads[dl_id]["speed"] = "0 KB/s"
                self.downloads[dl_id]["eta"] = "--:--"
                self.downloads[dl_id]["error_msg"] = job.error_message
                self.save_database()
                self.after(0, lambda: self.refresh_row_ui(dl_id))
                return

            # Update metadata from server response
            self.downloads[dl_id]["size"] = job.total_size
            self.downloads[dl_id]["url"] = job.url
            new_filename = os.path.basename(job.dest_path)
            self.downloads[dl_id]["filename"] = new_filename
            self.downloads[dl_id]["dest_path"] = job.dest_path
            self.downloads[dl_id]["category"] = self.get_category_by_extension(new_filename)
            self.save_database()
            self.after(0, lambda: self.refresh_row_ui(dl_id))

            # Start downloading
            job.start()

            # Monitor until done
            while job.status == "Downloading":
                time.sleep(0.3)
                if dl_id not in self.downloads:
                    job.pause()
                    break
                self.downloads[dl_id]["downloaded"] = job.downloaded_bytes
                self.downloads[dl_id]["speed"] = self.format_speed(job.current_speed)
                self.downloads[dl_id]["eta"] = self.format_eta(job.eta)
                self.downloads[dl_id]["status"] = job.status

            # Final state
            if dl_id in self.downloads:
                old_status = self.downloads[dl_id].get("status")
                self.downloads[dl_id]["status"] = job.status
                self.downloads[dl_id]["downloaded"] = job.downloaded_bytes
                self.downloads[dl_id]["speed"] = "0 KB/s"
                self.downloads[dl_id]["eta"] = "--:--"
                if job.error_message:
                    self.downloads[dl_id]["error_msg"] = job.error_message
                self.save_database()
                if job.status == "Completed" and old_status == "Downloading":
                    self.after(0, lambda: self.show_complete_dialog(dl_id))

        except Exception as e:
            if dl_id in self.downloads:
                self.downloads[dl_id]["status"] = "Failed"
                self.downloads[dl_id]["error_msg"] = str(e)
                self.downloads[dl_id]["speed"] = "0 KB/s"
                self.save_database()
        finally:
            self.active_jobs.pop(dl_id, None)
            self.after(0, lambda: self.refresh_row_ui(dl_id))
            self._try_start_queued()

    def _run_youtube_download(self, dl_id):
        """Background thread for YouTube downloads."""
        dl = self.downloads.get(dl_id)
        if not dl:
            return

        class YtJob:
            def __init__(self):
                self.stop_event = threading.Event()
            def pause(self):
                self.stop_event.set()
            def update_speed_limit(self, val):
                pass  # yt-dlp handles its own speed

        job = YtJob()
        self.active_jobs[dl_id] = job

        def yt_callback(downloaded, total, speed, eta):
            if job.stop_event.is_set():
                raise Exception("Download Cancelled")
            if dl_id in self.downloads:
                self.downloads[dl_id]["downloaded"] = downloaded
                self.downloads[dl_id]["size"] = total
                self.downloads[dl_id]["speed"] = self.format_speed(speed)
                self.downloads[dl_id]["eta"] = self.format_eta(eta)
                self.downloads[dl_id]["status"] = "Downloading"

        try:
            final_path = download_video_format(
                dl["url"], dl["yt_format_id"], dl["dest_path"],
                progress_callback=yt_callback,
                stop_event=job.stop_event
            )
            if dl_id in self.downloads:
                self.downloads[dl_id]["status"] = "Completed"
                self.downloads[dl_id]["dest_path"] = final_path
                self.downloads[dl_id]["filename"] = os.path.basename(final_path)
                self.downloads[dl_id]["downloaded"] = self.downloads[dl_id]["size"]
                self.downloads[dl_id]["speed"] = "0 KB/s"
                self.downloads[dl_id]["eta"] = "--:--"
                self.after(0, lambda: self.show_complete_dialog(dl_id))
        except Exception as e:
            if dl_id in self.downloads:
                if "Cancelled" in str(e) or job.stop_event.is_set():
                    self.downloads[dl_id]["status"] = "Paused"
                else:
                    self.downloads[dl_id]["status"] = "Failed"
                    self.downloads[dl_id]["error_msg"] = str(e)
                self.downloads[dl_id]["speed"] = "0 KB/s"
                self.downloads[dl_id]["eta"] = "--:--"
        finally:
            self.save_database()
            self.active_jobs.pop(dl_id, None)
            self.after(0, lambda: self.refresh_row_ui(dl_id))
            self._try_start_queued()

    def _try_start_queued(self):
        """Auto-start queued downloads when a slot opens up."""
        if len(self.active_jobs) >= self.max_simultaneous:
            return
        for dl_id, dl in list(self.downloads.items()):
            if dl["status"] == "Queued" and dl_id not in self.active_jobs:
                self.after(100, lambda d=dl_id: self.resume_download(d))
                break

    def pause_selected(self):
        if self.selected_download_id:
            self.pause_download(self.selected_download_id)

    def pause_download(self, dl_id):
        job = self.active_jobs.get(dl_id)
        if job:
            job.pause()
            if dl_id in self.downloads:
                self.downloads[dl_id]["status"] = "Paused"
                self.downloads[dl_id]["speed"] = "0 KB/s"
                self.downloads[dl_id]["eta"] = "--:--"
                self.save_database()
                self.refresh_row_ui(dl_id)
        elif dl_id in self.downloads and self.downloads[dl_id]["status"] == "Queued":
            self.downloads[dl_id]["status"] = "Paused"
            self.save_database()
            self.refresh_row_ui(dl_id)

    def pause_all(self):
        for dl_id in list(self.active_jobs.keys()):
            self.pause_download(dl_id)

    def delete_selected(self):
        if not self.selected_download_id:
            return
        self.pause_download(self.selected_download_id)
        dl = self.downloads.get(self.selected_download_id)
        if not dl:
            return

        confirm = messagebox.askyesno(
            "Delete Download",
            f"Delete this download?\nحذف هذا التحميل؟\n\n{dl['filename']}"
        )
        if confirm:
            try:
                if os.path.exists(dl["dest_path"]):
                    os.remove(dl["dest_path"])
                meta = dl["dest_path"] + ".meta"
                if os.path.exists(meta):
                    os.remove(meta)
            except Exception as e:
                print(f"Error removing files: {e}")
            self.downloads.pop(self.selected_download_id, None)
            self.selected_download_id = None
            self.save_database()
            self.refresh_downloads_list()

    def retry_download(self, dl_id):
        """Retry a failed download from scratch."""
        dl = self.downloads.get(dl_id)
        if not dl:
            return
        # Remove partial files
        try:
            if os.path.exists(dl["dest_path"]):
                os.remove(dl["dest_path"])
            meta = dl["dest_path"] + ".meta"
            if os.path.exists(meta):
                os.remove(meta)
        except Exception:
            pass
        dl["downloaded"] = 0
        dl["status"] = "Queued"
        dl["speed"] = "0 KB/s"
        dl["eta"] = "--:--"
        dl["error_msg"] = ""
        self.save_database()
        self.resume_download(dl_id)

    def clear_finished(self):
        completed = [d for d, dl in self.downloads.items() if dl["status"] == "Completed"]
        if not completed:
            return
        confirm = messagebox.askyesno(
            "Clear Finished",
            f"Remove {len(completed)} completed downloads from list?\n"
            "حذف التحميلات المكتملة من القائمة؟"
        )
        if confirm:
            for dl_id in completed:
                self.downloads.pop(dl_id, None)
            self.save_database()
            self.refresh_downloads_list()

    def open_downloaded_file(self, dl_id):
        dl = self.downloads.get(dl_id)
        if not dl:
            return
        if dl["status"] == "Completed":
            if os.path.exists(dl["dest_path"]):
                try:
                    os.startfile(dl["dest_path"])
                except Exception as e:
                    messagebox.showerror("Error", f"Cannot open file: {e}")
            else:
                messagebox.showerror("Error", "File not found on disk.\nالملف غير موجود")
        else:
            confirm = messagebox.askyesno(
                "Resume?", "File not completed. Resume download?\nالملف لم يكتمل. هل تريد الاستئناف؟"
            )
            if confirm:
                self.resume_download(dl_id)

    def open_containing_folder(self):
        if not self.selected_download_id:
            return
        dl = self.downloads.get(self.selected_download_id)
        if not dl:
            return
        folder = os.path.dirname(dl["dest_path"])
        if os.path.exists(folder):
            os.startfile(folder)
        else:
            messagebox.showerror("Error", "Folder not found.\nالمجلد غير موجود")

    def copy_url(self):
        if not self.selected_download_id:
            return
        dl = self.downloads.get(self.selected_download_id)
        if dl:
            pyperclip.copy(dl["url"])

    # ============================================================
    # SCHEDULER
    # ============================================================
    def check_scheduler(self):
        now = time.time()
        if now - self.last_scheduler_check < 10:
            return
        self.last_scheduler_check = now
        now_str = time.strftime("%H:%M")

        for dl_id, dl in list(self.downloads.items()):
            status = dl.get("status")
            start_time = dl.get("schedule_start")
            if start_time == now_str and status in ("Queued", "Paused") and dl_id not in self.active_jobs:
                print(f"[Scheduler] Starting: {dl['filename']}")
                self.resume_download(dl_id)

            stop_time = dl.get("schedule_stop")
            if stop_time == now_str and status == "Downloading" and dl_id in self.active_jobs:
                print(f"[Scheduler] Stopping: {dl['filename']}")
                self.pause_download(dl_id)

    # ============================================================
    # PERIODIC UI UPDATE
    # ============================================================
    def refresh_row_ui(self, dl_id):
        if dl_id not in self.row_widgets or dl_id not in self.downloads:
            return

        dl = self.downloads[dl_id]
        row = self.row_widgets[dl_id]

        status = dl.get("status", "Paused")
        icon_map = {"Completed": "✅", "Downloading": "⬇", "Paused": "⏸",
                     "Failed": "❌", "Queued": "⏳"}
        row["lbl_name"].configure(text=f"{icon_map.get(status, '❓')} {dl['filename']}")

        size_bytes = dl.get("size", 0)
        row["lbl_size"].configure(text=self.format_size(size_bytes))

        progress_val = 0
        if size_bytes > 0:
            progress_val = min(1.0, dl.get("downloaded", 0) / size_bytes)
        row["progress_bar"].set(progress_val)
        row["lbl_percent"].configure(text=f"{int(progress_val * 100)}%")

        # Progress bar color
        color_map = {"Completed": COLORS["completed"], "Downloading": COLORS["downloading"],
                      "Failed": COLORS["failed"]}
        row["progress_bar"].configure(progress_color=color_map.get(status, COLORS["paused"]))

        speed_text = dl.get("speed", "0 KB/s")
        speed_color = COLORS["green"] if status == "Downloading" else COLORS["text_dim"]
        row["lbl_speed"].configure(text=speed_text, text_color=speed_color)

        status_colors = {"Completed": COLORS["completed"], "Downloading": COLORS["downloading"],
                          "Paused": COLORS["paused"], "Failed": COLORS["failed"],
                          "Queued": COLORS["queued"]}
        row["lbl_status"].configure(text=status, text_color=status_colors.get(status, COLORS["text_dim"]))

        row["lbl_eta"].configure(text=dl.get("eta", "--:--"))

        sched_text = ""
        if dl.get("schedule_start") or dl.get("schedule_stop"):
            sched_text = f"⏰ {dl.get('schedule_start', '')}"
        row["lbl_sched"].configure(text=sched_text)

    def update_loop(self):
        if self._destroying:
            return

        # 1. Browser extension queue
        try:
            while not self.browser_queue.empty():
                item = self.browser_queue.get_nowait()
                url = item.get("url", "")
                if url:
                    self.deiconify()
                    self.focus_force()
                    self.show_add_url_dialog(initial_url=url)
        except Exception:
            pass

        # 2. YouTube queue from extension
        try:
            while not self.youtube_queue.empty():
                item = self.youtube_queue.get_nowait()
                url = item.get("url", "")
                if url:
                    self.deiconify()
                    self.focus_force()
                    self.show_youtube_dialog(initial_url=url)
        except Exception:
            pass

        # 3. Clipboard queue
        try:
            while not self.clipboard_queue.empty():
                url = self.clipboard_queue.get_nowait()
                self.deiconify()
                self.focus_force()
                if "youtube.com" in url or "youtu.be" in url:
                    self.show_youtube_dialog(initial_url=url)
                else:
                    self.show_add_url_dialog(initial_url=url)
        except Exception:
            pass

        # 4. Scheduler
        self.check_scheduler()

        # 5. Update active download rows
        for dl_id in list(self.active_jobs.keys()):
            self.refresh_row_ui(dl_id)

        # 6. Update counter
        active_count = len(self.active_jobs)
        total = len(self.downloads)
        self.lbl_counter.configure(
            text=f"Downloads: {total} | Active: {active_count} / {self.max_simultaneous}"
        )

        self.after(250, self.update_loop)

    def show_complete_dialog(self, dl_id):
        dl = self.downloads.get(dl_id)
        if not dl or self._destroying:
            return

        filename = dl.get("filename", "File")
        size_bytes = dl.get("size", 0)
        size_str = self.format_size(size_bytes)
        dest_path = dl.get("dest_path", "")

        dialog = DownloadCompleteDialog(self, filename, size_str, dest_path)



# ============================================================
# DIALOG: Add URL
# ============================================================
class AddUrlDialog(ctk.CTkToplevel):
    def __init__(self, parent, initial_url=""):
        super().__init__(parent)
        self.title("Add New Download - إضافة تحميل جديد")
        self.geometry("650x280")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result = None
        self.grid_columnconfigure(1, weight=1)

        # URL
        ctk.CTkLabel(self, text="URL:", font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=0, padx=15, pady=12, sticky="w")
        self.ent_url = ctk.CTkEntry(self, width=480, placeholder_text="https://example.com/file.zip")
        self.ent_url.insert(0, initial_url)
        self.ent_url.grid(row=0, column=1, padx=15, pady=12, sticky="ew")

        # Save to
        ctk.CTkLabel(self, text="Save to:", font=ctk.CTkFont(size=12)).grid(
            row=1, column=0, padx=15, pady=8, sticky="w")
        save_frame = ctk.CTkFrame(self, fg_color="transparent")
        save_frame.grid(row=1, column=1, padx=15, pady=8, sticky="ew")
        save_frame.grid_columnconfigure(0, weight=1)
        self.ent_save = ctk.CTkEntry(save_frame)
        self.ent_save.insert(0, DEFAULT_DOWNLOAD_DIR)
        self.ent_save.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(save_frame, text="Browse", width=70, command=self.browse).grid(
            row=0, column=1, padx=5)

        # Filename
        ctk.CTkLabel(self, text="File Name:", font=ctk.CTkFont(size=12)).grid(
            row=2, column=0, padx=15, pady=8, sticky="w")
        self.ent_file = ctk.CTkEntry(self, placeholder_text="filename.ext")
        self.ent_file.grid(row=2, column=1, padx=15, pady=8, sticky="ew")

        self.ent_url.bind("<FocusOut>", self.auto_filename)
        self.ent_url.bind("<KeyRelease>", self.auto_filename)
        self.auto_filename()

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=3, column=0, columnspan=2, pady=15, sticky="ew")

        ctk.CTkButton(btn_frame, text="Cancel (إلغاء)", fg_color="#636e72",
                       hover_color="#4a5459", command=self.destroy).pack(side="left", padx=15)
        ctk.CTkButton(btn_frame, text="Download Later (لاحقاً)", fg_color="#fdcb6e",
                       hover_color="#e6b85e", text_color="black",
                       command=self.download_later).pack(side="right", padx=10)
        ctk.CTkButton(btn_frame, text="▶ Download Now (تحميل الآن)",
                       fg_color=COLORS["green"], hover_color=COLORS["green_hover"],
                       command=self.download_now).pack(side="right", padx=15)

    def auto_filename(self, event=None):
        url = self.ent_url.get().strip()
        if url:
            job = DownloadJob(url, "temp")
            fn = job.get_filename_from_url()
            if "?" in fn:
                fn = fn.split("?")[0]
            curr = self.ent_file.get().strip()
            if not curr or curr == "downloaded_file":
                self.ent_file.delete(0, tk.END)
                self.ent_file.insert(0, fn)

    def browse(self):
        folder = filedialog.askdirectory(initialdir=self.ent_save.get())
        if folder:
            self.ent_save.delete(0, tk.END)
            self.ent_save.insert(0, folder)

    def download_now(self):
        if self._validate():
            url = self.ent_url.get().strip()
            dest = os.path.join(self.ent_save.get().strip(), self.ent_file.get().strip())
            self.result = (url, dest, True)
            self.destroy()

    def download_later(self):
        if self._validate():
            url = self.ent_url.get().strip()
            dest = os.path.join(self.ent_save.get().strip(), self.ent_file.get().strip())
            self.result = (url, dest, False)
            self.destroy()

    def _validate(self):
        url = self.ent_url.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a URL.\nأدخل رابط")
            return False
        if url.startswith("magnet:"):
            confirm = messagebox.askyesno(
                "Torrent Magnet Link",
                "This is a Torrent Magnet link. TurboDown does not download torrents directly.\n"
                "Would you like to open it in your system's default Torrent client?\n\n"
                "هذا رابط تورنت مغناطيسي. هل تريد فتحه في برنامج التورنت الافتراضي لديك؟"
            )
            if confirm:
                import webbrowser
                webbrowser.open(url)
            self.destroy()
            return False
        if not self.ent_save.get().strip():
            messagebox.showerror("Error", "Please choose a save folder.\nاختر مجلد الحفظ")
            return False
        if not self.ent_file.get().strip():
            messagebox.showerror("Error", "Please enter a file name.\nأدخل اسم الملف")
            return False
        return True


# ============================================================
# DIALOG: YouTube
# ============================================================
class YoutubeDialog(ctk.CTkToplevel):
    def __init__(self, parent, initial_url=""):
        super().__init__(parent)
        self.title("YouTube Video Grabber - جالب فيديوهات يوتيوب")
        self.geometry("650x420")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.parent = parent
        self.video_info = None
        self.formats_map = {}
        self.grid_columnconfigure(1, weight=1)

        # URL
        ctk.CTkLabel(self, text="YouTube URL:", font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=0, padx=15, pady=12, sticky="w")
        self.ent_url = ctk.CTkEntry(self, width=420, placeholder_text="https://youtube.com/watch?v=...")
        self.ent_url.insert(0, initial_url)
        self.ent_url.grid(row=0, column=1, padx=15, pady=12, sticky="ew")

        # Fetch button
        self.btn_fetch = ctk.CTkButton(self, text="🔍 Fetch Video Info\nجلب معلومات الفيديو",
                                        fg_color="#c4302b", hover_color="#a8221d",
                                        command=self.start_fetch)
        self.btn_fetch.grid(row=1, column=0, columnspan=2, padx=15, pady=5)

        # Info frame
        self.info_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_medium"])
        self.info_frame.grid(row=2, column=0, columnspan=2, padx=15, pady=10, sticky="ew")
        self.info_frame.grid_columnconfigure(0, weight=1)
        self.lbl_title = ctk.CTkLabel(self.info_frame,
                                       text="Video details will appear after fetching...",
                                       wraplength=550, anchor="w", justify="left",
                                       text_color=COLORS["text_dim"])
        self.lbl_title.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        # Format
        ctk.CTkLabel(self, text="Format:", font=ctk.CTkFont(size=12)).grid(
            row=3, column=0, padx=15, pady=8, sticky="w")
        self.opt_format = ctk.CTkOptionMenu(self, values=["No formats loaded"], state="disabled")
        self.opt_format.grid(row=3, column=1, padx=15, pady=8, sticky="ew")

        # Save to
        ctk.CTkLabel(self, text="Save to:", font=ctk.CTkFont(size=12)).grid(
            row=4, column=0, padx=15, pady=8, sticky="w")
        save_frame = ctk.CTkFrame(self, fg_color="transparent")
        save_frame.grid(row=4, column=1, padx=15, pady=8, sticky="ew")
        save_frame.grid_columnconfigure(0, weight=1)
        self.ent_save = ctk.CTkEntry(save_frame)
        self.ent_save.insert(0, DEFAULT_DOWNLOAD_DIR)
        self.ent_save.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(save_frame, text="Browse", width=70,
                       command=self.browse).grid(row=0, column=1, padx=5)

        # Download button
        self.btn_download = ctk.CTkButton(self, text="⬇ Download Video\nتحميل الفيديو",
                                           fg_color=COLORS["green"],
                                           hover_color=COLORS["green_hover"],
                                           state="disabled", command=self.add_to_downloads)
        self.btn_download.grid(row=5, column=0, columnspan=2, padx=15, pady=15)

    def browse(self):
        folder = filedialog.askdirectory(initialdir=self.ent_save.get())
        if folder:
            self.ent_save.delete(0, tk.END)
            self.ent_save.insert(0, folder)

    def start_fetch(self):
        url = self.ent_url.get().strip()
        if not url:
            messagebox.showerror("Error", "Enter a YouTube URL.\nأدخل رابط يوتيوب")
            return
        self.lbl_title.configure(text="⏳ Fetching video info, please wait...", text_color=COLORS["blue"])
        self.btn_fetch.configure(state="disabled")
        threading.Thread(target=self._fetch_worker, args=(url,), daemon=True).start()

    def _fetch_worker(self, url):
        info = get_video_info(url)
        self.after(0, lambda: self._fetch_complete(info))

    def _fetch_complete(self, info):
        self.btn_fetch.configure(state="normal")
        if not info:
            self.lbl_title.configure(text="❌ Failed to fetch video info. Check URL.",
                                      text_color=COLORS["failed"])
            return

        self.video_info = info
        dur = info.get('duration', 0) or 0
        dur_str = f"{dur // 60}m {dur % 60}s" if dur >= 60 else f"{dur}s"
        self.lbl_title.configure(
            text=f"🎬 {info['title']}\n⏱ Duration: {dur_str}",
            text_color=COLORS["text"]
        )

        self.formats_map = {}
        values = []
        for fmt in info["formats"]:
            label = f"{fmt['label']} - {fmt['size_str']} [{fmt['ext']}]"
            self.formats_map[label] = fmt
            values.append(label)

        if values:
            self.opt_format.configure(values=values, state="normal")
            self.opt_format.set(values[0])
            self.btn_download.configure(state="normal")
        else:
            self.opt_format.configure(values=["No formats found"], state="disabled")

    def add_to_downloads(self):
        if not self.video_info:
            return
        fmt = self.formats_map.get(self.opt_format.get())
        if not fmt:
            return

        folder = self.ent_save.get().strip()
        clean_title = "".join(
            c for c in self.video_info["title"]
            if c.isalnum() or c in (" ", "-", "_", ".")
        ).strip()
        filename = f"{clean_title}.{fmt['ext']}"
        dest_path = os.path.join(folder, filename)

        dl_id = str(int(time.time() * 1000))
        self.parent.downloads[dl_id] = {
            "id": dl_id,
            "url": self.video_info["webpage_url"],
            "filename": filename,
            "dest_path": dest_path,
            "size": fmt["filesize"],
            "downloaded": 0,
            "status": "Queued",
            "speed": "0 KB/s",
            "eta": "--:--",
            "date": time.time(),
            "category": "Video" if fmt["type"] != "audio_only" else "Music",
            "is_youtube": True,
            "yt_format_id": fmt["format_id"],
            "schedule_start": None,
            "schedule_stop": None,
            "error_msg": "",
        }

        self.parent.save_database()
        self.parent.refresh_downloads_list()
        self.parent.selected_download_id = dl_id
        self.parent.resume_download(dl_id)
        self.destroy()


# ============================================================
# DIALOG: Schedule
# ============================================================
class ScheduleDialog(ctk.CTkToplevel):
    def __init__(self, parent, dl_dict):
        super().__init__(parent)
        self.title(f"Schedule - {dl_dict['filename']}")
        self.geometry("480x280")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.dl_dict = dl_dict
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text=f"📅 Schedule: {dl_dict['filename']}",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      wraplength=400).grid(row=0, column=0, columnspan=2, padx=15, pady=15)

        ctk.CTkLabel(self, text="Start Time (وقت البدء):").grid(
            row=1, column=0, padx=15, pady=10, sticky="w")
        self.ent_start = ctk.CTkEntry(self, placeholder_text="HH:MM (e.g. 02:30)")
        if dl_dict.get("schedule_start"):
            self.ent_start.insert(0, dl_dict["schedule_start"])
        self.ent_start.grid(row=1, column=1, padx=15, pady=10, sticky="ew")

        ctk.CTkLabel(self, text="Stop Time (وقت الإيقاف):").grid(
            row=2, column=0, padx=15, pady=10, sticky="w")
        self.ent_stop = ctk.CTkEntry(self, placeholder_text="HH:MM (e.g. 06:00)")
        if dl_dict.get("schedule_stop"):
            self.ent_stop.insert(0, dl_dict["schedule_stop"])
        self.ent_stop.grid(row=2, column=1, padx=15, pady=10, sticky="ew")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=3, column=0, columnspan=2, pady=15, sticky="ew")

        ctk.CTkButton(btn_frame, text="Cancel", fg_color="#636e72",
                       command=self.destroy).pack(side="left", padx=15)
        ctk.CTkButton(btn_frame, text="Remove Schedule", fg_color=COLORS["red"],
                       hover_color=COLORS["red_hover"],
                       command=self.remove_schedule).pack(side="right", padx=10)
        ctk.CTkButton(btn_frame, text="✅ Save Schedule",
                       fg_color=COLORS["green"], hover_color=COLORS["green_hover"],
                       command=self.save_schedule).pack(side="right", padx=15)

    def validate_time(self, t):
        if not t:
            return True
        try:
            parts = t.split(":")
            return len(parts) == 2 and 0 <= int(parts[0]) < 24 and 0 <= int(parts[1]) < 60
        except ValueError:
            return False

    def save_schedule(self):
        start = self.ent_start.get().strip()
        stop = self.ent_stop.get().strip()
        if not self.validate_time(start) or not self.validate_time(stop):
            messagebox.showerror("Error", "Invalid time. Use HH:MM format (e.g. 14:30)")
            return
        self.dl_dict["schedule_start"] = start or None
        self.dl_dict["schedule_stop"] = stop or None
        self.destroy()

    def remove_schedule(self):
        self.dl_dict["schedule_start"] = None
        self.dl_dict["schedule_stop"] = None
        self.destroy()


# ============================================================
# DIALOG: Settings
# ============================================================
class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Settings - إعدادات")
        self.geometry("500x350")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.parent = parent
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="⚙ Settings", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, columnspan=2, padx=15, pady=15)

        # Max simultaneous
        ctk.CTkLabel(self, text="Max Simultaneous Downloads:").grid(
            row=1, column=0, padx=15, pady=10, sticky="w")
        self.ent_max = ctk.CTkEntry(self, width=100)
        self.ent_max.insert(0, str(parent.max_simultaneous))
        self.ent_max.grid(row=1, column=1, padx=15, pady=10, sticky="w")

        # Connections per download
        ctk.CTkLabel(self, text="Connections per Download:").grid(
            row=2, column=0, padx=15, pady=10, sticky="w")
        self.ent_conn = ctk.CTkEntry(self, width=100)
        self.ent_conn.insert(0, str(parent.default_connections))
        self.ent_conn.grid(row=2, column=1, padx=15, pady=10, sticky="w")

        # Default download folder
        ctk.CTkLabel(self, text="Default Download Folder:").grid(
            row=3, column=0, padx=15, pady=10, sticky="w")
        self.ent_folder = ctk.CTkEntry(self, width=300)
        self.ent_folder.insert(0, DEFAULT_DOWNLOAD_DIR)
        self.ent_folder.grid(row=3, column=1, padx=15, pady=10, sticky="ew")

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=5, column=0, columnspan=2, pady=20, sticky="ew")
        ctk.CTkButton(btn_frame, text="Cancel", fg_color="#636e72",
                       command=self.destroy).pack(side="left", padx=15)
        ctk.CTkButton(btn_frame, text="✅ Save",
                       fg_color=COLORS["green"], hover_color=COLORS["green_hover"],
                       command=self.save_settings).pack(side="right", padx=15)

    def save_settings(self):
        try:
            self.parent.max_simultaneous = max(1, min(32, int(self.ent_max.get())))
            self.parent.default_connections = max(1, min(128, int(self.ent_conn.get())))
        except ValueError:
            messagebox.showerror("Error", "Invalid number")
            return
        self.destroy()

class DownloadCompleteDialog(ctk.CTkToplevel):
    def __init__(self, parent, filename, size_str, dest_path):
        super().__init__(parent)
        self.title("Download Complete - اكتمل التحميل")
        self.geometry("520x220")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.dest_path = dest_path
        self.grid_columnconfigure(1, weight=1)

        # Icon / Title
        title_lbl = ctk.CTkLabel(
            self, text="✅ Download Completed Successfully!\nاكتمل تحميل الملف بنجاح!",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=COLORS["green"]
        )
        title_lbl.grid(row=0, column=0, columnspan=2, padx=15, pady=15)

        # File Name
        ctk.CTkLabel(self, text="File Name:", font=ctk.CTkFont(weight="bold")).grid(
            row=1, column=0, padx=15, pady=5, sticky="w"
        )
        name_lbl = ctk.CTkLabel(self, text=filename, wraplength=380, justify="left", anchor="w")
        name_lbl.grid(row=1, column=1, padx=15, pady=5, sticky="w")

        # Size
        ctk.CTkLabel(self, text="File Size:", font=ctk.CTkFont(weight="bold")).grid(
            row=2, column=0, padx=15, pady=5, sticky="w"
        )
        size_lbl = ctk.CTkLabel(self, text=size_str)
        size_lbl.grid(row=2, column=1, padx=15, pady=5, sticky="w")

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=3, column=0, columnspan=2, pady=20, sticky="ew")

        ctk.CTkButton(
            btn_frame, text="Close (إغلاق)", fg_color="#636e72",
            hover_color="#4a5459", command=self.destroy
        ).pack(side="left", padx=15)

        ctk.CTkButton(
            btn_frame, text="📁 Open Folder (المجلد)", fg_color=COLORS["blue"],
            hover_color=COLORS["blue_hover"], command=self.open_folder
        ).pack(side="right", padx=10)

        ctk.CTkButton(
            btn_frame, text="▶ Open File (تشغيل)", fg_color=COLORS["green"],
            hover_color=COLORS["green_hover"], command=self.open_file
        ).pack(side="right", padx=15)

    def open_file(self):
        if os.path.exists(self.dest_path):
            try:
                os.startfile(self.dest_path)
            except Exception as e:
                messagebox.showerror("Error", f"Cannot open file: {e}")
        else:
            messagebox.showerror("Error", "File not found on disk.\nالملف غير موجود")
        self.destroy()

    def open_folder(self):
        folder = os.path.dirname(self.dest_path)
        if os.path.exists(folder):
            try:
                os.startfile(folder)
            except Exception as e:
                messagebox.showerror("Error", f"Cannot open folder: {e}")
        else:
            messagebox.showerror("Error", "Folder not found.\nالمجلد غير موجود")
        self.destroy()


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    app = TurboDownApp()
    app.mainloop()
