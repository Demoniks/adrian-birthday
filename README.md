# 🎂 Happy Birthday, Adrian — Plus Ultra

A birthday letter as a website. Anime clips play behind glass cards, each chapter has its own music, and character voice lines play as he scrolls to them.

- **Chapter 1 · Plus Ultra** — My Hero Academia. Bakugo backgrounds, Bakugo + Deku messages, Deku's moments of reaching out (Kacchan, Todoroki, Kota).
- **Chapter 2 · Brothers** — Jujutsu Kaisen × Demon Slayer. Todo pulling Yuji back up in Shibuya, Yuji and Tanjiro messages, Tanjiro's moments.
- **Your letter** is split across both chapters and ends in a fireworks finale.

Python builds everything; the result is a plain static site in `docs/` that GitHub Pages serves for free.

---

## 1 · Open it in VS Code

1. Install **Python 3.11+** and **ffmpeg** (ffmpeg strips the audio out of clips and shrinks them for the web).
   - Windows: `winget install Python.Python.3.12` and `winget install ffmpeg`
   - macOS: `brew install python ffmpeg`
2. `File → Open Folder…` → this folder. Accept the recommended extensions (Python, TOML).
3. Press **Ctrl/Cmd + Shift + B** → *Preview birthday page (live reload)*.
   Your browser opens at `http://localhost:8000`. Every time you save a file, the page rebuilds and reloads.
   While editing, use `http://localhost:8000/?nogate` to skip the opening screen.

No VS Code? `python scripts/serve.py` does the same thing.

## 2 · Write your letter → `content/letter.md`

Just write. Blank line = new paragraph. `**bold**`, `*italic*`, `> quote`, and a line starting with `—` becomes your handwritten signature.

`[[next]]` on its own line moves the rest of the letter further down the page:

| Part | Where it shows up |
|---|---|
| I | Right after the big **HAPPY BIRTHDAY ADRIAN** |
| II | Middle of the *Brothers* chapter |
| III | The end, just before the finale |

The `<!-- comments -->` in the file are writing prompts. They never appear on the page.

## 3 · Drop in your clips, music and voice lines → `media/`

```
media/
├── plus-ultra/          Chapter 1 (My Hero Academia)
│   ├── videos/          Bakugo clips  → background, fade in/out, loop forever
│   ├── music/           MHA songs     → play in order, loop
│   └── voice/           bakugo.mp3, deku.mp3, deku-todoroki.mp3, deku-kota.mp3, deku-kacchan.mp3
└── brothers/            Chapter 2 (JJK × Demon Slayer)
    ├── videos/          Todo & Yuji vs Mahito clips
    ├── music/           JJK songs
    └── voice/           todo.mp3, todo-yuji.mp3, yuji.mp3, tanjiro.mp3, tanjiro-nezuko.mp3, tanjiro-giyu.mp3
```

- **Any format works** (mp4, mov, mkv, wav, flac…). The build converts everything; clip audio is removed.
- **Order** = file name, so prefix them: `01-…`, `02-…`.
- **Clip length**: 5–20 seconds each is the sweet spot. Each one fades out, the next fades in, and the list loops.
- **Voice lines** are matched to cards by file name (the `voice = "…"` value in `story.toml`). When he scrolls to that card the line plays and the music dips under it. Every card also gets a **Hear it** button. A card with no matching file just stays silent.
- Your raw files never get uploaded. Only the compressed copies in `docs/media/` are published.

## 4 · Make it yours → `content/story.toml`

Everything else lives here, with comments explaining each setting:

- `sender` → **your name** (it's "Your Brother" right now)
- `date_line` → his birthday date under the title
- Character **messages** — written in each character's voice, talking to Adrian
- **Moments** — the scene where Deku / Todo / Tanjiro lifted someone up, plus the lesson. Each one has an empty `line = ""`: paste the exact anime line you love there and it shows as a big pull-quote with the character's name.
- The **"Why you're the Bakugo of this family"** list — rewrite it with real things about him.
- `[media]` — fade length, `dip` vs `crossfade`, how dark the video overlay is, music and voice volume, auto-play voice on/off.
- Add a third chapter by copying a whole `[[sections]]` block and giving it a new `id`; its media folders appear automatically.

## 5 · Put it on GitHub Pages

**First time only:**

1. On github.com → **New repository** → name it (e.g. `for-adrian`) → **Public** → Create.
2. In the VS Code terminal (`` Ctrl+` ``), from this folder:
   ```bash
   git init
   git add -A
   git commit -m "Birthday letter"
   git branch -M main
   git remote add origin https://github.com/YOUR-USER/for-adrian.git
   git push -u origin main
   ```
   (Or use the **Publish to GitHub** button in VS Code's Source Control panel.)
3. On GitHub: **Settings → Pages → Build and deployment → Source: Deploy from a branch → `main` / `/docs` → Save.**
4. After ~1 minute it's live at `https://YOUR-USER.github.io/for-adrian/`.

**Every update after that:** run the task **🚀 Publish to GitHub Pages** (or `python scripts/publish.py`). It builds, commits and pushes.

Optional: put that URL in `site_url` in `story.toml` so the link preview shows a frame from your first clip when you text it to him.

## Good to know

- **Sound needs one tap.** Browsers block audio until the visitor interacts, which is why the page opens on an "Open it" card. That tap starts the music and shoots the first explosion.
- **Test on your phone** before you send it — that's probably where he'll open it.
- GitHub Pages sites are **public**: anyone with the link can see it. The repo name is the URL, so don't name it something that spoils the surprise if he follows you on GitHub.
- GitHub rejects files over 100 MB. The build warns you; trim the clip or raise `crf` (e.g. 28) in `story.toml`.
- `python scripts/build.py --force` re-encodes everything (after changing `max_width` or `crf`).

## Project map

```
content/letter.md       ← your letter
content/story.toml      ← names, characters, messages, moments, chapters, settings
media/                  ← your raw clips / songs / voice lines (not uploaded)
scripts/build.py        builds docs/ (validates content, renders HTML)
scripts/media.py        ffmpeg pipeline: strip audio, resize, compress, normalize loudness
scripts/render.py       turns content into HTML
scripts/serve.py        live-reload preview server (supports video seeking)
scripts/publish.py      build + git push
site_src/               page template, glass styles, video/audio engine (app.js)
docs/                   ← generated site that GitHub Pages serves (don't edit by hand)
```
