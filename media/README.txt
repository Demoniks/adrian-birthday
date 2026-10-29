DROP YOUR CLIPS AND AUDIO HERE
==============================

Each section of the page has its own folder (the folder name = the section id
in content/story.toml):

  media/plus-ultra/     → Chapter 1 · My Hero Academia (Bakugo)
  media/brothers/       → Chapter 2 · Jujutsu Kaisen × Demon Slayer (Todo & Yuji)

Inside each one:

  videos/   Background clips. Any format (mp4, mov, mkv, webm…).
            Sound is stripped automatically. They play in name order, each one
            fades in and out, and the whole set loops forever.
            Tip: name them 01-explosion.mp4, 02-..., keep each 5–20 seconds.

  music/    Songs for this section (mp3, m4a, wav, ogg, flac…).
            They play in name order and loop. When he scrolls into the next
            chapter, the music crossfades to that chapter's songs.

  voice/    Short voice lines from the anime. The file name must match the
            "voice" value of a card in story.toml, e.g.
                media/brothers/voice/todo-yuji.mp3
            plays on the Todo → Yuji card when he scrolls to it (the music dips
            while it plays). Video files work here too — the audio is extracted.

Nothing in here is uploaded to GitHub. The build makes small, web-ready copies
in docs/media/ and only those are published.
