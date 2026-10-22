
import os
import queue
import threading
import time
import webbrowser
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import requests

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False


DEFAULT_DOWNLOAD_DIR = str(Path.home() / "Downloads" / "SelaDownloader")
VIDEO_QUALITIES = ("Terbaik", "2160", "1440", "1080", "720", "480", "360")
AUDIO_QUALITIES = ("320", "256", "192", "128", "96")
IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/avif": ".avif",
    "image/svg+xml": ".svg",
}

def format_duration(seconds):
    """Return a compact human-readable duration from yt-dlp metadata."""
    if not isinstance(seconds, (int, float)) or seconds < 0:
        return "Durasi tidak diketahui"
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"


def preview_details(info):
    """Extract the preview fields the UI can show from a yt-dlp info dict."""
    title = info.get("title") or "Video tanpa judul"
    uploader = info.get("uploader") or info.get("channel") or "Sumber tidak diketahui"
    return {
        "title": title,
        "subtitle": f"{uploader} • {format_duration(info.get('duration'))}",
        "thumbnail": info.get("thumbnail"),
        "url": info.get("webpage_url") or info.get("original_url"),
    }


def progress_details(data):
    """Convert one yt-dlp progress hook event into UI-ready progress text."""
    total = data.get("total_bytes") or data.get("total_bytes_estimate")
    downloaded = data.get("downloaded_bytes", 0)
    percent = min(100, round(downloaded / total * 100)) if total else 0
    speed = data.get("speed") or 0
    eta = data.get("eta")
    details = [f"Mengunduh... {percent}%", f"{speed / 1024:.0f} KB/dtk"]
    if isinstance(eta, (int, float)) and eta >= 0:
        details.append(f"sisa {int(eta)} dtk")
    return {"percent": percent, "status": " • ".join(details)}


