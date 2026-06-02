"""
Video Downloader — standalone GUI for yt-dlp.
Downloads Bilibili, YouTube etc. All output is H.264 mp4, playable in Windows Films & TV.
"""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import yt_dlp


def norm(path: str) -> str:
    return os.path.normpath(path)


def exe_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def find_ffmpeg() -> str | None:
    """Find real ffmpeg.exe binary. Priority: exe dir > system PATH > yt-dlp cache."""
    # 1. Bundled alongside the exe
    bundled = norm(os.path.join(exe_dir(), "ffmpeg.exe"))
    if os.path.isfile(bundled):
        return bundled

    # 2. System PATH (Chocolatey / manual install)
    for d in os.environ.get("PATH", "").split(os.pathsep):
        c = os.path.join(d, "ffmpeg.exe")
        if os.path.isfile(c):
            return c

    # 3. yt-dlp auto-download cache
    for base in (os.path.join(os.path.expanduser("~"), ".cache", "yt-dlp"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "yt-dlp")):
        for root, dirs, files in os.walk(base):
            if "ffmpeg.exe" in files:
                return os.path.join(root, "ffmpeg.exe")

    return None


def needs_transcode(vcodec: str | None) -> bool:
    if not vcodec or vcodec == "none":
        return False
    vc = vcodec.lower()
    return any(tag in vc for tag in ("hev", "hvc", "av1", "av01", "vp9", "vp09"))


