"""
HTML rendering — turns story.toml + letter.md into the page.
Pure functions: no file access here (build.py does the I/O).
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
BULLET_RE = re.compile(r"^[-*•]\s+")

ICON_SOUND_ON = ('<svg class="i-on" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9H4z"/>'
                 '<path d="M16 8.5a5 5 0 0 1 0 7M18.5 6a8.5 8.5 0 0 1 0 12" fill="none"/></svg>')
ICON_SOUND_OFF = ('<svg class="i-off" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9H4z"/>'
                  '<path d="M16.5 9.5l5 5M21.5 9.5l-5 5" fill="none"/></svg>')
ICON_PLAY = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>'


# ── text helpers ──────────────────────────────────────────────────────
def esc(s) -> str:
    return html.escape(str(s), quote=True)


def fill(text: str, site: dict) -> str:
    for key in ("recipient", "sender", "nickname"):
        text = text.replace("{" + key + "}", str(site.get(key, "")))
    return text


def inline(text: str) -> str:
    t = html.escape(text, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])", r"<em>\1</em>", t)
    return t


def _cls(*names: str) -> str:
    names = [n for n in names if n]
    return f' class="{" ".join(names)}"' if names else ""


def markdown(text: str, line_class: str = "") -> str:
    """Tiny markdown: paragraphs, # headings, > quotes, - lists, — signature, **bold**, *italic*."""
    text = COMMENT_RE.sub("", text).replace("\r\n", "\n")
    out = []
    for block in re.split(r"\n[ \t]*\n", text.strip()):
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        first = lines[0]
        if first.startswith("#"):
            out.append(f"<h3{_cls(line_class)}>{inline(first.lstrip('#').strip())}</h3>")
            lines = lines[1:]
            if not lines:
                continue
            first = lines[0]
        if all(ln.startswith(">") for ln in lines):
            body = "<br>".join(inline(ln.lstrip(">").strip()) for ln in lines)
            out.append(f"<blockquote{_cls(line_class)}>{body}</blockquote>")
        elif all(re.match(r"[-*•]\s+", ln) for ln in lines):
            items = "".join("<li>" + inline(BULLET_RE.sub("", ln)) + "</li>" for ln in lines)
            out.append(f"<ul{_cls(line_class)}>{items}</ul>")
        elif first.startswith(("—", "– ", "-- ")):
            # the leading dash only marks the signature; it isn't shown
            body = "<br>".join(inline(re.sub(r"^(—|–|--)\s*", "", ln)) for ln in lines)
            out.append(f"<p{_cls(line_class, 'sig')}>{body}</p>")
        else:
            out.append(f"<p{_cls(line_class)}>{'<br>'.join(inline(ln) for ln in lines)}</p>")
    return "\n".join(out)


def theme_vars(sec: dict) -> str:
    return f"--a:{sec['accent']};--b:{sec['accent2']}"


# ── blocks ────────────────────────────────────────────────────────────
def gate(story: dict, first: dict) -> str:
    site, g = story["site"], story.get("gate", {})
    name = site["recipient"]
    return f"""
<div id="gate" role="dialog" aria-modal="true" aria-labelledby="gate-name" style="{theme_vars(first)}">
  <div class="gate-card glass">
    <p class="gate-k">{esc(fill(g.get('kicker', 'A letter for'), site))}</p>
    <p id="gate-name" class="gate-name" style="--n:{len(name)}">{esc(name)}</p>
    <p class="gate-from">{esc(fill(g.get('from', 'from {sender}'), site))}</p>
    <button id="gate-btn" class="gate-btn" type="button" autofocus>{esc(g.get('button', 'Open it'))}</button>
    <p class="gate-hint">{ICON_SOUND_ON}<span>{esc(fill(g.get('hint', 'Sound on.'), site))}</span></p>
  </div>
</div>"""


def hero(site: dict) -> str:
    name = site["recipient"]
    tags = []
    if site.get("nickname"):
        tags.append(f"a.k.a. {esc(fill(site['nickname'], site))}")
    if site.get("date_line"):
        tags.append(esc(site["date_line"]))
    tag_html = (f'<p class="hero-tag glass reveal">{" <i>·</i> ".join(tags)}</p>' if tags else "")
    return f"""
<header class="hero">
  <div class="hero-inner">
    <p class="hero-jp reveal">{esc(site.get('hero_jp', ''))}</p>
    <h1 class="hero-title">
      <span class="l1 reveal">{esc(site.get('hero_top', 'Happy Birthday'))}</span>
      <span class="name reveal" style="--n:{len(name)}">{esc(name)}</span>
    </h1>
    {tag_html}
  </div>
  <div class="cue" aria-hidden="true"><span>scroll</span><i></i></div>
</header>"""


