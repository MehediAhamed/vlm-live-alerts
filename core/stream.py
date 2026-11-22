import threading, time
from urllib.parse import urlparse
import cv2

_YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")


def _is_youtube(url):
    host = (urlparse(str(url)).hostname or "").lower().removeprefix("www.")
    return host in _YOUTUBE_HOSTS or host.endswith(".youtube.com") or host.startswith("youtube.")


def _video_url(info):
    if info.get("vcodec") not in (None, "none") and info.get("url"):
        return info["url"]
    for fmt in info.get("requested_formats") or []:
        if fmt.get("vcodec") not in (None, "none") and fmt.get("url"):
            return fmt["url"]
    best, score = None, -1
    for fmt in info.get("formats") or []:
        if fmt.get("vcodec") in (None, "none") or not fmt.get("url"):
            continue
        proto, ext = fmt.get("protocol") or "", fmt.get("ext") or ""
        height = fmt.get("height") or 0
        rank = (50 if ext == "mp4" else 0) + (30 if proto in ("http", "https") else 0)
        rank += 20 if "m3u8" in proto else 0
        rank += 10 if 0 < height <= 720 else 0
        rank += min(height, 720) / 100
        if rank > score:
            best, score = fmt["url"], rank
    return best


def _youtube_media_url(url):
    import yt_dlp
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "b[height<=720][ext=mp4]/b[height<=720]/bv*[height<=720]/b",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise RuntimeError("no stream info")
    if info.get("_type") == "playlist":
        info = next((e for e in info.get("entries") or [] if e), None)
        if not info:
            raise RuntimeError("empty playlist")
    media = _video_url(info)
    if not media:
        raise RuntimeError("no playable video URL")
    return media


class StreamReader:
    def __init__(self, url, delay=2.0):
        self.url = int(url) if str(url).isdigit() else url
        self.delay, self.frame, self.error = delay, None, None
        self._lock, self._stop = threading.Lock(), threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def read(self):
        with self._lock:
            return None if self.frame is None else self.frame.copy()

    def stop(self):
        self._stop.set()

    def _target(self):
        if not isinstance(self.url, str) or not _is_youtube(self.url):
            return self.url
        try:
            return _youtube_media_url(self.url)
        except Exception as exc:
            detail = str(exc).strip().splitlines()[-1][:180]
            self.error = f"YouTube: {detail}"
            return None

    def _run(self):
        while not self._stop.is_set():
            target = self._target()
            if target is None:
                time.sleep(self.delay)
                continue
            cap = cv2.VideoCapture(target) if isinstance(target, int) else cv2.VideoCapture(target, cv2.CAP_FFMPEG)
            self.error = None if cap.isOpened() else f"cannot open {self.url}"
            while cap.isOpened() and not self._stop.is_set():
                ok, f = cap.read()
                if not ok:
                    break
                with self._lock:
                    self.frame = f
            cap.release()
            if not self._stop.is_set():
                time.sleep(self.delay)
