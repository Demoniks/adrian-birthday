"""
Media pipeline — turns your raw clips and songs into small, web-ready files.

  media/<section>/videos/*  →  docs/media/<section>/videos/*.mp4   (H.264, ≤ max_width, audio kept if clip_audio)
  media/<section>/music/*   →  docs/media/<section>/music/*.mp3    (loudness-normalized)
  media/<section>/voice/*   →  docs/media/<section>/voice/*.mp3    (audio pulled out of videos too)

Uses ffmpeg when it's installed. Without it, files browsers can already play are
copied as-is and everything else is skipped with a warning.
Already-encoded files are reused, so rebuilding is fast.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".wmv", ".flv"}
AUDIO_EXT = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".oga", ".opus", ".flac", ".wma"}
WEB_VIDEO = {".mp4", ".webm", ".m4v"}
WEB_AUDIO = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".opus"}

WARN_MB = 50    # GitHub warns above 50 MB
LIMIT_MB = 95   # and rejects files above 100 MB


def natural_key(p: Path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


def slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-._").lower()
    return s or "file"


class MediaBuilder:
    def __init__(self, *, root: Path, src_dir: Path, site_dir: Path, settings: dict,
                 use_ffmpeg: bool = True, force: bool = False, log=print):
        self.root = root
        self.src_dir = src_dir
        self.site_dir = site_dir
        self.out_dir = site_dir / "media"
        self.s = settings
        self.ffmpeg = shutil.which("ffmpeg") if use_ffmpeg else None
        self.force = force
        self.log = log
        self.cache_path = root / ".build-cache.json"
        try:
            self.cache = json.loads(self.cache_path.read_text("utf-8"))
        except Exception:
            self.cache = {}
        self.produced: set[Path] = set()
        self.stats = {"encoded": 0, "reused": 0, "copied": 0}
        self.warnings: list[str] = []

    # ── public ────────────────────────────────────────────────────────
    def section(self, sec_id: str) -> dict:
        base = self.src_dir / sec_id
        out = self.out_dir / sec_id
        for sub in ("videos", "music", "voice"):
            (base / sub).mkdir(parents=True, exist_ok=True)

        result = {"videos": [], "music": [], "voice": {}, "poster": None}
        jobs = (
            ("video", "videos", VIDEO_EXT),
            ("music", "music", AUDIO_EXT),
            ("voice", "voice", AUDIO_EXT | VIDEO_EXT),
        )
        for kind, sub, exts in jobs:
            taken: set[str] = set()
            for src in self._files(base / sub, exts):
                dest = self._process(src, out / sub, kind, taken)
                if not dest:
                    continue
                url = self.url(dest)
                if kind == "video":
                    start, end = self.trim(src)
                    result["videos"].append({"src": url, "name": src.stem.lower(), "start": start, "end": end})
                elif kind == "music":
                    result["music"].append(url)
                else:
                    result["voice"][src.stem.lower()] = url
                    result["voice"].setdefault(dest.stem.lower(), url)

        if result["videos"] and self.ffmpeg:
            first = self.site_dir / result["videos"][0]["src"]
            poster = self._poster(first, out / "poster.jpg")
            if poster:
                result["poster"] = self.url(poster)
        return result

    def trim(self, src: Path) -> tuple[float, float | None]:
        """(start, end) seconds to keep from a clip, from the [trim] table in story.toml."""
        t = self.s.get("trim", {}).get(src.stem.lower()) or {}
        start = max(0.0, float(t.get("start", 0) or 0))
        end = t.get("end")
        return start, (float(end) if end is not None else None)

    def url(self, path: Path) -> str:
        return path.relative_to(self.site_dir).as_posix()

    def finish(self) -> list[str]:
        """Delete outputs whose source is gone, save the cache, report big files."""
        if self.out_dir.exists():
            for f in sorted(self.out_dir.rglob("*"), reverse=True):
                if f.is_file() and f not in self.produced:
                    f.unlink()
                elif f.is_dir() and not any(f.iterdir()):
                    f.rmdir()
        keep = {p.relative_to(self.out_dir).as_posix() for p in self.produced}
        self.cache = {k: v for k, v in self.cache.items() if k in keep}
        self.cache_path.write_text(json.dumps(self.cache, indent=1), "utf-8")

        report = []
        total = 0
        for f in self.produced:
            if not f.exists():
                continue
            mb = f.stat().st_size / 1_048_576
            total += mb
            rel = self.url(f)
            if mb > LIMIT_MB:
                self.warnings.append(f"{rel} is {mb:.0f} MB — GitHub rejects files over 100 MB. "
                                     f"Trim the clip or raise 'crf' in story.toml.")
            elif mb > WARN_MB:
                self.warnings.append(f"{rel} is {mb:.0f} MB — consider a shorter clip.")
        if self.produced:
            report.append(f"media total: {total:.1f} MB "
                          f"({self.stats['encoded']} encoded, {self.stats['reused']} reused, "
                          f"{self.stats['copied']} copied)")
        return report

    # ── internals ─────────────────────────────────────────────────────
    def _files(self, folder: Path, exts: set[str]) -> list[Path]:
        if not folder.is_dir():
            return []
        files = [p for p in folder.iterdir()
                 if p.is_file() and p.suffix.lower() in exts
                 and not p.name.startswith(".") and ".tmp." not in p.name]
        return sorted(files, key=natural_key)

    def _dest(self, folder: Path, stem: str, ext: str, taken: set[str]) -> Path:
        base = slug(stem)
        name, i = base + ext, 2
        while name in taken:
            name, i = f"{base}-{i}{ext}", i + 1
        taken.add(name)
        return folder / name

    def _sig(self, src: Path, kind: str, mode: str) -> str:
        st = src.stat()
        s = self.s
        opts = {
            "video": (s["max_width"], s["crf"], s["clip_audio"], self.trim(src)),
            "music": (s["music_bitrate"], s["normalize_audio"]),
            "voice": (s["voice_bitrate"], s["normalize_audio"]),
        }[kind]
        return f"{st.st_size}:{st.st_mtime_ns}:{kind}:{opts}:{mode}"

    def _fresh(self, src: Path, dest: Path, kind: str, mode: str) -> bool:
        key = dest.relative_to(self.out_dir).as_posix()
        if not self.force and dest.exists() and self.cache.get(key) == self._sig(src, kind, mode):
            self.produced.add(dest)
            self.stats["reused"] += 1
            return True
        return False

    def _remember(self, src: Path, dest: Path, kind: str, mode: str) -> None:
        self.cache[dest.relative_to(self.out_dir).as_posix()] = self._sig(src, kind, mode)
        self.produced.add(dest)

    def _process(self, src: Path, folder: Path, kind: str, taken: set[str]) -> Path | None:
        rel = src.relative_to(self.root).as_posix()
        if self.ffmpeg:
            dest = self._dest(folder, src.stem, ".mp4" if kind == "video" else ".mp3", taken)
            if self._fresh(src, dest, kind, "ff"):
                return dest
            self.log(f"   encoding  {rel}")
            if self._encode(src, dest, kind):
                self._remember(src, dest, kind, "ff")
                self.stats["encoded"] += 1
                return dest
            taken.discard(dest.name)

        web = WEB_VIDEO if kind == "video" else WEB_AUDIO
        if src.suffix.lower() in web:
            dest = self._dest(folder, src.stem, src.suffix.lower(), taken)
            if self._fresh(src, dest, kind, "copy"):
                return dest
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            self._remember(src, dest, kind, "copy")
            self.stats["copied"] += 1
            return dest

        self.warnings.append(f"skipped {rel} — browsers can't play {src.suffix} files. "
                             f"Install ffmpeg and the build will convert it.")
        return None

    def _encode(self, src: Path, dest: Path, kind: str) -> bool:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.stem + ".tmp" + dest.suffix)
        s = self.s
        cmd = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
        start, end = self.trim(src) if kind == "video" else (0.0, None)
        if start:
            cmd += ["-ss", f"{start:.3f}"]
        if end is not None:
            cmd += ["-t", f"{max(0.5, end - start):.3f}"]
        cmd += ["-i", str(src), "-map_metadata", "-1", "-sn", "-dn"]
        if kind == "video":
            w = int(s["max_width"])
            # keep the clip's own sound (played quietly on the page) or strip it
            if s["clip_audio"]:
                cmd += ["-c:a", "aac", "-b:a", "96k", "-ac", "2"]
                if end is not None:  # soft edges where the clip was cut
                    d = max(0.5, end - start)
                    cmd += ["-af", f"afade=t=in:d=0.4,afade=t=out:st={max(0, d - 1):.2f}:d=1"]
            else:
                cmd += ["-an"]
            cmd += ["-vf", f"scale='trunc(min({w},iw)/2)*2':-2:flags=lanczos,fps=30,format=yuv420p",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", str(int(s["crf"])),
                    "-movflags", "+faststart", str(tmp)]
        else:
            loud = -20 if kind == "music" else -15   # voice sits a bit hotter than the music bed
            cmd += ["-vn", "-ac", "2", "-ar", "44100"]
            if s["normalize_audio"]:
                cmd += ["-af", f"loudnorm=I={loud}:TP=-1.5:LRA=11"]
            br = s["music_bitrate"] if kind == "music" else s["voice_bitrate"]
            cmd += ["-c:a", "libmp3lame", "-b:a", str(br), str(tmp)]

        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                           text=True, errors="replace")
        if r.returncode == 0 and tmp.exists() and tmp.stat().st_size > 0:
            tmp.replace(dest)
            return True
        tmp.unlink(missing_ok=True)
        tail = " / ".join((r.stderr or "").strip().splitlines()[-2:]) or "unknown error"
        self.warnings.append(f"ffmpeg couldn't convert {src.name}: {tail}")
        return False

    def _poster(self, video: Path, poster: Path) -> Path | None:
        """A still frame for link previews (the image that shows when you text him the URL)."""
        self.produced.add(poster)
        if poster.exists() and poster.stat().st_mtime >= video.stat().st_mtime and not self.force:
            return poster
        for t in ("1", "0"):
            r = subprocess.run([self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", t,
                                "-i", str(video), "-frames:v", "1", "-vf", "scale=1200:-2",
                                "-q:v", "4", str(poster)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if r.returncode == 0 and poster.exists() and poster.stat().st_size > 0:
                return poster
        self.produced.discard(poster)
        return None
