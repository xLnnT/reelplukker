import os
import sys

os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

# Frozen re-entry: when bundled with PyInstaller, the same binary is also used as
# a gallery-dl runner via the `--gallery-dl` flag. This avoids needing a separate
# Python interpreter at runtime.
if len(sys.argv) > 1 and sys.argv[1] == "--gallery-dl":
    from gallery_dl import __main__ as _gdl_main
    sys.argv = ["gallery-dl", *sys.argv[2:]]
    sys.exit(_gdl_main.main())

_EXTRA_PATHS = ("/opt/homebrew/bin", "/usr/local/bin")
_path = os.environ.get("PATH", "")
for _p in _EXTRA_PATHS:
    if _p not in _path.split(":"):
        _path = f"{_p}:{_path}" if _path else _p
os.environ["PATH"] = _path

import atexit
import re
import shutil
import subprocess
import tempfile
import threading
import traceback
import tkinter as tk
import tkinter.font as tkfont
import zipfile
from pathlib import Path
from urllib.parse import urlparse, unquote
from urllib.request import urlopen, Request

try:
    from PIL import Image, ImageTk
    _HAS_PIL = True
except ImportError:
    Image = None
    ImageTk = None
    _HAS_PIL = False

_UNSET = object()

# --- Branding ---
APP_NAME = "ReelPlukker"
AUTHOR_NAME = "Lennert Nuyttens"
AUTHOR_URL = "https://www.instagram.com/xLnnT/"
COOKIES_FILE = Path.home() / ".reelplukker" / "cookies.txt"

# --- Theme ---
BG = "#000000"
FG = "#FFFFFF"
DIM = "#666666"
HOVER_BG = "#222222"
MONO = "Menlo"

# --- Window ---
WINDOW_SIZE = "1180x860"
WINDOW_MIN = (880, 640)
TITLE_TEXT = APP_NAME
PLACEHOLDER_TEXT = "Paste your URL..."

# --- Cell ---
THUMB_SRC_W = 480
THUMB_SRC_H = 300
CELL_INSET = 6
SAFE_INSET = 14
TEXT_BAR_PAD_X = 7
TEXT_BAR_PAD_Y = 4
TEXT_BAR_GAP = 2
NAME_FONT_SIZE = 9
STATUS_FONT_SIZE = 8
PROGRESS_BAR_H = 3
PROGRESS_MARGIN = 24
FOLDER_ICON_SIZE = 11
FOLDER_ICON_MARGIN = 4

CLICK_CURSOR = "pointinghand" if sys.platform == "darwin" else "hand2"

# --- Layout ---
PADDING_X = 72
INPUT_HEIGHT = 64
URL_RADIUS = 14
FMT_RADIUS = 12
BTN_RADIUS = 10
HISTORY_COLS = 4
HISTORY_ROWS = 3

# --- Formats ---
FORMATS = ["MP4 (1080p)", "MP4 (1440p)", "MP4 (4K)", "MP4 (8K)", "MP3", "JPG", "Original"]
FORMAT_HEIGHTS = {
    "MP4 (1080p)": 1080,
    "MP4 (1440p)": 1440,
    "MP4 (4K)": 2160,
    "MP4 (8K)": 4320,
}
FMT_MP4 = "MP4"
FMT_MP3 = "MP3"
FMT_JPG = "JPG"

# --- File extensions ---
IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".heic"})
VIDEO_EXTS = frozenset({".mp4", ".mov", ".webm", ".mkv", ".m4v"})
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS
JPG_EXTS = frozenset({".jpg", ".jpeg"})
H264_CODECS = frozenset({"h264", "avc1"})
DIRECT_EXTS = frozenset({
    ".mp4", ".mp3", ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".wav", ".m4a", ".mov", ".webm", ".ogg", ".flac", ".aac",
    ".tiff", ".bmp", ".heic", ".avi", ".mkv", ".pdf", ".zip",
})
FS_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\n\r\t]')

# --- Network ---
NET_TIMEOUT = 30
GALLERY_TIMEOUT = 120
CHUNK_SIZE = 64 * 1024
USER_AGENT = "Mozilla/5.0"
YT_DOMAINS = ("youtube.com", "youtu.be")
INSTAGRAM_DOMAINS = ("instagram.com",)
TIKTOK_DOMAINS = ("tiktok.com",)
YT_SHORTS_FORMAT = "MP4 (1080p)"
TEMP_PREFIX = "downloader_"