def chapter_head(sec: dict, n: int, site: dict) -> str:
    tagline = (f'<p class="chap-tag">{inline(fill(sec["tagline"], site))}</p>' if sec.get("tagline") else "")
    return f"""
<header class="chap-head reveal">
  <span class="chap-num" aria-hidden="true">{n:02d}</span>
  <p class="chap-jp">{esc(sec.get('jp', ''))}</p>
  <h2 class="chap-title">{esc(sec['title'])}</h2>
  <p class="chap-anime">{esc(sec['anime'])}</p>
  {tagline}
</header>"""


def _voice_attrs(url: str | None) -> tuple[str, str]:
    if not url:
        return "", ""
    btn = (f'<button class="voice-btn" type="button">{ICON_PLAY}'
           f'<span class="eq" aria-hidden="true"><i></i><i></i><i></i><i></i></span>'
           f'<span class="vb-l">Hear it</span></button>')
    return f' data-voice="{esc(url)}"', btn


def message(item: dict, ch: dict, site: dict, side: str, voice_url: str | None) -> str:
    attrs, btn = _voice_attrs(voice_url)
    return f"""
<article class="card glass message reveal lean-{side}{' voiced' if voice_url else ''}" style="--c:{ch['color']}"{attrs}>
  <div class="avatar" aria-hidden="true"><span>{esc(ch.get('initials', ch['name'][:2]))}</span></div>
  <div class="msg">
    <header><h3 class="who">{esc(ch['name'])}</h3><span class="chip">{esc(ch.get('anime', ''))}</span></header>
    <div class="msg-body">{markdown(fill(item.get('text', ''), site))}</div>
    {btn}
  </div>
</article>"""


def moment(item: dict, ch: dict, site: dict, side: str, voice_url: str | None) -> str:
    attrs, btn = _voice_attrs(voice_url)
    short = ch.get("short", ch["name"])
    line = (item.get("line") or "").strip()
    lesson = fill((item.get("lesson") or "").strip(), site)
    big = ""
    if line:
        big += f'<blockquote class="line">“{inline(line)}”<cite>{esc(short)}</cite></blockquote>'
    if lesson:
        big += f'<p class="lesson{" small" if line else ""}">{inline(lesson)}</p>'
    to = item.get("to", "")
    arrow = f' <span class="arrow">→</span> {esc(to)}' if to else ""
    return f"""
<article class="card glass moment reveal lean-{side}{' voiced' if voice_url else ''}" style="--c:{ch['color']}"{attrs}>
  <p class="k">The moment · {esc(ch.get('anime', ''))}</p>
  <h3>{esc(short)}{arrow}</h3>
  <p class="when">{esc(item.get('when', ''))}</p>
  <p class="scene">{inline(fill(item.get('scene', ''), site))}</p>
  {big}
  {btn}
</article>"""


def spotlight(item: dict, site: dict, side: str) -> str:
    points = "".join(f"<li>{inline(fill(p, site))}</li>" for p in item.get("points", []))
    intro = f'<p class="sp-intro">{inline(fill(item["intro"], site))}</p>' if item.get("intro") else ""
    return f"""
<article class="card glass spotlight reveal lean-{side}">
  <h3>{inline(fill(item.get('title', ''), site))}</h3>
  {intro}
  <ul>{points}</ul>
</article>"""


def letter(part_md: str, index: int, total: int, site: dict) -> str:
    label = "The letter" + (f" · {ROMAN[index] if index < len(ROMAN) else index + 1}" if total > 1 else "")
    return f"""
<article class="card glass letter reveal" aria-label="{esc(label)}">
  <p class="lk"><span>{esc(label)}</span><span>from {esc(site.get('sender', ''))}</span></p>
  <div class="letter-body">
{markdown(fill(part_md, site), 'rl')}
  </div>
</article>"""


def finale(story: dict, first: dict, last: dict) -> str:
    site, f = story["site"], story.get("finale", {})
    name = site["recipient"]
    return f"""
<footer class="finale" style="--x1:{first['accent']};--x2:{last['accent']};--x3:{last['accent2']}">
  <div class="finale-inner">
    <p class="f-top reveal">{esc(fill(f.get('top', 'Happy Birthday,'), site))}</p>
    <p class="f-name reveal" style="--n:{len(name)}">{esc(name)}</p>
    <p class="f-line reveal">{inline(fill(f.get('line', ''), site))}</p>
    <p class="f-sig reveal">{esc(fill(f.get('signoff', '{sender}'), site).lstrip('—–- '))}</p>
    <button class="again glass reveal" type="button">↺ {esc(f.get('button', 'Read it again'))}</button>
  </div>
</footer>"""


