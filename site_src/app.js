/* ==========================================================================
   Birthday letter — page runtime
   Data comes from <script id="site-data">, written by scripts/build.py.
   ========================================================================== */
(() => {
  "use strict";

  const SITE = JSON.parse(document.getElementById("site-data").textContent);
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const params = new URLSearchParams(location.search);
  const sections = SITE.sections;
  const byId = Object.fromEntries(sections.map((s) => [s.id, s]));
  const safePlay = (media) => {
    try { const p = media.play(); if (p && p.catch) p.catch(() => {}); } catch (_) { /* ignore */ }
  };
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";

  /* ------------------------------------------------------------------------
     1. Background clips — each clip fades in, plays, fades out, next one
        comes in; the list loops forever. Two <video> tags take turns so the
        next clip is always buffered.
     ------------------------------------------------------------------------ */
  class ClipLoop {
    constructor(root, clips, { fade, mode }, hooks = {}) {
      this.root = root;
      this.clips = clips;
      this.onClip = hooks.clip || (() => {});           // a clip is coming on screen
      this.onTime = hooks.time || (() => {});           // the playing clip reached time t
      this.fade = Math.max(0.2, Number(fade) || 0.9);
      this.mode = mode === "crossfade" ? "crossfade" : "dip";
      this.vids = $$("video", root);
      this.i = 0;
      this.cur = 0;
      this.running = false;
      this.switching = false;
      this.primed = false;
      this.pending = null;
      this.timers = [];
      for (const v of this.vids) {
        v.muted = true;
        v.defaultMuted = true;
        v.playsInline = true;
        v.addEventListener("timeupdate", () => this.tick(v));
        v.addEventListener("ended", () => { if (v === this.vids[this.cur]) this.advance(); });
      }
    }
    get n() { return this.clips.length; }
    load(v, idx) {
      const clip = this.clips[((idx % this.n) + this.n) % this.n];
      if (v.dataset.src !== clip.src) {
        v.dataset.src = clip.src;
        v.src = clip.src;
        v.preload = "auto";
        v.load();
      } else {
        try { v.currentTime = 0; } catch (_) { /* not ready yet */ }
      }
    }
    start() {
      if (!this.n || this.running) return;
      this.running = true;
      const v = this.vids[this.cur];
      if (!this.primed) {
        this.primed = true;
        this.load(v, 0);
        this.load(this.vids[1 - this.cur], 1);
      }
      safePlay(v);
      requestAnimationFrame(() => v.classList.add("on"));
      this.onClip(this.i);
    }
    kick() { if (this.running) safePlay(this.vids[this.cur]); }
    tick(v) {
      if (!this.running || this.switching || v !== this.vids[this.cur]) return;
      this.onTime(this.i, v.currentTime);
      const d = v.duration;
      if (!isFinite(d) || d <= 0) return;
      if (d - v.currentTime <= this.fade + 0.06) this.advance();
    }
    advance() {
      if (!this.running || this.switching) return;
      this.switching = true;
      const out = this.vids[this.cur];
      const inc = this.vids[1 - this.cur];
      const nextIdx = (this.i + 1) % this.n;
      this.load(inc, nextIdx);
      this.pending = { out, inc, nextIdx };
      out.classList.remove("on");                       // fade out
      const bringIn = () => {
        if (!this.running) return;
        safePlay(inc);
        inc.classList.add("on");                        // fade in
        this.onClip(nextIdx);
        this.later(() => this.finalize(), this.fade * 1000 + 80);
      };
      if (this.mode === "crossfade") bringIn();
      else this.later(bringIn, this.fade * 1000);
    }
    later(fn, ms) {
      const t = setTimeout(() => { this.timers = this.timers.filter((x) => x !== t); fn(); }, ms);
      this.timers.push(t);
    }
    finalize() {
      const p = this.pending;
      if (!p) return;
      this.pending = null;
      p.out.classList.remove("on");
      p.inc.classList.add("on");
      p.out.pause();
      this.i = p.nextIdx;
      this.cur = this.vids.indexOf(p.inc);
      this.load(p.out, p.nextIdx + 1);                  // pre-buffer the one after
      this.switching = false;
    }
    stop() {
      this.running = false;
      this.timers.forEach(clearTimeout);
      this.timers = [];
      if (this.pending) this.finalize();
      this.vids.forEach((v) => v.pause());
    }
  }

  /* ------------------------------------------------------------------------
     1b. Quote wall — each clip brings its quote onto the background. The new
         one glows bright, older ones stay behind, dimmer, so the wall keeps
         filling up as the clips play. No clips? Quotes arrive on a timer.
     ------------------------------------------------------------------------ */
  const SLOTS = 6;
  const HOLD = 6500;   // ms a new quote stays bright before it settles back into the wall
  class QuoteWall {
    constructor(root, onShow) {
      this.root = root;
      this.items = $$(".q", root);
      this.onShow = onShow;
      this.count = 0;
      this.slots = new Array(SLOTS).fill(null);
      this.now = null;
      this.timer = 0;
      this.dimT = 0;
      this.next = 0;
      this.fired = new Set();   // timed quotes already shown during this play of the clip
      this.timed = this.items.some((q) => q.dataset.clip === "-1");
    }
    // a clip starts: untimed quotes for it appear now, timed ones wait for their second
    clip(idx) {
      this.fired.clear();
      this.items
        .filter((q) => Number(q.dataset.clip) === idx && q.dataset.at === undefined)
        .forEach((q, k) => setTimeout(() => this.show(q), 600 + k * 3200));
    }
    time(idx, t) {
      for (const q of this.items) {
        if (q.dataset.at === undefined || Number(q.dataset.clip) !== idx || this.fired.has(q)) continue;
        const at = Number(q.dataset.at);
        if (t >= at - 0.15 && t < at + 4) { this.fired.add(q); this.show(q); }
      }
    }
    show(q) {
      if (!q.classList.contains("shown") || q.dataset.slot === undefined) {
        const slot = this.count++ % SLOTS;
        const old = this.slots[slot];
        if (old && old !== q) { old.classList.remove("shown", "now"); delete old.dataset.slot; }
        this.slots[slot] = q;
        q.dataset.slot = String(slot);
        q.classList.add("shown");
      }
      if (this.now && this.now !== q) this.now.classList.remove("now");
      this.now = q;
      q.classList.remove("now");
      void q.offsetWidth;            // restart the pop animation
      q.classList.add("now");
      clearTimeout(this.dimT);
      this.dimT = setTimeout(() => q.classList.remove("now"), HOLD);
      this.onShow(q);
    }
    start() {
      if (!this.timed || this.timer || !this.items.length) return;
      const step = () => { this.show(this.items[this.next]); this.next = (this.next + 1) % this.items.length; };
      this.timer = setTimeout(() => { step(); this.timer = setInterval(step, 7000); }, 1200);
    }
    stop() { clearTimeout(this.timer); clearInterval(this.timer); this.timer = 0; }
  }

  /* ------------------------------------------------------------------------
     2. Audio —one music playlist per chapter (crossfades when he scrolls
        into the next chapter) + voice lines that dip the music while they play.
        Web Audio gain nodes so fades also work on iPhone.
     ------------------------------------------------------------------------ */
  class AudioEngine {
    constructor(cfg) {
      this.cfg = cfg;
      this.ready = false;
      this.muted = false;
      this.ducked = false;
      this.active = null;
      this.tracks = new Map();
      this.onVoiceEnd = () => {};
    }
    init() {
      if (this.ready) return;
      this.ready = true;
      const AC = window.AudioContext || window.webkitAudioContext;
      if (AC) {
        try {
          this.ctx = new AC();
          this.master = this.ctx.createGain();
          this.master.connect(this.ctx.destination);
        } catch (_) { this.ctx = null; }
      }
      for (const s of sections) {
        if (!s.music.length) continue;
        const el = new Audio();
        el.preload = "auto";
        el.src = s.music[0];
        const t = { el, list: s.music, idx: 0, gain: null, raf: 0, stopT: 0 };
        if (s.music.length === 1) el.loop = true;
        else el.addEventListener("ended", () => {
          t.idx = (t.idx + 1) % t.list.length;
          el.src = t.list[t.idx];
          safePlay(el);
        });
        if (this.ctx) {
          const src = this.ctx.createMediaElementSource(el);
          t.gain = this.ctx.createGain();
          t.gain.gain.value = 0;
          src.connect(t.gain).connect(this.master);
        } else {
          el.volume = 0;
        }
        this.tracks.set(s.id, t);
        // Start every track inside the tap so iOS lets us play it later; pause the ones not needed yet.
        const p = el.play();
        if (p && p.then) p.then(() => { if (this.active !== s.id) el.pause(); }).catch(() => {});
      }
      // the background clips' own sound, kept quiet under everything else
      this.clipVids = this.cfg.clip_audio ? $$("#stage video") : [];
      if (this.clipVids.length && this.ctx) {
        this.clipGain = this.ctx.createGain();
        this.clipGain.gain.value = this.cfg.clip_volume;
        this.clipGain.connect(this.master);
        for (const v of this.clipVids) {
          try { this.ctx.createMediaElementSource(v).connect(this.clipGain); } catch (_) { /* already wired */ }
        }
      }
      for (const v of this.clipVids) {
        if (!this.ctx) v.volume = Math.min(1, this.cfg.clip_volume);
        v.defaultMuted = false;
        v.muted = false;
      }
      this.voice = new Audio();
      this.voice.preload = "auto";
      if (this.ctx) {
        const vs = this.ctx.createMediaElementSource(this.voice);
        this.vgain = this.ctx.createGain();
        this.vgain.gain.value = this.cfg.voice_volume;
        vs.connect(this.vgain).connect(this.master);
      } else {
        this.voice.volume = Math.min(1, this.cfg.voice_volume);
      }
      const done = () => {
        if (!this.voice.paused && !this.voice.ended) return; // a new line already started
        this.setDuck(false);
        this.onVoiceEnd();
      };
      this.voice.addEventListener("ended", done);
      this.voice.addEventListener("pause", done);
      if (this.ctx && this.ctx.state === "suspended") this.ctx.resume();
      document.addEventListener("visibilitychange", () => {
        if (this.ctx) document.hidden ? this.ctx.suspend() : this.ctx.resume();
      });
    }
    level(id) {
      return (id === this.active ? 1 : 0) * this.cfg.music_volume * (this.ducked ? this.cfg.duck : 1);
    }
    ramp(t, value, secs) {
      if (t.gain) {
        const g = t.gain.gain, now = this.ctx.currentTime;
        g.cancelScheduledValues(now);
        g.setValueAtTime(g.value, now);
        g.linearRampToValueAtTime(value, now + secs);
      } else {
        cancelAnimationFrame(t.raf);
        const from = t.el.volume, t0 = performance.now();
        const step = (now) => {
          const k = Math.min(1, (now - t0) / (secs * 1000));
          t.el.volume = Math.max(0, Math.min(1, from + (value - from) * k));
          if (k < 1) t.raf = requestAnimationFrame(step);
        };
        t.raf = requestAnimationFrame(step);
      }
    }
    setSection(id) {
      this.active = id;
      if (!this.ready) return;
      for (const [sid, t] of this.tracks) {
        clearTimeout(t.stopT);
        if (sid === id) {
          safePlay(t.el);
          this.ramp(t, this.level(sid), 1.8);
        } else {
          this.ramp(t, 0, 1.8);
          t.stopT = setTimeout(() => { if (this.active !== sid) t.el.pause(); }, 2000);
        }
      }
    }
    setDuck(on) {
      if (this.ducked === on) return;
      this.ducked = on;
      const t = this.tracks.get(this.active);
      if (t) this.ramp(t, this.level(this.active), on ? 0.35 : 1.2);
      if (this.clipGain) {
        const g = this.clipGain.gain, now = this.ctx.currentTime;
        g.cancelScheduledValues(now);
        g.setValueAtTime(g.value, now);
        g.linearRampToValueAtTime(this.cfg.clip_volume * (on ? this.cfg.duck : 1), now + (on ? 0.35 : 1.2));
      }
    }
    setMuted(m) {
      this.muted = m;
      if (!this.ready) return;
      if (this.master) {
        const g = this.master.gain, now = this.ctx.currentTime;
        g.cancelScheduledValues(now);
        g.setValueAtTime(g.value, now);
        g.linearRampToValueAtTime(m ? 0 : 1, now + 0.4);
        if (!m && this.ctx.state === "suspended") this.ctx.resume();
      } else {
        for (const t of this.tracks.values()) t.el.muted = m;
        for (const v of this.clipVids) v.muted = m;
        this.voice.muted = m;
      }
    }
    playVoice(src) {
      if (!this.ready) return false;
      if (this.ctx && this.ctx.state === "suspended") this.ctx.resume();
      const abs = new URL(src, location.href).href;
      if (this.voice.src !== abs) this.voice.src = abs;
      try { this.voice.currentTime = 0; } catch (_) { /* fine */ }
      this.setDuck(true);
      const p = this.voice.play();
      if (p && p.catch) p.catch(() => this.setDuck(false));
      return true;
    }
    stopVoice() { if (this.voice) this.voice.pause(); }
    voicePlaying() { return !!this.voice && !this.voice.paused && !this.voice.ended; }
  }

  /* ------------------------------------------------------------------------
     3. Particles — explosion embers (MHA) / drifting cursed energy (JJK).
     ------------------------------------------------------------------------ */
  class Particles {
    constructor(canvas) {
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.list = [];
      this.mode = "embers";
      this.colors = ["#ff7a1a", "#ffd23f"];
      this.enabled = !reduced && !!this.ctx;
      this.seeded = false;
      this.resize();
      addEventListener("resize", () => this.resize(), { passive: true });
      this.last = performance.now();
      if (this.enabled) requestAnimationFrame((t) => this.frame(t));
    }
    resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      this.w = document.documentElement.clientWidth;   // visible width, without the scrollbar
      this.h = document.documentElement.clientHeight;
      this.canvas.width = Math.round(this.w * dpr);
      this.canvas.height = Math.round(this.h * dpr);
      if (this.ctx) this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      this.target = Math.round(Math.min(80, (this.w * this.h) / 18000));
    }
    theme(sec) { this.mode = sec.fx || "embers"; this.colors = [sec.accent, sec.accent2]; }
    rnd(a, b) { return a + Math.random() * (b - a); }
    pick(a) { return a[(Math.random() * a.length) | 0]; }
    ambient(anywhere) {
      const e = this.mode === "energy";
      this.list.push({
        kind: "amb",
        x: this.rnd(0, this.w),
        y: anywhere || e ? this.rnd(0, this.h) : this.h + 12,
        vx: this.rnd(-8, 8),
        vy: e ? -this.rnd(6, 22) : -this.rnd(18, 58),
        r: e ? this.rnd(0.8, 2.6) : this.rnd(0.6, 2.1),
        life: 0,
        max: e ? this.rnd(4, 9) : this.rnd(5, 11),
        wob: e ? this.rnd(16, 36) : this.rnd(4, 14),
        ph: this.rnd(0, 6.28),
        sp: this.rnd(0.6, 1.6),
        color: this.pick(this.colors),
      });
    }
    burst(x, y, colors = this.colors, n = 100) {
      if (!this.enabled) return;
      for (let i = 0; i < n; i++) {
        const a = Math.random() * Math.PI * 2, v = this.rnd(120, 540);
        this.list.push({
          kind: "burst", x, y,
          vx: Math.cos(a) * v, vy: Math.sin(a) * v - 80,
          r: this.rnd(1, 3.2), life: 0, max: this.rnd(0.9, 2.1), color: this.pick(colors),
        });
      }
    }
    frame(now) {
      const dt = Math.min(0.05, (now - this.last) / 1000);
      this.last = now;
      const ctx = this.ctx;
      ctx.clearRect(0, 0, this.w, this.h);
      if (this.mode !== "none") {
        if (!this.seeded) { this.seeded = true; for (let i = 0; i < this.target; i++) this.ambient(true); }
        let amb = 0;
        for (const p of this.list) if (p.kind === "amb") amb++;
        for (let k = 0; amb < this.target && k < 2; k++, amb++) this.ambient(false);
      }
      ctx.globalCompositeOperation = "lighter";
      const keep = [];
      for (const p of this.list) {
        p.life += dt;
        if (p.life >= p.max) continue;
        if (p.kind === "amb") {
          p.ph += dt * p.sp;
          p.x += (p.vx + Math.sin(p.ph) * p.wob) * dt;
          p.y += p.vy * dt;
          if (p.y < -20) continue;
        } else {
          const drag = 1 - 1.7 * dt;
          p.vx *= drag;
          p.vy = p.vy * drag + 260 * dt;
          p.x += p.vx * dt;
          p.y += p.vy * dt;
        }
        const t = p.life / p.max;
        let a = t < 0.12 ? t / 0.12 : 1 - (t - 0.12) / 0.88;
        if (p.kind === "amb") a *= 0.55 + 0.45 * Math.abs(Math.sin(p.ph * 3));
        ctx.fillStyle = p.color;
        ctx.globalAlpha = a * 0.22;
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r * 4, 0, 6.2832); ctx.fill();
        ctx.globalAlpha = a;
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, 6.2832); ctx.fill();
        keep.push(p);
      }
      this.list = keep;
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";
      requestAnimationFrame((t) => this.frame(t));
    }
  }

  /* ------------------------------------------------------------------------
     4. Wiring it all together
     ------------------------------------------------------------------------ */
  const audio = new AudioEngine(SITE.audio);
  let heardQuotes = new WeakSet();
  function quoteVoice(q) {     // a quote with its own voice clip speaks once, if nothing else is talking
    if (!q.dataset.voice || heardQuotes.has(q) || !SITE.audio.auto_voice) return;
    if (!audio.ready || audio.muted || audio.voicePlaying()) return;
    heardQuotes.add(q);
    audio.playVoice(q.dataset.voice);
  }
  const walls = new Map();
  for (const s of sections) {
    const root = $(`.qwall[data-qwall="${CSS.escape(s.id)}"]`);
    if (root) walls.set(s.id, new QuoteWall(root, quoteVoice));
  }
  const loops = new Map();
  for (const s of sections) {
    const root = $(`.bg[data-bg="${CSS.escape(s.id)}"]`);
    const wall = walls.get(s.id);
    if (root && s.videos.length) {
      loops.set(s.id, new ClipLoop(root, s.videos, SITE.video, {
        clip: (i) => { if (wall) wall.clip(i); },
        time: (i, t) => { if (wall) wall.time(i, t); },
      }));
    }
  }
  const fx = new Particles($("#fx"));
  const docEl = document.documentElement;
  let current = null;
  let opened = false;

  // which chapter is on screen → background, music, colors
  function activate(id) {
    if (!byId[id] || id === current) return;
    current = id;
    const sec = byId[id];
    $$(".bg").forEach((bg) => bg.classList.toggle("active", bg.dataset.bg === id));
    $$(".qwall").forEach((w) => w.classList.toggle("active", w.dataset.qwall === id));
    walls.forEach((wall, sid) => { if (sid === id && opened) wall.start(); else wall.stop(); });
    loops.forEach((loop, sid) => {
      if (sid === id) loop.start();
      else setTimeout(() => { if (current !== sid) loop.stop(); }, 1800);
    });
    docEl.style.setProperty("--live-a", sec.accent);
    docEl.style.setProperty("--live-b", sec.accent2);
    fx.theme(sec);
    audio.setSection(id);
    $$(".dock .sec").forEach((b) => b.setAttribute("aria-current", String(b.dataset.go === id)));
  }
  activate(sections[0].id);

  const chapterIO = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) activate(e.target.dataset.section);
  }, { rootMargin: "-48% 0px -48% 0px" });
  $$(".chapter").forEach((c) => chapterIO.observe(c));

  // pause the clips when the tab is hidden (saves battery)
  document.addEventListener("visibilitychange", () => {
    const loop = loops.get(current);
    if (!loop || !opened) return;
    document.hidden ? loop.stop() : loop.start();
  });

  // reveal cards & letter lines as they scroll in
  const revealIO = new IntersectionObserver((entries, io) => {
    for (const e of entries) if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
  }, { threshold: 0.12, rootMargin: "0px 0px -6% 0px" });

  // voice lines
  let heard = new WeakSet();
  let speaking = null;
  const voiceCards = $$("[data-voice]");
  function markSpeaking(card) {
    if (speaking) speaking.classList.remove("playing");
    speaking = card;
    if (card) card.classList.add("playing");
  }
  audio.onVoiceEnd = () => markSpeaking(null);
  function speak(card) {
    if (!audio.ready) enableSound();
    if (audio.playVoice(card.dataset.voice)) { heard.add(card); markSpeaking(card); }
  }
  voiceCards.forEach((card) => {
    const btn = $(".voice-btn", card);
    if (btn) btn.addEventListener("click", () => {
      if (speaking === card && audio.voicePlaying()) audio.stopVoice();
      else speak(card);
    });
  });
  const voiceIO = new IntersectionObserver((entries) => {
    for (const e of entries) {
      const card = e.target;
      clearTimeout(card._vt);
      const seen = e.intersectionRatio >= 0.5 || e.intersectionRect.height > innerHeight * 0.45;
      if (e.isIntersecting && seen && SITE.audio.auto_voice && audio.ready && !audio.muted && !heard.has(card)) {
        card._vt = setTimeout(() => { if (!audio.voicePlaying()) speak(card); }, 700);
      }
    }
  }, { threshold: [0, 0.25, 0.5, 0.75, 1] });

  // sound button
  const soundBtn = $("#sound");
  const hasSound = sections.some((s) => s.music.length) || voiceCards.length > 0 ||
    (SITE.audio.clip_audio && loops.size > 0);
  if (!hasSound) { soundBtn.hidden = true; const sep = $(".dock .sep"); if (sep) sep.hidden = true; }
  function syncSound() {
    const on = audio.ready && !audio.muted;
    soundBtn.dataset.state = on ? "on" : "off";
    soundBtn.setAttribute("aria-label", on ? "Mute" : "Turn sound on");
  }
  function enableSound() {
    audio.init();
    audio.setSection(current);
    audio.setMuted(false);
    syncSound();
  }
  soundBtn.addEventListener("click", () => {
    if (!audio.ready) enableSound();
    else { audio.setMuted(!audio.muted); if (audio.muted) audio.stopVoice(); syncSound(); }
  });

  // dock: jump to a chapter
  $$(".dock .sec").forEach((b) => b.addEventListener("click", () => {
    const i = sections.findIndex((s) => s.id === b.dataset.go);
    if (i === 0) scrollTo({ top: 0, behavior: reduced ? "auto" : "smooth" });
    else document.getElementById(`ch-${b.dataset.go}`).scrollIntoView({ behavior: reduced ? "auto" : "smooth" });
  }));

  // the opening screen
  function open(silent) {
    if (opened) return;
    opened = true;
    scrollTo(0, 0);
    document.body.classList.add("opened");
    document.body.classList.remove("locked");
    if (!silent) enableSound();
    const loop = loops.get(current);
    if (loop) { loop.start(); loop.kick(); }           // re-kick inside the tap (iPhone low-power mode)
    const wall = walls.get(current);
    if (wall) { wall.start(); if (wall.now) setTimeout(() => quoteVoice(wall.now), 900); }
    const gate = $("#gate");
    const btn = $("#gate-btn");
    if (btn && !silent) {
      const r = btn.getBoundingClientRect();
      const s = byId[current];
      fx.burst(r.left + r.width / 2, r.top + r.height / 2, [s.accent, s.accent2, "#ffffff"], 130);
    }
    if (gate) { gate.classList.add("gone"); setTimeout(() => gate.remove(), 1300); }
    $$(".reveal, .rl").forEach((el) => (reduced ? el.classList.add("in") : revealIO.observe(el)));
    voiceCards.forEach((c) => voiceIO.observe(c));
    syncSound();
  }
  const gateBtn = $("#gate-btn");
  if (gateBtn) gateBtn.addEventListener("click", () => open(false));
  if (params.has("nogate")) open(true);

  // finale: fireworks in both chapters' colors, once
  const finale = $(".finale");
  if (finale) {
    let fired = false;
    new IntersectionObserver((entries) => {
      if (fired || !entries.some((e) => e.isIntersecting)) return;
      fired = true;
      const colors = [...new Set(sections.flatMap((s) => [s.accent, s.accent2])), "#ffffff"];
      [0, 450, 900, 1500].forEach((ms) => setTimeout(() => {
        fx.burst(innerWidth * (0.2 + Math.random() * 0.6), innerHeight * (0.2 + Math.random() * 0.35), colors, 90);
      }, ms));
    }, { threshold: 0.45 }).observe(finale);
    const again = $(".again", finale);
    if (again) again.addEventListener("click", () => {
      heard = new WeakSet();
      heardQuotes = new WeakSet();
      fired = false;
      scrollTo({ top: 0, behavior: reduced ? "auto" : "smooth" });
    });
  }
})();