# --- ffmpeg ---
ENCODE_LOCK = threading.Semaphore(1)
FFMPEG_THREADS = "4"
AUDIO_ARGS = ("-c:a", "aac", "-b:a", "192k")
VT_QUALITY = "65"
JPG_QUALITY = "2"
X264_PRESET = "faster"
X264_CRF = "20"
MP3_BITRATE = "192k"

IS_FROZEN = getattr(sys, "frozen", False)
IS_WINDOWS = sys.platform == "win32"
_EXE = ".exe" if IS_WINDOWS else ""


def _find_binary(name: str) -> str:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = Path(meipass) / f"{name}{_EXE}"
        if bundled.exists():
            return str(bundled)
    if IS_FROZEN:
        next_to_exe = Path(sys.executable).parent / f"{name}{_EXE}"
        if next_to_exe.exists():
            return str(next_to_exe)
    found = shutil.which(name)
    if found:
        return found
    return name + _EXE


FFMPEG_BIN = _find_binary("ffmpeg")
FFPROBE_BIN = _find_binary("ffprobe")

# --- Status strings ---
S_QUEUED = "Queued"
S_FETCHING = "Fetching"
S_CONNECTING = "Connecting"
S_DOWNLOADING = "Downloading"
S_PROCESSING = "Processing"
S_DONE = "Done"
S_WAITING_ENC = "Waiting to encode"
S_RE_ENCODING = "Re-encoding"
S_EXTRACTING_MP3 = "Extracting MP3"


def _cli_python() -> str:
    for name in ("python3.14", "python3"):
        candidate = Path(sys.prefix) / "bin" / name
        if candidate.exists() and not candidate.is_symlink():
            return str(candidate)
        if candidate.exists():
            return str(candidate.resolve())
    return sys.executable


CLI_PYTHON = _cli_python()


def is_direct_url(url):
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in DIRECT_EXTS)


def is_instagram_url(url):
    netloc = urlparse(url).netloc.lower()
    return any(d in netloc for d in INSTAGRAM_DOMAINS)


def is_tiktok_url(url):
    netloc = urlparse(url).netloc.lower()
    return any(d in netloc for d in TIKTOK_DOMAINS)


def is_youtube_shorts_url(url):
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    if not any(d in netloc for d in YT_DOMAINS):
        return False
    return "/shorts/" in parsed.path.lower()


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    i = 1
    while True:
        candidate = parent / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def rounded_rect(canvas, x1, y1, x2, y2, r=12, **kw):
    pts = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


class RoundedBox(tk.Canvas):
    def __init__(self, parent, radius=12, border=2, **kw):
        super().__init__(parent, bg=BG, highlightthickness=0, bd=0, **kw)
        self._radius = radius
        self._border = border
        self._shape = None
        self.bind("<Configure>", self._redraw)

    def _redraw(self, _=None):
        if self._shape is not None:
            self.delete(self._shape)
        w, h = self.winfo_width(), self.winfo_height()
        b = self._border
        self._shape = rounded_rect(
            self, b, b, w - b, h - b,
            r=self._radius, fill="", outline=FG, width=b,
        )