class VideoDL:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Video Downloader")
        self.root.geometry("780x680")
        self.root.minsize(640, 500)
        self.root.resizable(True, True)

        self.formats: list[dict] = []
        self.url = ""
        self.msg_queue = queue.Queue()
        self.ffmpeg_path: str | None = find_ffmpeg()

        cookie_path = norm(os.path.join(exe_dir(), "cookies.txt"))
        self._cookie_path = cookie_path if os.path.isfile(cookie_path) else ""

        self.build_ui()
        self.poll_queue()
        self.root.after(300, self._check_ffmpeg)
        self.root.after(500, self._show_disclaimer)

    def _check_ffmpeg(self):
        if self.ffmpeg_path:
            self._log("ffmpeg found: " + self.ffmpeg_path)
            return

        ok = messagebox.askyesno(
            "ffmpeg Required",
            "ffmpeg was not found on this computer.\n\n"
            "ffmpeg is needed to:\n"
            "  - Merge separate video + audio streams\n"
            "  - Transcode HEVC/AV1/VP9 to H.264\n\n"
            "Without ffmpeg, only pre-merged Windows-compatible\n"
            "formats will be available.\n\n"
            "Download ffmpeg automatically? (~50 MB)",
        )
        if ok:
            self._download_ffmpeg_setup()
            self.ffmpeg_path = find_ffmpeg()
            if self.ffmpeg_path:
                self._log("ffmpeg ready: " + self.ffmpeg_path)
            else:
                self._log("ffmpeg download failed. Running in limited mode.")
        else:
            self._log("ffmpeg not available. Running in limited mode.")

    def _show_disclaimer(self):
        messagebox.showinfo(
            "免责声明 / Disclaimer",
            "本软件仅供学习、研究与个人使用，严禁用于任何商业用途。\n"
            "使用者应遵守目标网站的服务条款及相关法律法规，\n"
            "因使用本软件产生的任何法律责任由使用者自行承担。\n\n"
            "This software is for educational and personal use only.\n"
            "Commercial use is strictly prohibited.",
        )

    # ── UI ──────────────────────────────────────────────────

    def build_ui(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill=tk.X)

        ttk.Label(top, text="Video URL:").pack(anchor=tk.W)
        uf = ttk.Frame(top)
        uf.pack(fill=tk.X, pady=(2, 0))
        self.url_var = tk.StringVar()
        ttk.Entry(uf, textvariable=self.url_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(uf, text="Fetch Formats", command=self.on_fetch).pack(side=tk.LEFT, padx=(6, 0))

        mid = ttk.Frame(self.root, padding=10)
        mid.pack(fill=tk.X)

        ttk.Label(mid, text="Output folder:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.out_var = tk.StringVar(value=norm(str(Path.home() / "Downloads")))
        of = ttk.Frame(mid)
        of.grid(row=0, column=1, sticky=tk.EW, pady=2)
        ttk.Entry(of, textvariable=self.out_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(of, text="Browse", command=lambda: self._browse_dir(self.out_var)).pack(side=tk.LEFT, padx=(4, 0))

        ttk.Label(mid, text="Cookies (txt):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.cookie_var = tk.StringVar(value=self._cookie_path)
        cf = ttk.Frame(mid)
        cf.grid(row=1, column=1, sticky=tk.EW, pady=2)
        ttk.Entry(cf, textvariable=self.cookie_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(cf, text="Browse", command=lambda: self._browse_file(self.cookie_var)).pack(side=tk.LEFT, padx=(4, 0))

        ttk.Label(mid, text="Subtitles:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.sub_var = tk.StringVar()
        ttk.Entry(mid, textvariable=self.sub_var).grid(row=2, column=1, sticky=tk.EW, pady=2)
        ttk.Label(mid, text="e.g. en,zh  (blank = no subs)", foreground="gray").grid(row=2, column=1, sticky=tk.E, pady=2)

        ttk.Label(mid, text="Proxy:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.proxy_var = tk.StringVar()
        ttk.Entry(mid, textvariable=self.proxy_var).grid(row=3, column=1, sticky=tk.EW, pady=2)
        ttk.Label(mid, text="e.g. socks5://127.0.0.1:1080", foreground="gray").grid(row=3, column=1, sticky=tk.E, pady=2)

        self.playlist_var = tk.BooleanVar()
        ttk.Checkbutton(mid, text="Download entire playlist", variable=self.playlist_var).grid(row=4, column=1, sticky=tk.W, pady=2)

        mid.columnconfigure(1, weight=1)

        # Format list
        ff = ttk.LabelFrame(self.root, text="Quality / Format  (click to select, then Download)", padding=8)
        ff.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 4))

        cols = ("#", "ID", "Resolution", "Codec", "FPS", "Size", "Bitrate", "Note")
        self.fmt_tree = ttk.Treeview(ff, columns=cols, show="headings", height=10)
        self.fmt_tree.pack(fill=tk.BOTH, expand=True)
        for col, w in zip(cols, [35, 85, 105, 150, 45, 80, 80, 80]):
            self.fmt_tree.heading(col, text=col)
            self.fmt_tree.column(col, width=w, anchor=tk.W)
        vsb = ttk.Scrollbar(self.fmt_tree, orient=tk.VERTICAL, command=self.fmt_tree.yview)
        self.fmt_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Progress
        pf = ttk.LabelFrame(self.root, text="Progress", padding=4)
        pf.pack(fill=tk.X, padx=10, pady=(0, 4))
        self.pbar = ttk.Progressbar(pf, mode="determinate")
        self.pbar.pack(fill=tk.X, pady=(0, 2))
        self.plabel = ttk.Label(pf, text="Ready", foreground="gray")
        self.plabel.pack(anchor=tk.W)

        # Log
        lf = ttk.LabelFrame(self.root, text="Log", padding=4)
        lf.pack(fill=tk.BOTH, expand=False, padx=10, pady=(0, 4))
        self.log_text = tk.Text(lf, height=5, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        ls = ttk.Scrollbar(self.log_text, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=ls.set)
        ls.pack(side=tk.RIGHT, fill=tk.Y)

        bt = ttk.Frame(self.root, padding=10)
        bt.pack(fill=tk.X)
        self.dl_btn = ttk.Button(bt, text="Download", command=self.on_download, state=tk.DISABLED)
        self.dl_btn.pack(side=tk.RIGHT)
        ttk.Button(bt, text="Clear Log", command=self._clear_log).pack(side=tk.LEFT)

        disclaimer = ttk.Label(
            self.root,
            text="免责声明：本软件仅供学习、研究与个人使用，严禁用于任何商业用途。",
            foreground="gray",
            padding=6,
        )
        disclaimer.pack(side=tk.BOTTOM)

    # ── helpers ─────────────────────────────────────────────

    def _emit(self, kind: str, data=None):
        self.msg_queue.put((kind, data))

    def _log_safe(self, msg: str):
        self._emit("log", msg)

    def _error_safe(self, msg: str):
        self._emit("error", msg)

    def _log(self, msg: str):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _clear_log(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def poll_queue(self):
        while True:
            try:
                kind, data = self.msg_queue.get_nowait()
                if kind == "log":
                    self._log(data)
                elif kind == "formats":
                    self._fill_formats(data)
                elif kind == "progress":
                    self._update_progress(data)
                elif kind == "progress_reset":
                    self.pbar["value"] = 0
                    self.plabel.configure(text="Starting...")
                elif kind == "progress_done":
                    self.pbar["value"] = 100
                    self.plabel.configure(text="Complete")
                    self.dl_btn.configure(state=tk.NORMAL)
                    messagebox.showinfo("Done", "Download finished!")
                elif kind == "error":
                    self.dl_btn.configure(state=tk.NORMAL)
                    self.plabel.configure(text="Failed")
                    messagebox.showerror("Error", data)
                elif kind == "ready":
                    self.dl_btn.configure(state=tk.NORMAL)
            except queue.Empty:
                break
        self.root.after(200, self.poll_queue)

    def _fill_formats(self, formats: list):
        self.fmt_tree.delete(*self.fmt_tree.get_children())
        for f in formats:
            fid = f.get("format_id", "")
            w = f.get("width") or ""
            h = f.get("height") or ""
            res = f.get("resolution") or (f"{w}x{h}" if w and h else "")
            vcodec = (f.get("vcodec") or "none")[:24]
            acodec = f.get("acodec") or "none"
            if vcodec != "none" and acodec != "none":
                codec = f"{vcodec}+{acodec}"
            elif vcodec != "none":
                codec = vcodec
            else:
                codec = f"audio:{acodec}"
            note = f.get("format_note", "")
            fps = str(f.get("fps") or "")
            size = f.get("filesize") or f.get("filesize_approx")
            tbr = f.get("tbr") or ""
            size_str = f"{size / 1024 / 1024:.1f} MB" if size else ""
            tbr_str = f"{tbr:.0f} kbps" if tbr else ""
            idx = len(self.fmt_tree.get_children())
            self.fmt_tree.insert("", tk.END, values=(idx, fid, res, codec, fps, size_str, tbr_str, note))

    def _update_progress(self, data: dict):
        s = data.get("_percent_str", "").strip()
        speed = data.get("_speed_str", "").strip()
        eta = data.get("_eta_str", "").strip()
        try:
            pct = float(s.replace("%", ""))
        except (ValueError, AttributeError):
            pct = 0
        self.pbar["value"] = pct
        parts = [s]
        if speed:
            parts.append(speed)
        if eta:
            parts.append(f"ETA {eta}")
        self.plabel.configure(text="  ".join(parts))

    def _browse_dir(self, var: tk.StringVar):
        p = filedialog.askdirectory(initialdir=var.get())
        if p:
            var.set(norm(p))

    def _browse_file(self, var: tk.StringVar):
        p = filedialog.askopenfilename(filetypes=[("Cookies", "*.txt"), ("All files", "*.*")], initialdir=Path.home())
        if p:
            var.set(norm(p))

    # ── Fetch ────────────────────────────────────────────────

    def on_fetch(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Paste a video URL first.")
            return
        self.url = url
        self.dl_btn.configure(state=tk.DISABLED)
        self.fmt_tree.delete(*self.fmt_tree.get_children())
        self._clear_log()
        self._log(f"Fetching formats for: {url}")
        threading.Thread(target=self._fetch_formats, daemon=True).start()

    def _fetch_formats(self):
        opts = {"quiet": True, "no_warnings": True}
        c = self.cookie_var.get().strip()
        if c and Path(c).exists():
            opts["cookiefile"] = c
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
        except Exception as e:
            self._error_safe(str(e))
            return
        self.formats = info.get("formats", [])
        title = info.get("title", "Unknown")
        self._log_safe(f"Title: {title}")

        if not self.ffmpeg_path:
            self.formats = [f for f in self.formats if self._is_direct_playable(f)]
            self._log_safe(f"Found {len(self.formats)} formats (limited mode: pre-merged H.264 only).")
        else:
            self._log_safe(f"Found {len(self.formats)} formats.")
        self._emit("formats", self.formats)
        self._emit("ready", None)

    @staticmethod
    def _is_direct_playable(f: dict) -> bool:
        """Format is ready-to-play without ffmpeg: has video+audio already merged and H.264."""
        vcodec = (f.get("vcodec") or "none").lower()
        acodec = (f.get("acodec") or "none").lower()
        if vcodec == "none" or acodec == "none":
            return False
        if needs_transcode(vcodec):
            return False
        return True

    # ── Download ─────────────────────────────────────────────

    def on_download(self):
        sel = self.fmt_tree.selection()
        if not sel:
            messagebox.showwarning("No Format", "Select a format from the list, then click Download.")
            return
        row = self.fmt_tree.item(sel[0], "values")
        # columns: #, ID, Resolution, Codec, FPS, Size, Bitrate, Note
        fid = row[1]
        vcodec_raw = row[3]  # e.g. "avc1.640032+m4a" or "hev1.2.4.L150.90+m4a"

        self.dl_btn.configure(state=tk.DISABLED)
        self._clear_log()
        self._log(f"Downloading: {self.url}")
        self._log(f"Format: {row[2]}  Codec: {vcodec_raw}")

        # Extract vcodec from the Codec column
        if "+" in vcodec_raw:
            vcodec = vcodec_raw.split("+")[0].split(":")[-1]
        elif vcodec_raw.startswith("audio:"):
            vcodec = "none"
        else:
            vcodec = vcodec_raw
        self._log(f"Video codec: {vcodec}")

        threading.Thread(target=self._download, args=(fid, vcodec), daemon=True).start()

    def _download(self, format_id: str, vcodec: str):
        out = norm(self.out_var.get())
        proxy = self.proxy_var.get().strip()
        cookie = self.cookie_var.get().strip()
        subs = self.sub_var.get().strip()

        if self.ffmpeg_path:
            fmt = f"{format_id}+bestaudio[ext=m4a]/best[ext=mp4]/best"
        else:
            # No ffmpeg: only use the selected pre-merged format, no audio merging
            fmt = format_id

        opts = {
            "outtmpl": str(Path(out) / "%(title)s.%(ext)s"),
            "format": fmt,
            "merge_output_format": "mp4",
            "noplaylist": not self.playlist_var.get(),
            "retries": 10,
            "progress_hooks": [self._on_progress],
            "fixup": "detect_or_warn",
            "sleep_interval": 3,
            "max_sleep_interval": 8,
        }

        if cookie and Path(cookie).exists():
            opts["cookiefile"] = norm(cookie)

        if proxy:
            opts["proxy"] = proxy

        if subs:
            opts["writesubtitles"] = True
            opts["writeautomaticsub"] = True
            opts["subtitleslangs"] = subs.split(",")
            opts["embedsubs"] = True

        if self.ffmpeg_path:
            opts["ffmpeg_location"] = os.path.dirname(self.ffmpeg_path)

        self._emit("progress_reset")

        # Step 1: download + merge via yt-dlp
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                out_file = ydl.prepare_filename(info)
        except Exception as e:
            self._error_safe(str(e))
            return

        # Step 2: if codec is HEVC/AV1/VP9, re-encode to H.264
        if vcodec != "none" and needs_transcode(vcodec) and self.ffmpeg_path:
            self._log_safe(f"Codec {vcodec} not playable on Windows — transcoding to H.264...")
            self._transcode(out_file)
        elif vcodec != "none":
            self._log_safe(f"Codec {vcodec} Windows-compatible, no transcode needed.")

        self._emit("progress_done")

    def _download_ffmpeg_setup(self):
        """Download ffmpeg via PowerShell (handles redirects). Tries GitHub then domestic mirrors.
        Extracts just ffmpeg.exe next to the executable."""
        import zipfile, tempfile

        dest = norm(os.path.join(exe_dir(), "ffmpeg.exe"))
        if os.path.isfile(dest):
            self._log("ffmpeg.exe already bundled, skipping download.")
            return

        urls = [
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
            "https://ghproxy.com/https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
            "https://mirror.ghproxy.com/https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
        ]
        zip_path = os.path.join(tempfile.gettempdir(), "ffmpeg-temp.zip")

        downloaded = False
        for url in urls:
            self._log(f"Trying: {url}")
            try:
                subprocess.run(
                    ["powershell", "-Command",
                     f"Invoke-WebRequest -Uri '{url}' -OutFile '{zip_path}' -UseBasicParsing"],
                    check=True, timeout=600, capture_output=True, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if os.path.getsize(zip_path) > 100_000:
                    downloaded = True
                    break
            except Exception:
                continue

        if not downloaded:
            self._log("All download mirrors failed.")
            return

        self._log("Download complete. Extracting ffmpeg.exe...")
        try:
            with zipfile.ZipFile(zip_path) as zf:
                for name in zf.namelist():
                    if name.endswith("/bin/ffmpeg.exe"):
                        with open(dest, "wb") as f:
                            f.write(zf.read(name))
                        self._log(f"ffmpeg installed: {dest}")
                        break
        except Exception as e:
            self._log(f"Extract failed: {e}")
        finally:
            try:
                os.remove(zip_path)
            except OSError:
                pass

    def _transcode(self, input_file: str):
        """Re-encode to H.264 using ffmpeg (no console window)."""
        tmp = input_file + ".transcoded.mp4"
        cmd = [
            self.ffmpeg_path, "-y",
            "-i", input_file,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "copy",
            "-movflags", "+faststart",
            tmp,
        ]
        self._log_safe("Running ffmpeg re-encode...")
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            subprocess.run(cmd, check=True, capture_output=True, text=True,
                           startupinfo=si, creationflags=subprocess.CREATE_NO_WINDOW)
        except subprocess.CalledProcessError as e:
            self._log_safe(f"Transcode failed: {e.stderr[:300]}")
            if os.path.exists(tmp):
                os.remove(tmp)
            return

        # Atomic replace: keep correct .mp4 extension
        final = os.path.splitext(input_file)[0] + ".mp4"
        if os.path.normcase(final) == os.path.normcase(input_file):
            os.replace(tmp, input_file)
        else:
            os.remove(input_file)
            os.replace(tmp, final)
            input_file = final
        self._log_safe("Transcode complete. Video saved as H.264 mp4.")

    def _on_progress(self, d: dict):
        self._emit("progress", {
            "_percent_str": d.get("_percent_str", ""),
            "_speed_str": d.get("_speed_str", ""),
            "_eta_str": d.get("_eta_str", ""),
        })

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = VideoDL()
    app.run()