class _ImageParser(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base = base
        self.images = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        candidate = None
        if tag == "meta" and attrs.get("property", "").lower() in ("og:image", "og:image:url", "twitter:image"):
            candidate = attrs.get("content")
        elif tag in ("img", "source"):
            srcset = attrs.get("srcset") or attrs.get("data-srcset")
            if srcset:
                candidate = srcset.split(",")[-1].strip().split()[0]
            else:
                candidate = attrs.get("data-src") or attrs.get("src")
        if candidate:
            url = urljoin(self.base, candidate)
            if urlsplit(url).scheme in ("http", "https") and url not in self.images:
                self.images.append(url)


def page_images(html, url):
    parser = _ImageParser(url)
    parser.feed(html)
    return parser.images


class DownloaderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Sela Downloader")
        self.geometry("780x660")
        self.minsize(620, 600)

        self.log_queue = queue.Queue()
        self.ui_queue = queue.Queue()
        self.preview_url = None
        self.dest_dir = tk.StringVar(value=DEFAULT_DOWNLOAD_DIR)
        self.mode = tk.StringVar(value="video")  # video | audio | photo | file
        self.url_var = tk.StringVar()
        self.video_quality = tk.StringVar(value="Terbaik")
        self.audio_quality = tk.StringVar(value="192")

        self._build_ui()
        self.after(150, self._poll_log_queue)

    # ---------------------------------------------------------------- UI ---
    def _build_ui(self):
        # Shared ttk styles keep keyboard focus and native control semantics.
        bg, paper, ink = "#F6F5F1", "#FFFFFF", "#252D33"
        muted, accent, border = "#53636B", "#326782", "#CED5D8"
        self.configure(background=bg)
        self.option_add("*Font", "{Segoe UI} 10")
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=ink)
        style.configure("Title.TLabel", font=("Segoe UI", 24, "bold"))
        style.configure("Muted.TLabel", foreground=muted)
        style.configure("Section.TLabel", font=("Segoe UI", 10, "bold"))
        style.configure("TEntry", padding=10, fieldbackground=paper,
                        foreground=ink, bordercolor=border)
        style.map("TEntry", bordercolor=[("focus", accent)])
        style.configure("TButton", padding=(16, 10), background=paper,
                        foreground=ink, bordercolor=border)
        style.map("TButton", background=[("active", "#E4ECEF")],
                  bordercolor=[("focus", accent)])
        style.configure("Primary.TButton", background=accent, foreground=paper,
                        font=("Segoe UI", 11, "bold"))
        style.map("Primary.TButton", background=[("disabled", "#D7DFDF"),
                  ("pressed", "#244E63"), ("active", "#295870")],
                  foreground=[("disabled", muted)])
        style.configure("Mode.TRadiobutton", background=bg, foreground=ink,
                        padding=(0, 8, 18, 8))
        style.map("Mode.TRadiobutton", background=[("active", bg)])
        style.configure("Horizontal.TProgressbar", background=accent,
                        troughcolor="#DCE5E5", borderwidth=0)

        body = ttk.Frame(self, padding=28)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(13, weight=1)
        ttk.Label(body, text="Sela Downloader", style="Title.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Label(body, text="Tempel tautan. Pilih yang ingin disimpan.",
                  style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 24))

        ttk.Label(body, text="Tautan media", style="Section.TLabel").grid(
            row=2, column=0, sticky="w", pady=(0, 6))
        url_entry = ttk.Entry(body, textvariable=self.url_var, font=("Segoe UI", 12))
        url_entry.grid(row=3, column=0, sticky="ew")
        url_entry.focus_set()

        modes = ttk.Frame(body)
        modes.grid(row=4, column=0, sticky="ew", pady=(8, 16))
        for label, value in (
            ("Video", "video"),
            ("Audio", "audio"),
            ("Foto halaman", "photo"),
            ("File langsung", "file"),
        ):
            ttk.Radiobutton(
                modes,
                text=label,
                variable=self.mode,
                value=value,
                style="Mode.TRadiobutton",
            ).pack(side="left")
        quality = ttk.Frame(body)
        quality.grid(row=5, column=0, sticky="w", pady=(0, 12))
        self.video_control = ttk.Frame(quality)
        ttk.Label(self.video_control, text="Batas resolusi").pack(side="left", padx=(0, 8))
        ttk.Combobox(
            self.video_control,
            textvariable=self.video_quality,
            state="readonly",
            width=10,
            values=VIDEO_QUALITIES,
        ).pack(side="left")
        self.audio_control = ttk.Frame(quality)
        ttk.Label(self.audio_control, text="MP3 kbps").pack(side="left", padx=(0, 8))
        ttk.Combobox(
            self.audio_control,
            textvariable=self.audio_quality,
            state="readonly",
            width=10,
            values=AUDIO_QUALITIES,
        ).pack(side="left")
        self.mode.trace_add("write", self._update_quality)
        self._update_quality()

        self.preview_frame = ttk.Frame(body)
        self.preview_frame.grid(row=6, column=0, sticky="ew", pady=(0, 12))
        self.preview_frame.columnconfigure(0, weight=1)
        ttk.Label(self.preview_frame, text="Preview video", style="Section.TLabel").grid(
            row=0, column=0, sticky="w")
        self.preview_title = tk.StringVar(value="Tempel link video untuk melihat judul dan durasinya.")
        self.preview_meta = tk.StringVar(value="")
        ttk.Label(self.preview_frame, textvariable=self.preview_title, font=("Segoe UI", 10, "bold"),
                  wraplength=540).grid(row=1, column=0, sticky="w", pady=(5, 0))
        ttk.Label(self.preview_frame, textvariable=self.preview_meta, style="Muted.TLabel").grid(
            row=2, column=0, sticky="w", pady=(2, 0))
        self.btn_open_preview = ttk.Button(self.preview_frame, text="Buka preview", command=self._open_preview,
                                           state="disabled")
        self.btn_open_preview.grid(row=1, column=1, rowspan=2, sticky="e", padx=(12, 0))

        ttk.Label(body, text="Folder tujuan", style="Section.TLabel").grid(
            row=7, column=0, sticky="w", pady=(0, 6))
        destination = ttk.Frame(body)
        destination.grid(row=8, column=0, sticky="ew")
        destination.columnconfigure(0, weight=1)
        ttk.Entry(destination, textvariable=self.dest_dir).grid(
            row=0, column=0, sticky="ew")
        ttk.Button(destination, text="Pilih folder", command=self._choose_folder).grid(
            row=0, column=1, padx=(10, 0))

        actions = ttk.Frame(body)
        actions.grid(row=9, column=0, sticky="ew", pady=(22, 12))
        actions.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="Siap mengunduh.")
        ttk.Label(actions, textvariable=self.status_var, style="Muted.TLabel",
                  wraplength=350).grid(row=0, column=0, sticky="w")
        self.btn_download = ttk.Button(actions, text="Unduh sekarang",
                                       style="Primary.TButton", command=self._start_download)
        self.btn_download.grid(row=0, column=1, sticky="e")
        self.progress = ttk.Progressbar(body, mode="determinate")
        self.progress.grid(row=10, column=0, sticky="ew")
        ttk.Label(body, text="Foto: gambar dalam HTML halaman; konten setelah interaksi mungkin tidak muncul.",
                  style="Muted.TLabel").grid(row=11, column=0, sticky="w", pady=(8, 18))
        ttk.Label(body, text="Aktivitas unduhan", style="Section.TLabel").grid(
            row=12, column=0, sticky="w", pady=(0, 8))
        log_frame = ttk.Frame(body)
        log_frame.grid(row=13, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_box = tk.Text(log_frame, height=5, width=1, state="disabled", wrap="word",
                               background=paper, foreground=ink, relief="flat",
                               padx=12, pady=10, highlightthickness=1,
                               highlightbackground=border, highlightcolor=accent)
        self.log_box.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_box.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_box.configure(yscrollcommand=scrollbar.set)

    def _update_quality(self, *_):
        self.video_control.pack_forget()
        self.audio_control.pack_forget()
        if self.mode.get() == "video":
            self.video_control.pack(anchor="w")
        elif self.mode.get() == "audio":
            self.audio_control.pack(anchor="w")

    def _choose_folder(self):
        folder = filedialog.askdirectory(initialdir=self.dest_dir.get() or ".")
        if folder:
            self.dest_dir.set(folder)

    # ------------------------------------------------------------- Logging --
    def _log(self, msg: str):
        self.log_queue.put(msg)

    def _poll_log_queue(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get_nowait()
            self.log_box.configure(state="normal")
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        while not self.ui_queue.empty():
            event, value = self.ui_queue.get_nowait()
            if event == "status":
                self.status_var.set(value)
            elif event == "progress":
                self.progress["value"] = value
            elif event == "button":
                self.btn_download.config(state=value)
            elif event == "preview":
                self.preview_title.set(value["title"])
                self.preview_meta.set(value["subtitle"])
                self.preview_url = value["url"]
                self.btn_open_preview.config(state="normal" if self.preview_url else "disabled")
        self.after(150, self._poll_log_queue)

    def _set_status(self, text: str) -> None:
        self.ui_queue.put(("status", text))

    def _set_progress(self, value: float) -> None:
        self.ui_queue.put(("progress", max(0, min(100, value))))

    def _open_preview(self):
        if self.preview_url:
            webbrowser.open_new_tab(self.preview_url)

    def _load_preview(self, url: str) -> None:
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
                info = ydl.extract_info(url, download=False)
            self.ui_queue.put(("preview", preview_details(info)))
        except Exception as error:
            self._log(f"Preview tidak tersedia: {error}")

    def _queue_button_state(self, state):
        self.ui_queue.put(("button", state))

    # ---------------------------------------------------------- Download ---
    def _start_download(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Perhatian", "Masukkan link terlebih dahulu.")
            return

        dest = self.dest_dir.get().strip() or DEFAULT_DOWNLOAD_DIR
        os.makedirs(dest, exist_ok=True)

        mode = self.mode.get()

        if mode in ("video", "audio") and not YT_DLP_AVAILABLE:
            messagebox.showerror(
                "yt-dlp belum terpasang",
                "Jalankan: pip install -r requirements.txt",
            )
            return

        self.btn_download.config(state="disabled")
        self._set_progress(0)
        self._set_status("Memulai...")
        self._log(f"--- Mulai unduh ({mode}): {url}")

        if mode in ("video", "audio"):
            self.preview_title.set("Memuat preview video...")
            self.preview_meta.set("")
            self.preview_url = None
            self.btn_open_preview.config(state="disabled")
            threading.Thread(target=self._load_preview, args=(url,), daemon=True).start()

        download_thread = threading.Thread(
            target=self._download_worker,
            args=(url, dest, mode, self.video_quality.get(), self.audio_quality.get()),
            daemon=True,
        )
        download_thread.start()

    def _download_worker(self, url, dest, mode, video_quality, audio_quality):
        try:
            if mode == "file":
                self._download_direct_file(url, dest)
            elif mode == "photo":
                self._download_photos(url, dest)
            else:
                self._download_with_ytdlp(url, dest, mode, video_quality, audio_quality)
            self._set_status("Selesai ✔")
            self._log("--- Selesai.")
        except Exception as e:
            self._set_status("Gagal ✗")
            self._log(f"ERROR: {e}")
            messagebox.showerror("Gagal mengunduh", str(e))
        finally:
            self._queue_button_state("normal")

    # -- gambar / file langsung via requests, streaming + progress --
    def _download_direct_file(self, url, dest):
        headers = {"User-Agent": "Mozilla/5.0 (SelaDownloader/1.0)"}
        with requests.get(url, headers=headers, stream=True, timeout=30) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            filename = url.split("?")[0].rstrip("/").split("/")[-1] or "download"
            filepath = Path(dest) / filename
            downloaded = 0
            start = time.time()
            with open(filepath, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded / total * 100
                        self._set_progress(pct)
                        speed = downloaded / max(time.time() - start, 0.01) / 1024
                        self._set_status(f"{pct:.0f}%  ({speed:.0f} KB/s)")
            self._log(f"Tersimpan: {filepath}")

    def _download_photos(self, url, dest):
        with requests.Session() as session:
            response = session.get(url, timeout=30)
            response.raise_for_status()
            images = page_images(response.text, response.url)
            if not images:
                raise ValueError("Tidak ada gambar di HTML halaman")
            saved = failed = 0
            for index, image_url in enumerate(images, 1):
                try:
                    with session.get(image_url, headers={"Referer": response.url}, stream=True, timeout=30) as image:
                        image.raise_for_status()
                        content_type = image.headers.get("content-type", "").split(";", 1)[0].lower()
                        if content_type not in IMAGE_EXTENSIONS:
                            raise ValueError(
                                f"Bukan gambar: {content_type or 'tipe tidak diketahui'}"
                            )
                        name = Path(urlsplit(image_url).path).name or f"foto-{index}"
                        suffix = Path(name).suffix.lower()
                        if suffix not in IMAGE_EXTENSIONS.values():
                            name += IMAGE_EXTENSIONS[content_type]
                        path = Path(dest) / name
                        stem, ext = path.stem, path.suffix
                        number = 2
                        while path.exists():
                            path = Path(dest) / f"{stem}-{number}{ext}"
                            number += 1
                        with path.open("xb") as output:
                            for chunk in image.iter_content(65536):
                                output.write(chunk)
                        saved += 1
                        self._log(f"Tersimpan: {path}")
                except (requests.RequestException, ValueError, OSError) as error:
                    failed += 1
                    self._log(f"Gagal: {image_url}: {error}")
                self._set_progress(index / len(images) * 100)
                self._set_status(f"Foto: {saved} tersimpan, {failed} gagal ({index}/{len(images)})")
            if not saved:
                raise ValueError(f"Tidak ada foto tersimpan; {failed} gagal")
            self._log(f"Foto selesai: {saved} tersimpan, {failed} gagal")

    # -- video/audio via yt-dlp --
    def _download_with_ytdlp(self, url, dest, mode, video_quality, audio_quality):
        outtmpl = str(Path(dest) / "%(title)s.%(ext)s")

        def hook(data):
            if data["status"] == "downloading":
                details = progress_details(data)
                self._set_progress(details["percent"])
                self._set_status(details["status"])
            elif data["status"] == "finished":
                self._set_progress(100)
                self._set_status("Memproses file...")
                self._log(f"Selesai unduh mentah: {data.get('filename')}")

        ydl_opts = {
            "outtmpl": outtmpl,
            "progress_hooks": [hook],
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
        }

        if mode == "audio":
            ydl_opts.update(
                {
                    "format": "bestaudio/best",
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": audio_quality,
                        }
                    ],
                }
            )
        else:  # video
            if video_quality not in VIDEO_QUALITIES:
                raise ValueError("Resolusi video tidak valid")
            height_filter = "" if video_quality == "Terbaik" else f"[height<={int(video_quality)}]"
            ydl_opts.update(
                {
                    "format": f"bestvideo{height_filter}+bestaudio/best{height_filter}",
                    "merge_output_format": "mp4",
                }
            )

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "file")
            self._log(f"Judul: {title}")


if __name__ == "__main__":
    app = DownloaderApp()
    app.mainloop()