class HistoryCell(tk.Canvas):
    _name_font = None
    _status_font = None

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=BG, highlightthickness=0, bd=0, **kw)
        self.name = ""
        self.status = ""
        self.progress = None
        self.file_path = None
        self._pil_source = None
        self._tk_image = None
        self._tk_image_size = (0, 0)
        if HistoryCell._name_font is None:
            HistoryCell._name_font = tkfont.Font(family=MONO, size=NAME_FONT_SIZE)
            HistoryCell._status_font = tkfont.Font(family=MONO, size=STATUS_FONT_SIZE)
        self.bind("<Configure>", self._redraw)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def set(self, *, name=_UNSET, status=_UNSET, progress=_UNSET,
            file_path=_UNSET, thumbnail_path=_UNSET):
        if name is not _UNSET:
            self.name = name
        if status is not _UNSET:
            self.status = status
        if progress is not _UNSET:
            self.progress = progress
        if file_path is not _UNSET:
            self.file_path = file_path
        if thumbnail_path is not _UNSET:
            self._pil_source = self._load_source(thumbnail_path)
            self._tk_image = None
            self._tk_image_size = (0, 0)
        self._redraw()

    def reset(self):
        self.name = ""
        self.status = ""
        self.progress = None
        self.file_path = None
        self._pil_source = None
        self._tk_image = None
        self._tk_image_size = (0, 0)
        self._redraw()

    @staticmethod
    def _load_source(path):
        if not path:
            return None
        try:
            if _HAS_PIL:
                return Image.open(str(path)).convert("RGB")
            return tk.PhotoImage(file=str(path))
        except Exception:
            return None

    def _on_click(self, _):
        if not self.file_path:
            return
        p = Path(self.file_path)
        if not p.exists():
            return
        if IS_WINDOWS:
            subprocess.run(["explorer", f"/select,{p}"])
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", str(p)])
        else:
            subprocess.run(["xdg-open", str(p.parent)])

    def _on_enter(self, _):
        self.config(cursor=CLICK_CURSOR if self.file_path else "")

    def _on_leave(self, _):
        self.config(cursor="")

    def _redraw(self, _=None):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4 or h < 4:
            return

        inner_x0, inner_y0 = CELL_INSET, CELL_INSET
        inner_x1, inner_y1 = w - CELL_INSET, h - CELL_INSET
        inner_w = inner_x1 - inner_x0
        inner_h = inner_y1 - inner_y0

        if self._pil_source is not None and inner_w > 0 and inner_h > 0:
            self._render_thumbnail(inner_x0, inner_y0, inner_w, inner_h)

        rounded_rect(self, 3, 3, w - 3, h - 3, r=16, fill="", outline=FG, width=3)

        safe_x0 = SAFE_INSET
        safe_x1 = w - SAFE_INSET
        safe_y0 = SAFE_INSET
        safe_y1 = h - SAFE_INSET
        safe_w = max(0, safe_x1 - safe_x0)

        has_progress = (
            self.progress is not None and 0.0 <= self.progress < 1.0
        )
        has_text = bool(self.name or self.status)

        bar_top = safe_y1

        if has_text:
            max_text_w = max(20, safe_w - TEXT_BAR_PAD_X * 2)
            name_text = self._fit_text(self.name, self._name_font, max_text_w) if self.name else ""
            status_text = self._fit_text(self.status, self._status_font, max_text_w) if self.status else ""

            name_w = self._name_font.measure(name_text) if name_text else 0
            status_w = self._status_font.measure(status_text) if status_text else 0
            text_w = max(name_w, status_w)

            name_h = self._name_font.metrics("linespace") if name_text else 0
            status_h = self._status_font.metrics("linespace") if status_text else 0
            gap = TEXT_BAR_GAP if (name_text and status_text) else 0
            content_h = name_h + status_h + gap
            bar_h = content_h + TEXT_BAR_PAD_Y * 2
            bar_w = min(safe_w, text_w + TEXT_BAR_PAD_X * 2)

            bar_left = safe_x0
            bar_right = bar_left + bar_w
            bar_top = safe_y1 - bar_h

            self.create_rectangle(
                bar_left, bar_top, bar_right, bar_top + bar_h,
                fill=BG, outline="",
            )

            text_x = bar_left + TEXT_BAR_PAD_X
            y_cursor = bar_top + TEXT_BAR_PAD_Y
            if name_text:
                self.create_text(
                    text_x, y_cursor,
                    text=name_text,
                    fill=FG, font=self._name_font, anchor="nw",
                )
                y_cursor += name_h + gap
            if status_text:
                self.create_text(
                    text_x, y_cursor,
                    text=status_text,
                    fill=DIM, font=self._status_font, anchor="nw",
                )

        if has_progress:
            self._draw_progress_bar(safe_x0, safe_x1, bar_top)

        if self.file_path:
            self._draw_folder_icon(
                safe_x1 - FOLDER_ICON_SIZE / 2 - FOLDER_ICON_MARGIN,
                safe_y0 + FOLDER_ICON_SIZE / 2 + FOLDER_ICON_MARGIN,
                FOLDER_ICON_SIZE,
            )

    def _render_thumbnail(self, x, y, w, h):
        if _HAS_PIL and isinstance(self._pil_source, Image.Image):
            if self._tk_image is None or self._tk_image_size != (w, h):
                cropped = self._cover_crop(self._pil_source, w, h)
                self._tk_image = ImageTk.PhotoImage(cropped)
                self._tk_image_size = (w, h)
            self.create_image(x + w / 2, y + h / 2, image=self._tk_image)
        elif isinstance(self._pil_source, tk.PhotoImage):
            self.create_image(x + w / 2, y + h / 2, image=self._pil_source)

    @staticmethod
    def _cover_crop(img, target_w, target_h):
        src_w, src_h = img.size
        if src_w <= 0 or src_h <= 0:
            return img
        src_ratio = src_w / src_h
        target_ratio = target_w / target_h
        if src_ratio > target_ratio:
            new_w = int(round(src_h * target_ratio))
            x = (src_w - new_w) // 2
            box = (x, 0, x + new_w, src_h)
        else:
            new_h = int(round(src_w / target_ratio))
            y = (src_h - new_h) // 2
            box = (0, y, src_w, y + new_h)
        return img.resize((target_w, target_h), Image.LANCZOS, box=box)

    def _draw_progress_bar(self, x0, x1, bar_top):
        bar_y = bar_top - PROGRESS_BAR_H - 6
        if x1 <= x0:
            return
        self.create_rectangle(
            x0, bar_y, x1, bar_y + PROGRESS_BAR_H,
            fill=DIM, outline="",
        )
        p = max(0.0, min(1.0, self.progress))
        fill_x = x0 + (x1 - x0) * p
        if fill_x > x0:
            self.create_rectangle(
                x0, bar_y, fill_x, bar_y + PROGRESS_BAR_H,
                fill=FG, outline="",
            )

    def _draw_folder_icon(self, cx, cy, size):
        s = size
        x0, y0 = cx - s / 2, cy - s / 3
        x1, y1 = cx + s / 2, cy + s / 2
        self.create_rectangle(x0, y0, x1, y1, fill="", outline=FG, width=1.4)
        tab_w = s * 0.45
        self.create_rectangle(
            x0, y0 - s * 0.22, x0 + tab_w, y0,
            fill="", outline=FG, width=1.4,
        )

    @staticmethod
    def _fit_text(text, font_obj, max_px):
        if not text:
            return ""
        if font_obj.measure(text) <= max_px:
            return text
        ellipsis = "…"
        if font_obj.measure(ellipsis) > max_px:
            return ""
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if font_obj.measure(text[:mid] + ellipsis) <= max_px:
                lo = mid
            else:
                hi = mid - 1
        return (text[:lo] + ellipsis) if lo > 0 else ellipsis