def _clip_for(want: str, clips: list[dict]) -> int:
    """Index of the clip whose file name is (or starts with) `want`, or -1."""
    want = want.strip().lower()
    if not want:
        return -1
    names = [c.get("name", "") for c in clips]
    if want in names:
        return names.index(want)
    return next((i for i, name in enumerate(names) if name.startswith(want)), -1)


def quote_clips(sec: dict, clips: list[dict], notes: list[str]) -> list[int]:
    """Which clip shows each quote. A quote with video = "…" goes on that clip;
    the rest fill the remaining clips in order. -1 = no clips, shown on a timer."""
    quotes = sec.get("quotes", [])
    if not clips:
        return [-1] * len(quotes)
    out = [_clip_for(q.get("video", ""), clips) for q in quotes]
    for q, i in zip(quotes, out):
        if q.get("video") and i < 0:
            notes.append(f"!{sec['id']}: no clip named '{q['video']}', so that quote goes in order instead")
    free = [i for i in range(len(clips)) if i not in out] or list(range(len(clips)))
    k = 0
    for j, i in enumerate(out):
        if i < 0:
            out[j] = free[k % len(free)]
            k += 1
    return out


def quote_wall(sec: dict, chars: dict, site: dict, media: dict, notes: list[str]) -> str:
    quotes = sec.get("quotes", [])
    if not quotes:
        return ""
    sid = sec["id"]
    clips = quote_clips(sec, media[sid]["videos"], notes)
    figs = []
    for q, clip in zip(quotes, clips):
        ch = chars.get(q.get("character", ""), {})
        words = fill(str(q.get("text", "")).strip(), site).split()
        text = " ".join(f'<span style="--i:{i}">{esc(w)}</span>' for i, w in enumerate(words))
        who = esc(ch.get("short", ch.get("name", "")))
        anime = f' · {esc(ch["anime"])}' if ch.get("anime") else ""
        voice = ""
        stem = (q.get("voice") or "").strip()
        if stem:
            url = media[sid]["voice"].get(Path(stem).stem.lower())
            if url:
                voice = f' data-voice="{esc(url)}"'
            else:
                notes.append(f"media/{sid}/voice/{Path(stem).stem}.mp3")
        at = ""
        if q.get("at") is not None and clip >= 0:  # 'at' is in the original video's time
            c = media[sid]["videos"][clip]
            rel = float(q["at"]) - float(c.get("start") or 0)
            if rel < 0 or (c.get("end") is not None and float(q["at"]) > float(c["end"])):
                notes.append(f"!{sid}: quote at {q['at']}s is outside the trimmed part of "
                             f"'{c.get('name')}', so it was skipped")
                continue
            at = f' data-at="{rel:.2f}"'
        figs.append(f'<figure class="q" data-clip="{clip}"{at} style="--c:{ch.get("color", "#ffffff")}"{voice}>'
                    f'<blockquote>{text}</blockquote><figcaption>{who}{anime}</figcaption></figure>')
    return f'<div class="qwall" data-qwall="{esc(sid)}" style="{theme_vars(sec)}">{"".join(figs)}</div>'


def stage(sections: list[dict], media: dict, cfg: dict, walls: str = "") -> str:
    out = []
    for s in sections:
        vids = ""
        if media[s["id"]]["videos"]:
            v = '<video muted playsinline preload="none" disablepictureinpicture disableremoteplayback></video>'
            vids = v + v
        out.append(f'<div class="bg fx-{esc(s.get("fx", "embers"))}" data-bg="{esc(s["id"])}" '
                   f'style="{theme_vars(s)};--fade:{float(cfg["video_fade"])}s">'
                   f'<div class="bg-fallback"></div>{vids}</div>')
    out.append(f'<div class="dim" style="--dim:{float(cfg["dim"])}"></div><div class="grain"></div>')
    out.append(walls)  # quotes sit above the darkening so they stay readable
    return "".join(out)


