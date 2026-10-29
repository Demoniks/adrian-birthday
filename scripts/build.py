#!/usr/bin/env python3
"""
Build Adrian's birthday letter into  docs/  — the folder GitHub Pages publishes.

    python scripts/build.py              build (re-uses clips that are already encoded)
    python scripts/build.py --force      re-encode every clip and song
    python scripts/build.py --no-ffmpeg  skip ffmpeg, copy browser-ready files as-is

Inputs:   content/story.toml   content/letter.md   media/<section>/...   site_src/
Output:   docs/index.html  docs/assets/  docs/media/
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):  # keep ✓ and → readable in the Windows terminal
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    sys.exit("This project needs Python 3.11 or newer. Get it from https://www.python.org/downloads/ "
             "and pick it in VS Code with  Ctrl/Cmd+Shift+P → 'Python: Select Interpreter'.")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONTENT = ROOT / "content"
MEDIA = ROOT / "media"
SRC = ROOT / "site_src"
OUT = ROOT / "docs"

sys.path.insert(0, str(HERE))
import media as media_mod  # noqa: E402
import render  # noqa: E402


class BuildError(Exception):
    """A problem in the content files — shown to you as a friendly message."""


MEDIA_DEFAULTS = {
    "video_transition": "dip", "video_fade": 0.9, "dim": 0.4, "max_width": 1280, "crf": 26,
    "music_volume": 0.7, "voice_volume": 1.0, "duck": 0.25, "auto_voice": True,
    "normalize_audio": True, "music_bitrate": "160k", "voice_bitrate": "128k",
    "clip_audio": True, "clip_volume": 0.12,
}
FLOW_TYPES = {"hero", "letter", "message", "moment", "spotlight"}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")


# ── loading & checking ────────────────────────────────────────────────
def load_story() -> dict:
    path = CONTENT / "story.toml"
    try:
        story = tomllib.loads(path.read_text("utf-8"))
    except FileNotFoundError:
        raise BuildError("content/story.toml is missing.")
    except tomllib.TOMLDecodeError as e:
        raise BuildError(f"content/story.toml has a typo → {e}\n"
                         "   (common causes: a missing quote, or a \" inside a \"…\" string — use ''' or \\\")")
    story.setdefault("media", {})
    story["media"] = {**MEDIA_DEFAULTS, **story["media"]}
    trim = story.get("trim", {})
    if not isinstance(trim, dict) or not all(isinstance(v, dict) for v in trim.values()):
        raise BuildError('story.toml → [trim] entries look like:  "01-my-clip" = { start = 5.3, end = 209.3 }')
    story["media"]["trim"] = {k.lower(): v for k, v in trim.items()}
    validate(story)
    return story


def validate(story: dict) -> None:
    site = story.get("site", {})
    if not site.get("recipient"):
        raise BuildError("story.toml → [site] needs a recipient name.")
    secs = story.get("sections") or []
    if not secs:
        raise BuildError("story.toml needs at least one [[sections]] block.")
    chars = story.get("characters", {})
    for key, ch in chars.items():
        if "name" not in ch:
            raise BuildError(f"[characters.{key}] needs a name.")
        ch.setdefault("color", "#ffffff")
        if not HEX.match(ch["color"]):
            raise BuildError(f"[characters.{key}] color must look like #ff7a1a (got {ch['color']!r}).")
    seen = set()
    for i, sec in enumerate(secs, 1):
        sid = sec.get("id", "")
        where = f"section #{i} ({sid or 'no id'})"
        if not ID.match(sid):
            raise BuildError(f"{where}: id must be lowercase letters, numbers and dashes, e.g. 'plus-ultra'.")
        if sid in seen:
            raise BuildError(f"two sections use the id '{sid}'.")
        seen.add(sid)
        for k in ("title", "anime"):
            sec.setdefault(k, "")
        for k, default in (("accent", "#ff7a1a"), ("accent2", "#ffd23f")):
            sec.setdefault(k, default)
            if not HEX.match(sec[k]):
                raise BuildError(f"{where}: {k} must look like #ff7a1a (got {sec[k]!r}).")
        for j, q in enumerate(sec.get("quotes", []), 1):
            if q.get("character") not in chars:
                raise BuildError(f"{where}, quote #{j}: character {q.get('character')!r} isn't defined. "
                                 f"Add a [characters.{q.get('character')}] block.")
            if not str(q.get("text", "")).strip():
                raise BuildError(f"{where}, quote #{j}: text is empty.")
            if "at" in q and not isinstance(q["at"], (int, float)):
                raise BuildError(f"{where}, quote #{j}: at must be a number of seconds, e.g. at = 23.6")
        for j, item in enumerate(sec.get("flow", []), 1):
            t = item.get("type")
            if t not in FLOW_TYPES:
                raise BuildError(f"{where}, block #{j}: unknown type {t!r}. Use one of: {', '.join(sorted(FLOW_TYPES))}.")
            if t in ("message", "moment") and item.get("character") not in chars:
                raise BuildError(f"{where}, block #{j}: character {item.get('character')!r} isn't defined. "
                                 f"Add a [characters.{item.get('character')}] block.")


def load_letter() -> list[str]:
    path = CONTENT / "letter.md"
    if not path.exists():
        raise BuildError("content/letter.md is missing.")
    text = path.read_text("utf-8")
    parts = re.split(r"^[ \t]*\[\[\s*next\s*\]\][ \t]*$", text, flags=re.M | re.I)
    parts = [p for p in parts if render.COMMENT_RE.sub("", p).strip()]
    return parts


# ── build ─────────────────────────────────────────────────────────────
def short_hash(*paths: Path) -> str:
    h = hashlib.sha1()
    for p in paths:
        h.update(p.read_bytes())
    return h.hexdigest()[:10]


def build(force: bool = False, use_ffmpeg: bool = True, log=print) -> Path:
    story = load_story()
    parts = load_letter()
    sections = story["sections"]

    OUT.mkdir(exist_ok=True)
    mb = media_mod.MediaBuilder(root=ROOT, src_dir=MEDIA, site_dir=OUT, settings=story["media"],
                                use_ffmpeg=use_ffmpeg, force=force, log=log)
    if use_ffmpeg and not mb.ffmpeg:
        log("⚠  ffmpeg not found — clips are copied as-is (sound NOT stripped, no compression).\n"
            "   Install it for the full pipeline: https://ffmpeg.org/download.html")

    media = {}
    for sec in sections:
        media[sec["id"]] = mb.section(sec["id"])
    report = mb.finish()

    # assets
    assets = OUT / "assets"
    assets.mkdir(exist_ok=True)
    for name in ("style.css", "app.js"):
        shutil.copy2(SRC / name, assets / name)
    version = short_hash(SRC / "style.css", SRC / "app.js")

    template = (SRC / "index.html").read_text("utf-8")
    html_doc, missing_voice = render.page(template, story, parts, media, version)
    (OUT / "index.html").write_text(html_doc, "utf-8")
    (OUT / ".nojekyll").write_text("", "utf-8")

    # summary
    log("✓ built docs/index.html")
    for sec in sections:
        m = media[sec["id"]]
        log(f"   {sec['id']:<14} {len(m['videos'])} clip(s) · {len(m['music'])} song(s) · "
            f"{len(set(m['voice'].values()))} voice line(s)")
    log(f"   letter: {len(parts)} part(s)")
    for line in report:
        log("   " + line)
    for w in [n for n in missing_voice if n.startswith("!")]:  # "!" = a warning, not a missing voice
        log("⚠  " + w[1:])
    missing_voice = [n for n in missing_voice if not n.startswith("!")]
    if missing_voice:
        log(f"   ◦ optional: {len(missing_voice)} card(s)/quote(s) can speak if you add their voice clip, e.g. "
            f"{missing_voice[0]}")
    for w in mb.warnings:
        log("⚠  " + w)
    return OUT


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="re-encode all media")
    ap.add_argument("--no-ffmpeg", action="store_true", help="don't use ffmpeg")
    args = ap.parse_args()
    try:
        build(force=args.force, use_ffmpeg=not args.no_ffmpeg)
    except BuildError as e:
        print(f"✗ {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