class DownloaderApp:
    def __init__(self, root):
        self.root = root
        root.title(APP_NAME)
        root.configure(bg=BG)
        root.geometry(WINDOW_SIZE)
        root.minsize(*WINDOW_MIN)

        self.dest_dir = Path.home() / "Downloads"
        self.format_var = tk.StringVar(value=FORMATS[0])
        self.thumb_dir = Path(tempfile.mkdtemp(prefix="reelplukker_thumbs_"))
        atexit.register(shutil.rmtree, self.thumb_dir, True)

        self._build_ui()

    def _build_ui(self):
        root = self.root

        self._build_footer(root)

        tk.Label(
            root, text=TITLE_TEXT,
            bg=BG, fg=FG, font=(MONO, 34),
        ).pack(pady=(72, 56))

        input_row = tk.Frame(root, bg=BG)
        input_row.pack(fill="x", padx=PADDING_X, pady=(0, 28))

        url_box = RoundedBox(input_row, radius=URL_RADIUS, border=2, height=INPUT_HEIGHT)
        url_box.pack(side="left", fill="x", expand=True, padx=(0, 14))

        self._placeholder_active = True
        self.url_entry = tk.Entry(
            url_box,
            bg=BG, fg=DIM, insertbackground=FG,
            font=(MONO, 13), bd=0, highlightthickness=0,
            relief="flat",
        )
        self.url_entry.insert(0, PLACEHOLDER_TEXT)
        self.url_entry.bind("<FocusIn>", self._clear_placeholder)
        self.url_entry.bind("<FocusOut>", self._restore_placeholder)
        self.url_entry.bind("<Return>", lambda _: self.start_download())
        self.url_entry_window_id = url_box.create_window(
            20, INPUT_HEIGHT // 2, anchor="w", window=self.url_entry, width=200,
        )
        url_box.bind("<Configure>", self._resize_url_entry)
        self._url_box = url_box

        fmt_box = RoundedBox(
            input_row, radius=FMT_RADIUS, border=2,
            width=180, height=INPUT_HEIGHT,
        )
        fmt_box.pack(side="left", padx=(0, 14))

        self._format_display = tk.StringVar()
        self.format_var.trace_add(
            "write",
            lambda *_: self._format_display.set(f"{self.format_var.get()}  ▾"),
        )
        self._format_display.set(f"{self.format_var.get()}  ▾")

        fmt_label = tk.Label(
            fmt_box, textvariable=self._format_display,
            bg=BG, fg=FG, font=(MONO, 11), cursor=CLICK_CURSOR,
        )
        fmt_box.create_window(90, INPUT_HEIGHT // 2, window=fmt_label)

        fmt_menu = tk.Menu(
            self.root, tearoff=0, bg=BG, fg=FG,
            activebackground=HOVER_BG, activeforeground=FG,
        )
        for f in FORMATS:
            fmt_menu.add_command(label=f, command=lambda v=f: self.format_var.set(v))

        open_menu = lambda e: fmt_menu.tk_popup(e.x_root, e.y_root)
        fmt_label.bind("<Button-1>", open_menu)
        fmt_box.bind("<Button-1>", open_menu)

        dl_btn = RoundedBox(
            input_row, radius=BTN_RADIUS, border=2,
            width=INPUT_HEIGHT, height=INPUT_HEIGHT,
        )
        dl_btn.pack(side="left")
        dl_label = tk.Label(dl_btn, text="↓", bg=BG, fg=FG, font=(MONO, 22), cursor=CLICK_CURSOR)
        dl_btn.create_window(INPUT_HEIGHT // 2, INPUT_HEIGHT // 2, window=dl_label)
        click_dl = lambda _: self.start_download()
        dl_label.bind("<Button-1>", click_dl)
        dl_btn.bind("<Button-1>", click_dl)

        tk.Label(
            root, text="History",
            bg=BG, fg=FG, font=(MONO, 20),
        ).pack(pady=(24, 18))

        grid = tk.Frame(root, bg=BG)
        grid.pack(fill="both", expand=True, padx=PADDING_X, pady=(0, 40))

        self.cells = []
        for r in range(HISTORY_ROWS):
            for c in range(HISTORY_COLS):
                cell = HistoryCell(grid)
                cell.grid(row=r, column=c, padx=10, pady=10, sticky="nsew")
                self.cells.append(cell)
        for c in range(HISTORY_COLS):
            grid.columnconfigure(c, weight=1, uniform="col")
        for r in range(HISTORY_ROWS):
            grid.rowconfigure(r, weight=1, uniform="row")

    def _build_footer(self, root):
        footer = tk.Frame(root, bg=BG)
        footer.pack(side="bottom", fill="x", pady=(0, 14))

        inner = tk.Frame(footer, bg=BG)
        inner.pack()

        tk.Label(
            inner, text=f"{APP_NAME} made by ",
            bg=BG, fg=DIM, font=(MONO, 9),
        ).pack(side="left")

        link = tk.Label(
            inner, text=AUTHOR_NAME,
            bg=BG, fg=FG, font=(MONO, 9, "underline"),
            cursor=CLICK_CURSOR,
        )
        link.pack(side="left")
        link.bind("<Button-1>", lambda _: self._open_url(AUTHOR_URL))

    @staticmethod
    def _open_url(url):
        if IS_WINDOWS:
            os.startfile(url)
        elif sys.platform == "darwin":
            subprocess.run(["open", url])
        else:
            subprocess.run(["xdg-open", url])

    def _resize_url_entry(self, event):
        self._url_box._redraw()
        self._url_box.coords(self.url_entry_window_id, 20, event.height / 2)
        self._url_box.itemconfigure(
            self.url_entry_window_id, width=max(100, event.width - 40)
        )

    def _clear_placeholder(self, _):
        if self._placeholder_active:
            self.url_entry.delete(0, "end")
            self.url_entry.config(fg=FG)
            self._placeholder_active = False

    def _restore_placeholder(self, _):
        if not self.url_entry.get().strip():
            self.url_entry.insert(0, PLACEHOLDER_TEXT)
            self.url_entry.config(fg=DIM)
            self._placeholder_active = True

    def _get_url(self):
        if self._placeholder_active:
            return ""
        return self.url_entry.get().strip()

    def start_download(self):
        url = self._get_url()
        if not url:
            return
        self.url_entry.delete(0, "end")
        cell = self._next_cell()
        name = unquote(Path(urlparse(url).path).name) or url[:40]
        cell.set(name=name, status=S_QUEUED)
        threading.Thread(
            target=self._download, args=(url, cell), daemon=True
        ).start()

    def _next_cell(self):
        cell = self.cells.pop()
        cell.reset()
        self.cells.insert(0, cell)
        self._regrid()
        return cell

    def _regrid(self):
        for i, cell in enumerate(self.cells):
            r, c = divmod(i, HISTORY_COLS)
            cell.grid(row=r, column=c, padx=10, pady=10, sticky="nsew")

    def _ui(self, fn):
        self.root.after(0, fn)

    def _make_thumbnail(self, src: Path) -> Path | None:
        try:
            if not src.exists():
                return None
            thumb = self.thumb_dir / f"thumb_{abs(hash(str(src)))}.png"
            vf = (
                f"scale={THUMB_SRC_W}:{THUMB_SRC_H}"
                ":force_original_aspect_ratio=increase"
                f",crop={THUMB_SRC_W}:{THUMB_SRC_H}"
            )
            for ss_args in (["-ss", "0.5"], []):
                cmd = [FFMPEG_BIN, "-y", *ss_args, "-i", str(src),
                       "-frames:v", "1", "-vf", vf,
                       "-f", "image2", str(thumb)]
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=20,
                )
                if result.returncode == 0 and thumb.exists():
                    return thumb
        except Exception:
            pass
        return None

    def _finalize_cell(self, cell, file_path: Path):
        thumb = self._make_thumbnail(file_path)
        self._ui(lambda n=file_path.name, p=file_path, t=thumb:
                 cell.set(name=n, file_path=p, thumbnail_path=t,
                          progress=1.0))

    def _download(self, url, cell):
        try:
            self.dest_dir.mkdir(parents=True, exist_ok=True)
            fmt = self.format_var.get()
            direct = is_direct_url(url)
            if direct:
                self._direct_download(url, cell)
            elif is_instagram_url(url) or is_tiktok_url(url):
                self._photo_download(url, cell)
            elif is_youtube_shorts_url(url):
                self._ytdlp_download(url, cell, force_fmt=YT_SHORTS_FORMAT)
            elif fmt == FMT_JPG:
                self._photo_download(url, cell)
            else:
                self._ytdlp_download(url, cell)
            self._ui(lambda: cell.set(status=S_DONE, progress=1.0))
        except Exception as e:
            print(f"\n[download error] {url}", file=sys.stderr)
            traceback.print_exc()
            sys.stderr.flush()
            msg = str(e).replace("\n", " ")[:80]
            self._ui(lambda: cell.set(status=f"Error: {msg}", progress=None))

    def _direct_download(self, url, cell):
        self._ui(lambda: cell.set(status=S_CONNECTING, progress=None))
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=NET_TIMEOUT) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            name = unquote(Path(urlparse(url).path).name) or "download"
            out = unique_path(self.dest_dir / name)
            self._ui(lambda n=out.name: cell.set(
                name=n, status=S_DOWNLOADING, progress=0.0,
            ))
            done = 0
            with open(out, "wb") as f:
                while True:
                    chunk = resp.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        frac = done / total
                        self._ui(lambda f=frac: cell.set(
                            status=f"{int(f*100)}%", progress=f,
                        ))
        self._finalize_cell(cell, out)

    def _ytdlp_download(self, url, cell, force_fmt=None):
        try:
            import yt_dlp
        except ImportError:
            raise RuntimeError("yt-dlp not installed")

        fmt = force_fmt or self.format_var.get()
        work_dir = Path(tempfile.mkdtemp(prefix=TEMP_PREFIX))
        opts = {
            "outtmpl": str(work_dir / "%(title)s.%(ext)s"),
            "progress_hooks": [self._make_hook(cell)],
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "socket_timeout": NET_TIMEOUT,
            "retries": 3,
            "overwrites": True,
        }

        if not any(d in url for d in YT_DOMAINS):
            try:
                from yt_dlp.networking.impersonate import ImpersonateTarget
                opts["impersonate"] = ImpersonateTarget("chrome")
            except ImportError:
                pass

        if fmt.startswith(FMT_MP4):
            height = str(FORMAT_HEIGHTS.get(fmt, 1080))
            opts["format"] = (
                f"bestvideo[height<={height}]+bestaudio/"
                f"best[height<={height}]/best"
            )
            opts["format_sort"] = ["res", "vcodec:h264", "ext:mp4"]
            opts["merge_output_format"] = "mp4"
        elif fmt == FMT_MP3:
            opts["format"] = "bestaudio/best"

        try:
            self._ui(lambda: cell.set(status=S_FETCHING))
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                final_path = Path(ydl.prepare_filename(info))
                if opts.get("merge_output_format"):
                    final_path = final_path.with_suffix("." + opts["merge_output_format"])

            if fmt.startswith(FMT_MP4) and final_path.exists():
                self._ensure_h264(final_path, cell)
            elif fmt == FMT_MP3 and final_path.exists():
                final_path = self._extract_mp3(final_path, cell)

            if final_path.exists():
                moved = unique_path(self.dest_dir / final_path.name)
                shutil.move(str(final_path), str(moved))
                self._finalize_cell(cell, moved)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    def _photo_download(self, url, cell):
        self._ui(lambda: cell.set(status=S_FETCHING))
        work_dir = Path(tempfile.mkdtemp(prefix=TEMP_PREFIX))

        try:
            if IS_FROZEN:
                gdl_base = [sys.executable, "--gallery-dl"]
            else:
                gdl_base = [CLI_PYTHON, "-m", "gallery_dl"]
            if COOKIES_FILE.exists():
                cookie_args = ["--cookies", str(COOKIES_FILE)]
            else:
                cookie_args = ["--cookies-from-browser", "chrome"]
            gdl_cmd = [
                *gdl_base,
                *cookie_args,
                "-q",
                "-D", str(work_dir),
                "--filename", "{num:>03}.{extension}",
                url,
            ]
            result = subprocess.run(
                gdl_cmd, capture_output=True, text=True, timeout=GALLERY_TIMEOUT,
            )
            if result.returncode != 0:
                err = (result.stderr or result.stdout)[-300:]
                raise RuntimeError(f"gallery-dl failed: {err}")

            slides = sorted(
                p for p in work_dir.iterdir()
                if p.is_file()
                and not p.name.startswith(".")
                and p.suffix.lower() in MEDIA_EXTS
            )
            if not slides:
                raise RuntimeError("No media found in this post")

            shortcode = urlparse(url).path.strip("/").split("/")[-1] or "instagram"
            base = FS_INVALID_CHARS.sub("_", shortcode).strip()[:80] or "instagram"
            n = len(slides)
            self._ui(lambda: cell.set(status=f"0/{n}", progress=0.0))

            if n == 1:
                self._save_single_slide(slides[0], base, cell)
                return

            preview_thumb = self._make_thumbnail(slides[0])
            if preview_thumb:
                self._ui(lambda t=preview_thumb: cell.set(thumbnail_path=t))

            zip_path = unique_path(self.dest_dir / f"{base}.zip")
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for i, src in enumerate(slides, 1):
                    ext = src.suffix.lower()
                    if ext in IMAGE_EXTS and ext not in JPG_EXTS:
                        jpg_path = work_dir / f"slide_{i}.jpg"
                        self._convert_to_jpg(src, jpg_path)
                        zf.write(jpg_path, f"slide {i}.jpg")
                    elif ext in IMAGE_EXTS:
                        zf.write(src, f"slide {i}.jpg")
                    else:
                        self._ensure_h264(src, cell)
                        zf.write(src, f"slide {i}.mp4")
                    frac = i / n
                    self._ui(lambda i=i, f=frac: cell.set(
                        status=f"{i}/{n}", progress=f,
                    ))

            self._ui(lambda d=zip_path.name, p=zip_path: cell.set(
                name=d, file_path=p, progress=1.0,
            ))
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    def _save_single_slide(self, src: Path, base: str, cell):
        ext = src.suffix.lower()
        if ext in IMAGE_EXTS and ext not in JPG_EXTS:
            out = unique_path(self.dest_dir / f"{base}.jpg")
            self._convert_to_jpg(src, out)
        elif ext in IMAGE_EXTS:
            out = unique_path(self.dest_dir / f"{base}.jpg")
            shutil.move(str(src), str(out))
        else:
            self._ensure_h264(src, cell)
            out = unique_path(self.dest_dir / f"{base}.mp4")
            shutil.move(str(src), str(out))
        self._ui(lambda: cell.set(status="1/1"))
        self._finalize_cell(cell, out)

    def _convert_to_jpg(self, src: Path, out: Path):
        result = subprocess.run(
            [FFMPEG_BIN, "-y", "-i", str(src), "-q:v", JPG_QUALITY, str(out)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"image convert failed: {result.stderr[-200:]}")

    def _extract_mp3(self, path: Path, cell):
        self._ui(lambda: cell.set(status=S_EXTRACTING_MP3))
        mp3_path = path.with_suffix(".mp3")
        if mp3_path.resolve() == path.resolve():
            mp3_path = path.with_name(path.stem + ".converted.mp3")
        result = subprocess.run(
            [FFMPEG_BIN, "-y", "-i", str(path),
             "-vn", "-c:a", "libmp3lame", "-b:a", MP3_BITRATE,
             str(mp3_path)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg mp3 extract failed: {result.stderr[-200:]}")
        return mp3_path

    def _ensure_h264(self, path: Path, cell):
        codec, duration = self._probe_video(path)
        if codec in H264_CODECS:
            return

        self._ui(lambda: cell.set(status=S_WAITING_ENC))
        with ENCODE_LOCK:
            self._ui(lambda: cell.set(status=S_RE_ENCODING))
            tmp = path.with_suffix(".converting.mp4")
            tail = ("-movflags", "+faststart", str(tmp))
            hw_in = ("-hwaccel", "videotoolbox", "-i", str(path))
            sw_in = ("-i", str(path))
            attempts = (
                (hw_in, ("-c:v", "h264_videotoolbox", "-q:v", VT_QUALITY)),
                (hw_in, ("-c:v", "hevc_videotoolbox", "-q:v", VT_QUALITY, "-tag:v", "hvc1")),
                (sw_in, ("-threads", FFMPEG_THREADS, "-c:v", "libx264",
                         "-preset", X264_PRESET, "-crf", X264_CRF)),
            )

            last_err = ""
            for input_args, codec_args in attempts:
                tmp.unlink(missing_ok=True)
                cmd = [FFMPEG_BIN, "-y", *input_args, *codec_args, *AUDIO_ARGS, *tail]
                rc, err = self._run_ffmpeg_progress(cmd, duration, cell)
                if rc == 0:
                    break
                last_err = err
            else:
                tmp.unlink(missing_ok=True)
                raise RuntimeError(f"ffmpeg re-encode failed: {last_err[-300:]}")

            tmp.replace(path)

    @staticmethod
    def _probe_video(path: Path):
        probe = subprocess.run(
            [FFPROBE_BIN, "-v", "error",
             "-show_entries", "stream=codec_name:format=duration",
             "-select_streams", "v:0",
             "-of", "default=noprint_wrappers=1", str(path)],
            capture_output=True, text=True,
        )
        codec = ""
        duration = 0.0
        for line in probe.stdout.splitlines():
            key, _, value = line.partition("=")
            value = value.strip()
            if key == "codec_name":
                codec = value
            elif key == "duration":
                try:
                    duration = float(value)
                except ValueError:
                    pass
        return codec, duration

    def _run_ffmpeg_progress(self, cmd, duration, cell):
        cmd_with_progress = [cmd[0], "-progress", "pipe:1", "-nostats", *cmd[1:]]
        proc = subprocess.Popen(
            cmd_with_progress,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        stderr_buf = []

        def drain_stderr():
            try:
                stderr_buf.extend(proc.stderr)
            except Exception:
                pass

        t = threading.Thread(target=drain_stderr, daemon=True)
        t.start()

        last_status = ""
        try:
            for line in proc.stdout:
                if not line.startswith("out_time_ms="):
                    continue
                try:
                    us = int(line.split("=", 1)[1].strip())
                except (ValueError, IndexError):
                    continue
                elapsed = us / 1_000_000
                if duration > 0:
                    pct = max(0, min(99, int(elapsed * 100 / duration)))
                    status = f"{S_RE_ENCODING} {pct}%"
                    progress = pct / 100
                else:
                    status = f"{S_RE_ENCODING} {int(elapsed)}s"
                    progress = None
                if status != last_status:
                    last_status = status
                    self._ui(lambda s=status, p=progress: cell.set(
                        status=s, progress=p,
                    ))
        finally:
            proc.wait()
            t.join(timeout=1)
        return proc.returncode, "".join(stderr_buf)

    _PCT_RE = re.compile(r"(\d+(?:\.\d+)?)")

    def _make_hook(self, cell):
        def hook(d):
            status = d.get("status")
            if status == "downloading":
                pct_str = (d.get("_percent_str") or "").strip()
                m = self._PCT_RE.search(pct_str)
                progress = float(m.group(1)) / 100 if m else None
                fn = d.get("filename")
                name = Path(fn).name if fn else None
                self._ui(lambda p=pct_str, n=name, pr=progress: cell.set(
                    name=n or cell.name,
                    status=p or "…",
                    progress=pr,
                ))
            elif status == "finished":
                self._ui(lambda: cell.set(status=S_PROCESSING, progress=None))
        return hook


if __name__ == "__main__":
    root = tk.Tk()
    try:
        root.tk_setPalette(background=BG, foreground=FG)
    except tk.TclError:
        pass
    DownloaderApp(root)
    root.mainloop()