def dock(sections: list[dict]) -> str:
    secs = "".join(
        f'<button class="sec" type="button" data-go="{esc(s["id"])}" style="--c:{s["accent"]}" '
        f'aria-label="Go to {esc(s["title"])}"><i class="dot"></i><span class="lbl">{esc(s["title"])}</span></button>'
        for s in sections)
    return f"""
<nav class="dock glass" aria-label="Letter controls">
  <button id="sound" class="snd" type="button" aria-label="Turn sound on" data-state="off">{ICON_SOUND_ON}{ICON_SOUND_OFF}</button>
  <span class="sep" aria-hidden="true"></span>
  {secs}
</nav>"""


# ── page ──────────────────────────────────────────────────────────────
def chapters(story: dict, letter_parts: list[str], media: dict) -> tuple[str, list[str]]:
    site = story["site"]
    chars = story.get("characters", {})
    sections = story["sections"]
    notes: list[str] = []
    parts = list(letter_parts)
    total, used = len(parts), 0
    html_out = []

    def next_letter() -> str:
        nonlocal used
        if used >= total:
            return ""
        block = letter(parts[used], used, total, site)
        used += 1
        return block

    for n, sec in enumerate(sections, 1):
        sid = sec["id"]
        flow = list(sec.get("flow", []))
        items, side_i = [], 0
        if flow and flow[0].get("type") == "hero":
            items.append(hero(site))
            flow = flow[1:]
        items.append(chapter_head(sec, n, site))

        for item in flow:
            kind = item.get("type")
            side = "left" if side_i % 2 == 0 else "right"
            if kind == "hero":
                items.append(hero(site))
            elif kind == "letter":
                items.append(next_letter())
            elif kind in ("message", "moment"):
                ch = chars.get(item.get("character", ""))
                if not ch:  # build.py validates first; this is a fallback
                    continue
                vurl = None
                stem = (item.get("voice") or "").strip()
                if stem:
                    vurl = media[sid]["voice"].get(Path(stem).stem.lower())
                    if not vurl:
                        notes.append(f"media/{sid}/voice/{Path(stem).stem}.mp3")
                render_fn = message if kind == "message" else moment
                items.append(render_fn(item, ch, site, side, vurl))
                side_i += 1
            elif kind == "spotlight":
                items.append(spotlight(item, site, side))
                side_i += 1

        if n == len(sections):
            while used < total:  # any letter parts the flow didn't place go at the end
                items.append(next_letter())
            items.append(finale(story, sections[0], sec))

        html_out.append(f'<section class="chapter" id="ch-{esc(sid)}" data-section="{esc(sid)}" '
                        f'style="{theme_vars(sec)}" aria-label="{esc(sec["title"])}">'
                        + "".join(items) + "</section>")
    return "\n".join(html_out), notes


def page(template: str, story: dict, letter_parts: list[str], media: dict, version: str) -> tuple[str, list[str]]:
    site = story["site"]
    cfg = story["media"]
    sections = story["sections"]
    body, notes = chapters(story, letter_parts, media)
    walls = "".join(quote_wall(s, story.get("characters", {}), site, media, notes) for s in sections)

    data = {
        "sections": [{
            "id": s["id"], "title": s["title"], "anime": s["anime"],
            "accent": s["accent"], "accent2": s["accent2"], "fx": s.get("fx", "embers"),
            "videos": media[s["id"]]["videos"], "music": media[s["id"]]["music"],
        } for s in sections],
        "video": {"fade": float(cfg["video_fade"]), "mode": cfg["video_transition"]},
        "audio": {k: cfg[k] for k in ("music_volume", "voice_volume", "duck", "auto_voice",
                                       "clip_audio", "clip_volume")},
    }
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

    title = fill(site.get("page_title", "Happy Birthday, {recipient}"), site)
    desc = fill(site.get("link_preview", ""), site)
    poster = next((media[s["id"]]["poster"] for s in sections if media[s["id"]]["poster"]), None)
    og = ""
    if poster:
        base = (site.get("site_url") or "").strip()
        if base and not base.endswith("/"):
            base += "/"
        og = (f'<meta property="og:image" content="{esc(base + poster)}">'
              f'<meta name="twitter:card" content="summary_large_image">')

    html_doc = (template
                .replace("{{TITLE}}", esc(title))
                .replace("{{DESC}}", esc(desc))
                .replace("{{OG_IMAGE}}", og)
                .replace("{{V}}", version)
                .replace("{{STAGE}}", stage(sections, media, cfg, walls))
                .replace("{{GATE}}", gate(story, sections[0]))
                .replace("{{CHAPTERS}}", body)
                .replace("{{DOCK}}", dock(sections))
                .replace("{{DATA}}", data_json))
    return html_doc, notes
