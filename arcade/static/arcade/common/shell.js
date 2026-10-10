/* پوسته‌ی مشترک مینی‌اپ: اتصال به تلگرام، صفحه‌ها، حلقه‌ی بازی با گام ثابت، ثبت لاگ ورودی
   و ارسال آن به سرور. منطق هر بازی در core.js خودش است و اینجا فقط اجرا و ضبط می‌شود.

   نکته‌ی ضدتقلب: امتیاز را سرور از روی لاگ ورودی دوباره حساب می‌کند؛ عددی که این‌جا
   نمایش داده می‌شود فقط پیش‌نمایش است. */
(function () {
  "use strict";

  var BOOT = window.ARCADE_BOOT;
  var tg = window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initData !== undefined
    ? window.Telegram.WebApp
    : null;
  var query = new URLSearchParams(location.search);

  // ------------------------------------------------------------------ ابزار
  var FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
  function fa(value) {
    return String(value)
      .replace(/\B(?=(\d{3})+(?!\d))/g, "٬")
      .replace(/\d/g, function (d) { return FA_DIGITS[d]; });
  }
  function $(id) { return document.getElementById(id); }
  function clamp(v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; }

  var screens = ["loading", "menu", "start", "over", "error"];
  function show(name) {
    screens.forEach(function (s) { $("screen-" + s).classList.toggle("hidden", s !== name); });
    $("hud").classList.toggle("hidden", name !== null);
  }
  function fail(message) {
    $("error-text").textContent = message;
    show("error");
  }

  var ERRORS = {
    match_not_found: "این مسابقه پیدا نشد.",
    match_not_running: "این مسابقه الان در جریان نیست.",
    match_over: "زمان مسابقه تمام شده.",
    not_a_player: "تو عضو این مسابقه نیستی. دفعه‌ی بعد توی گروه دکمه‌ی «شرکت» رو بزن.",
    no_attempts_left: "همه‌ی تلاش‌هات رو استفاده کردی.",
    banned: "حساب شما مسدود شده.",
    rate_limited: "یواش‌تر! چند ثانیه صبر کن.",
    unknown_game: "این بازی پیدا نشد.",
    session_already_used: "این تلاش قبلاً ثبت شده.",
    rejected: "این تلاش تأیید نشد و ثبت نمی‌شود.",
  };
  function errorText(code) {
    if (code && code.indexOf("auth_") === 0) return "این صفحه باید از داخل تلگرام باز شود.";
    return ERRORS[code] || "مشکلی پیش آمد. دوباره امتحان کن.";
  }

  // ------------------------------------------------------------------ تلگرام
  var initData = tg && tg.initData ? tg.initData : "";
  if (!initData && BOOT.devAuth) initData = "dev:" + (query.get("dev_user") || "1");
  var startParam = BOOT.startParam || (tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param) || query.get("startapp") || "";

  function haptic(kind) {
    if (!tg || !tg.HapticFeedback) return;
    try {
      if (kind === "success" || kind === "error" || kind === "warning") tg.HapticFeedback.notificationOccurred(kind);
      else tg.HapticFeedback.impactOccurred(kind || "light");
    } catch (e) { /* نسخه‌های قدیمی */ }
  }

  if (tg) {
    try {
      tg.ready();
      tg.expand();
      if (tg.disableVerticalSwipes) tg.disableVerticalSwipes();
      if (tg.setHeaderColor) tg.setHeaderColor("secondary_bg_color");
    } catch (e) { /* نسخه‌های قدیمی */ }
  }

  function api(path, body) {
    body = body || {};
    body.initData = initData;
    return fetch(BOOT.apiBase + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function (response) {
      return response.json().catch(function () { return { ok: false, error: "bad_response" }; });
    });
  }

  function loadScript(url) {
    return new Promise(function (resolve, reject) {
      var el = document.createElement("script");
      el.src = url;
      el.onload = resolve;
      el.onerror = function () { reject(new Error("load " + url)); };
      document.head.appendChild(el);
    });
  }

  // ------------------------------------------------------------------ صدا (پیش‌فرض قطع)
  var soundOn = false;
  try { soundOn = localStorage.getItem("arcade_sound") === "1"; } catch (e) { /* ممکن است در دسترس نباشد */ }
  var audio = null;
  var SOUNDS = {
    tap: [520, 0.05, "square"], good: [760, 0.08, "sine"], clear: [980, 0.18, "triangle"],
    bad: [140, 0.28, "sawtooth"], tick: [320, 0.03, "square"], bonus: [1180, 0.1, "sine"],
  };
  function sound(name) {
    if (!soundOn) return;
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      var spec = SOUNDS[name] || SOUNDS.tap;
      var osc = audio.createOscillator();
      var gain = audio.createGain();
      osc.type = spec[2];
      osc.frequency.value = spec[0];
      gain.gain.setValueAtTime(0.12, audio.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + spec[1]);
      osc.connect(gain);
      gain.connect(audio.destination);
      osc.start();
      osc.stop(audio.currentTime + spec[1]);
    } catch (e) { /* بدون صدا ادامه می‌دهیم */ }
  }
  function renderSoundButton() { $("sound-btn").textContent = soundOn ? "🔊" : "🔇"; }
  $("sound-btn").addEventListener("click", function () {
    soundOn = !soundOn;
    try { localStorage.setItem("arcade_sound", soundOn ? "1" : "0"); } catch (e) { /* مهم نیست */ }
    renderSoundButton();
    sound("tap");
  });
  renderSoundButton();

  // ------------------------------------------------------------------ بوم و افکت‌های مشترک
  var canvas = $("stage");
  var ctx = canvas.getContext("2d");
  var view = { W: 360, H: 640, scale: 1, offsetX: 0, dpr: 1 };

  function css(name, fallback) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }
  var colors = {};
  function readColors() {
    colors.bg = "#0d1024";
    colors.bg2 = "#1b1446";
    colors.panel = "#1c2145";
    colors.ink = "#f5f6ff";
    colors.muted = "#9aa3cf";
    colors.accent = "#6ee7ff";
    colors.gold = "#ffc857";
    colors.danger = "#ff5c7a";
    colors.good = "#5ee6a8";
    colors.violet = "#a78bfa";
    colors.pink = "#f472b6";
    colors.set = ["#56ccf2", "#ffb84d", "#5ee6a8", "#f472b6", "#a78bfa", "#ff5c7a"];
  }
  readColors();

  function resize() {
    var w = window.innerWidth, h = window.innerHeight;
    view.dpr = Math.min(window.devicePixelRatio || 1, 2);
    view.scale = Math.min(w / 360, h / 520);
    view.W = 360;
    view.H = h / view.scale;
    view.offsetX = (w - 360 * view.scale) / 2;
    canvas.width = Math.round(w * view.dpr);
    canvas.height = Math.round(h * view.dpr);
    env.W = view.W;
    env.H = view.H;
    env.safeTop = (parseFloat(css("--tg-content-safe-area-inset-top", "0")) || 0) / view.scale + 96;
  }

  var fx = {
    particles: [], texts: [], shakeMag: 0, flashAlpha: 0, flashColor: "#fff",
    burst: function (x, y, color, count, speed) {
      count = count || 12;
      speed = speed || 3;
      for (var i = 0; i < count && this.particles.length < 220; i++) {
        var a = Math.random() * Math.PI * 2, s = (0.4 + Math.random()) * speed;
        this.particles.push({ x: x, y: y, vx: Math.cos(a) * s, vy: Math.sin(a) * s - 1, life: 1, color: color, size: 2 + Math.random() * 3 });
      }
    },
    shake: function (magnitude) { this.shakeMag = Math.max(this.shakeMag, magnitude); },
    flash: function (color, alpha) { this.flashColor = color; this.flashAlpha = alpha || 0.5; },
    text: function (x, y, text, color) { this.texts.push({ x: x, y: y, text: text, color: color || colors.gold, life: 1 }); },
    reset: function () { this.particles = []; this.texts = []; this.shakeMag = 0; this.flashAlpha = 0; },
    update: function (dt) {
      var k = dt / 16.7, i, p;
      for (i = this.particles.length - 1; i >= 0; i--) {
        p = this.particles[i];
        p.x += p.vx * k; p.y += p.vy * k; p.vy += 0.16 * k; p.life -= 0.022 * k;
        if (p.life <= 0) this.particles.splice(i, 1);
      }
      for (i = this.texts.length - 1; i >= 0; i--) {
        p = this.texts[i];
        p.y -= 0.9 * k; p.life -= 0.02 * k;
        if (p.life <= 0) this.texts.splice(i, 1);
      }
      this.shakeMag *= Math.pow(0.86, k);
      if (this.shakeMag < 0.2) this.shakeMag = 0;
      this.flashAlpha = Math.max(0, this.flashAlpha - 0.035 * k);
    },
    draw: function (c) {
      var i, p;
      c.globalCompositeOperation = "lighter";
      for (i = 0; i < this.particles.length; i++) {
        p = this.particles[i];
        c.globalAlpha = clamp(p.life, 0, 1);
        c.fillStyle = p.color;
        c.beginPath();
        c.arc(p.x, p.y, p.size, 0, 6.2832);
        c.fill();
      }
      c.globalCompositeOperation = "source-over";
      c.textAlign = "center";
      c.font = "900 21px Vazirmatn, Tahoma, sans-serif";
      for (i = 0; i < this.texts.length; i++) {
        p = this.texts[i];
        c.globalAlpha = clamp(p.life * 1.4, 0, 1);
        c.fillStyle = p.color;
        c.fillText(p.text, p.x, p.y);
      }
      c.globalAlpha = 1;
    },
  };

  var env = {
    W: 360, H: 640, safeTop: 96, ctx: ctx, colors: colors, fa: fa, fx: fx, haptic: haptic, sound: sound,
    now: function () { return performance.now(); },
    font: function (size, weight) { return (weight || 700) + " " + size + "px Vazirmatn, Tahoma, sans-serif"; },
    /* درخشش نئونی: glow(c, color, blur) و برای خاموش کردن glow(c) */
    glow: function (c, color, blur) {
      c.shadowColor = color || "transparent";
      c.shadowBlur = color ? (blur || 14) * view.scale * view.dpr : 0;
    },
    roundRect: function (c, x, y, w, h, r) {
      r = Math.min(r, w / 2, h / 2);
      c.beginPath();
      c.moveTo(x + r, y);
      c.arcTo(x + w, y, x + w, y + h, r);
      c.arcTo(x + w, y + h, x, y + h, r);
      c.arcTo(x, y + h, x, y, r);
      c.arcTo(x, y, x + w, y, r);
      c.closePath();
    },
  };
  resize();
  window.addEventListener("resize", function () { resize(); if (!run) drawIdle(); });

  /* پس‌زمینه‌ی مشترک: گرادیان شب، دو هاله‌ی نئونی و ستاره‌های چشمک‌زن */
  var stars = [];
  for (var si = 0; si < 46; si++) stars.push({ x: Math.random(), y: Math.random(), r: 0.5 + Math.random() * 1.3, p: Math.random() * 6.28 });
  var bgCache = null;
  function paintBackdrop() {
    var w = canvas.width, h = canvas.height;
    if (!bgCache || bgCache.width !== w || bgCache.height !== h) {
      bgCache = document.createElement("canvas");
      bgCache.width = w;
      bgCache.height = h;
      var b = bgCache.getContext("2d");
      var g = b.createLinearGradient(0, 0, 0, h);
      g.addColorStop(0, "#1b1446");
      g.addColorStop(0.55, "#101330");
      g.addColorStop(1, "#090b1c");
      b.fillStyle = g;
      b.fillRect(0, 0, w, h);
      var glow = function (x, y, r, color) {
        var rg = b.createRadialGradient(x, y, 0, x, y, r);
        rg.addColorStop(0, color);
        rg.addColorStop(1, "rgba(0,0,0,0)");
        b.fillStyle = rg;
        b.fillRect(0, 0, w, h);
      };
      glow(w * 0.12, h * 0.1, w * 0.7, "rgba(110,231,255,.13)");
      glow(w * 0.95, h * 0.3, w * 0.8, "rgba(167,139,250,.16)");
      glow(w * 0.4, h * 1.02, w * 0.9, "rgba(244,114,182,.10)");
    }
    ctx.drawImage(bgCache, 0, 0);
    var t = performance.now() / 900;
    ctx.fillStyle = "#fff";
    for (var i = 0; i < stars.length; i++) {
      var st = stars[i];
      ctx.globalAlpha = 0.18 + 0.32 * (0.5 + 0.5 * Math.sin(t + st.p));
      ctx.beginPath();
      ctx.arc(st.x * w, st.y * h, st.r * view.dpr, 0, 6.2832);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  function beginFrame() {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.shadowBlur = 0;
    paintBackdrop();
    var s = view.dpr * view.scale;
    var sx = 0, sy = 0;
    if (fx.shakeMag) {
      sx = (Math.random() - 0.5) * fx.shakeMag;
      sy = (Math.random() - 0.5) * fx.shakeMag;
    }
    ctx.setTransform(s, 0, 0, s, (view.offsetX + sx * view.scale) * view.dpr, sy * view.scale * view.dpr);
  }
  function endFrame() {
    ctx.shadowBlur = 0;
    ctx.globalAlpha = 1;
    fx.draw(ctx);
    if (fx.flashAlpha > 0) {
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.globalAlpha = fx.flashAlpha;
      ctx.fillStyle = fx.flashColor;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.globalAlpha = 1;
    }
  }
  function drawIdle() {
    beginFrame();
    if (game && game.renderer && game.idleState) game.renderer.draw(ctx, game.idleState, 0);
    endFrame();
  }

  // ------------------------------------------------------------------ وضعیت بازی
  var game = null; // { key, core, renderer, meta, assets, info, idleState }
  var run = null; // اجرای فعلی

  function toLogical(event) {
    return {
      x: clamp((event.clientX - view.offsetX) / view.scale, 0, view.W),
      y: clamp(event.clientY / view.scale, 0, view.H),
    };
  }
  function pushInput(kind, data) {
    if (!run || run.state.over || !game.renderer.input) return;
    var payload = game.renderer.input(kind, data, run.state);
    if (payload) run.queue.push(payload);
  }

  var pointer = null;
  canvas.addEventListener("pointerdown", function (event) {
    if (!run) return;
    event.preventDefault();
    var p = toLogical(event);
    pointer = { id: event.pointerId, x0: p.x, y0: p.y, x: p.x, y: p.y, swiped: false };
    pushInput("tap", p);
    pushInput("down", p);
  });
  canvas.addEventListener("pointermove", function (event) {
    if (!run || !pointer || pointer.id !== event.pointerId) return;
    var p = toLogical(event);
    var dx = p.x - pointer.x0, dy = p.y - pointer.y0;
    pushInput("drag", { x: p.x, y: p.y, dx: p.x - pointer.x, dy: p.y - pointer.y });
    pointer.x = p.x; pointer.y = p.y;
    if (!pointer.swiped && Math.max(Math.abs(dx), Math.abs(dy)) > 22) {
      pointer.swiped = true;
      var dir = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "right" : "left") : (dy > 0 ? "down" : "up");
      pushInput("swipe", { dir: dir, x: pointer.x0, y: pointer.y0 });
    }
  });
  function pointerEnd(event) {
    if (pointer && pointer.id === event.pointerId) {
      pushInput("up", { x: pointer.x, y: pointer.y });
      pointer = null;
    }
  }
  canvas.addEventListener("pointerup", pointerEnd);
  canvas.addEventListener("pointercancel", pointerEnd);

  var KEY_DIRS = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down" };
  window.addEventListener("keydown", function (event) {
    if (!run || event.repeat) return;
    var dir = KEY_DIRS[event.key];
    if (dir) {
      event.preventDefault();
      var x = dir === "left" ? view.W * 0.2 : dir === "right" ? view.W * 0.8 : view.W / 2;
      pushInput("tap", { x: x, y: view.H * 0.6, key: dir });
      pushInput("swipe", { dir: dir, x: view.W / 2, y: view.H / 2 });
    } else if (event.key === " " || event.key === "Enter") {
      event.preventDefault();
      pushInput("tap", { x: view.W / 2, y: view.H * 0.6 });
    }
  });

  function drainEvents() {
    var events = run.state.events;
    if (!events || !events.length) return;
    for (var i = 0; i < events.length; i++) {
      if (game.renderer.event) game.renderer.event(events[i], run.state);
    }
    events.length = 0;
  }

  function updateHud() {
    var state = run ? run.state : game.idleState;
    $("hud-score").textContent = fa(state ? state.score : 0);
    var sub = game.renderer.hud ? game.renderer.hud(state) : "";
    if (run && run.deadline) {
      var left = Math.max(0, Math.ceil((run.deadline - Date.now()) / 1000));
      if (left <= 60) sub = (sub ? sub + " · " : "") + "⏳ " + fa(left);
    }
    $("hud-sub").textContent = sub;
  }

  function frame(ts) {
    if (!run) return;
    var dt = Math.min(ts - run.last, 250);
    run.last = ts;
    var state = run.state;
    var tickMs = game.core.TICK_MS;

    if (!run.ended) {
      run.acc += dt;
      while (run.acc >= tickMs && !state.over) {
        if (game.renderer.sample) {
          var sampled = game.renderer.sample(state);
          if (sampled) run.queue.push(sampled);
        }
        while (run.queue.length && !state.over) {
          var ev = [run.tick * tickMs].concat(run.queue.shift());
          run.log.push(ev);
          game.core.applyInput(state, ev);
          drainEvents();
        }
        if (!state.over) {
          game.core.step(state);
          run.tick++;
          drainEvents();
        }
        run.acc -= tickMs;
      }
      var timeUp = run.deadline && Date.now() > run.deadline - 3000;
      if (state.over || timeUp || run.quit || run.log.length >= (game.core.MAX_INPUTS || 20000) - 100) {
        run.ended = true;
        run.outro = state.over ? 900 : 0;
        submit();
      }
    } else {
      run.outro -= dt;
    }

    fx.update(dt);
    beginFrame();
    game.renderer.draw(ctx, state, run.ended ? 0 : run.acc / tickMs);
    endFrame();
    updateHud();

    if (run.ended && run.outro <= 0) {
      showOver();
      run.frozen = true;
      return;
    }
    requestAnimationFrame(frame);
  }

  // ------------------------------------------------------------------ شروع و پایان یک تلاش
  function startRun() {
    $("start-btn").disabled = true;
    var body = game.matchToken ? { match_token: game.matchToken } : { game: game.key };
    api("session/start", body).then(function (res) {
      $("start-btn").disabled = false;
      if (!res.ok) { fail(errorText(res.error)); return; }
      var config = Object.assign({}, res.level_config || {}, { assets: game.assets });
      fx.reset();
      run = {
        sessionId: res.session_id,
        state: game.core.newState(res.seed, config),
        queue: [], log: [], tick: 0, acc: 0, last: performance.now(),
        ended: false, outro: 0, quit: false, result: null,
        deadline: game.info.mode === "match" ? game.infoAt + game.info.seconds_left * 1000 : 0,
      };
      if (game.renderer.reset) game.renderer.reset(run.state);
      show(null);
      if (tg) {
        try { tg.BackButton.show(); tg.enableClosingConfirmation(); } catch (e) { /* قدیمی */ }
      }
      requestAnimationFrame(frame);
    }).catch(function () {
      $("start-btn").disabled = false;
      fail("اتصال به سرور برقرار نشد.");
    });
  }

  function submit() {
    var current = run;
    var body = {
      session_id: current.sessionId,
      input_log: current.log,
      duration_ms: current.tick * game.core.TICK_MS,
      claimed_score: current.state.score,
    };
    var attempt = function (retries) {
      return api("session/submit", body).catch(function (error) {
        if (retries <= 0) throw error;
        return new Promise(function (resolve) { setTimeout(resolve, 1200); }).then(function () { return attempt(retries - 1); });
      });
    };
    attempt(2).then(function (res) {
      current.result = res;
      if (current.frozen) renderOver(current);
    }).catch(function () {
      current.result = { ok: false, error: "network" };
      if (current.frozen) renderOver(current);
    });
  }

  function stat(label, value) {
    return '<div class="stat"><b>' + value + "</b><span>" + label + "</span></div>";
  }

  function showOver() {
    if (tg) { try { tg.disableClosingConfirmation(); } catch (e) { /* قدیمی */ } }
    renderOver(run);
    show("over");
  }

  function renderOver(current) {
    var res = current.result;
    var local = current.state.score;
    var again = $("again-btn");
    $("over-note").textContent = "";
    if (!res) {
      $("over-label").textContent = "در حال ثبت امتیاز…";
      $("over-score").textContent = fa(local);
      $("over-stats").innerHTML = "";
      again.disabled = true;
      return;
    }
    again.disabled = false;
    if (!res.ok) {
      $("over-label").textContent = "ثبت نشد";
      $("over-score").textContent = fa(local);
      $("over-stats").innerHTML = "";
      $("over-note").textContent = res.error === "network" ? "اتصال به سرور برقرار نشد." : errorText(res.error);
    } else {
      $("over-label").textContent = "امتیاز تو";
      $("over-score").textContent = fa(res.verified_score);
      var html = "";
      if (res.rank) html += stat("رتبه در مسابقه", fa(res.rank) + " از " + fa(res.players));
      if (res.best !== undefined) html += stat("بهترین تو", fa(res.best));
      html += stat("رکورد شخصی", fa(res.record || 0));
      if (res.attempts_left !== undefined) html += stat("تلاش مانده", fa(res.attempts_left));
      $("over-stats").innerHTML = html;
      if (res.verified_score > 0 && res.verified_score >= (res.record || 0)) haptic("success");
    }
    var canRetry = game.info.mode !== "match" || (res.ok ? res.attempts_left > 0 : false);
    if (game.info.mode === "match" && res.attempts_left !== undefined) game.info.attempts_left = res.attempts_left;
    again.classList.toggle("hidden", !canRetry);
    $("close-btn").textContent = game.info.mode === "match" ? "برگشت به گروه" : "بازی‌های دیگر";
  }

  // ------------------------------------------------------------------ صفحه‌ی شروع
  var countdownTimer = null;
  function renderStart() {
    var info = game.info;
    $("start-emoji").textContent = game.meta.emoji;
    $("start-title").textContent = game.meta.title;
    $("start-howto").textContent = game.meta.howto;
    var note = "";
    var btn = $("start-btn");
    btn.disabled = false;
    var paint = function () {
      var html = "";
      if (info.mode === "match") {
        var left = Math.max(0, Math.round((game.infoAt + info.seconds_left * 1000 - Date.now()) / 1000));
        html += stat("تلاش مانده", fa(info.attempts_left) + " از " + fa(info.attempts_total));
        html += stat("زمان مسابقه", fa(Math.floor(left / 60)) + ":" + fa(String(left % 60).padStart(2, "0")));
        html += stat("بهترین تو", fa(info.best || 0));
        if (left <= 3) btn.disabled = true;
      } else {
        html += stat("رکورد شخصی", fa(info.record || 0));
      }
      $("start-stats").innerHTML = html;
    };
    paint();
    clearInterval(countdownTimer);
    if (info.mode === "match") {
      countdownTimer = setInterval(paint, 1000);
      if (!info.is_player) { note = errorText("not_a_player"); btn.disabled = true; }
      else if (info.status !== "RUNNING") { note = errorText(info.status === "LOBBY" ? "match_not_running" : "match_over"); btn.disabled = true; }
      else if (info.attempts_left <= 0) { note = info.seconds_left > 0 ? errorText("no_attempts_left") : errorText("match_over"); btn.disabled = true; }
      else note = "بهترین امتیازت حساب می‌شود. همه مرحله‌های یکسان می‌گیرند.";
    } else {
      note = "تمرین آزاد — بدون سکه";
    }
    $("start-note").textContent = note;
    run = null;
    fx.reset();
    drawIdle();
    updateHud();
    show("start");
    $("hud").classList.add("hidden");
  }

  function refreshInfo() {
    var body = game.matchToken ? { match_token: game.matchToken } : { game: game.key };
    return api("info", body).then(function (res) {
      if (res.ok) { game.info = res; game.infoAt = Date.now(); }
      return res;
    });
  }

  $("start-btn").addEventListener("click", function () { haptic("light"); startRun(); });
  $("again-btn").addEventListener("click", function () {
    haptic("light");
    refreshInfo().then(renderStart).catch(renderStart);
  });
  function leave() {
    if (game && game.info && game.info.mode !== "match") {
      location.href = BOOT.apiBase.replace(/api\/$/, "") + location.search;
      return;
    }
    if (tg) tg.close();
    else history.back();
  }
  $("close-btn").addEventListener("click", leave);
  $("error-close-btn").addEventListener("click", function () { if (tg) tg.close(); else history.back(); });

  if (tg && tg.BackButton) {
    try {
      tg.BackButton.onClick(function () {
        if (run && !run.ended) run.quit = true; // تلاش همان‌جا تمام و ثبت می‌شود
        else leave();
      });
    } catch (e) { /* قدیمی */ }
  }
  // خروج از صفحه یعنی پایان همان تلاش (جلوی توقف بازی برای وقت‌کشی را می‌گیرد)
  var keepAlive = BOOT.devAuth && query.get("dev_keepalive") === "1"; // فقط برای تست محلی
  document.addEventListener("visibilitychange", function () {
    if (document.hidden && run && !run.ended && !keepAlive) run.quit = true;
  });

  // ------------------------------------------------------------------ بارگذاری
  function showMenu() {
    var list = $("menu-list");
    list.innerHTML = "";
    BOOT.games.forEach(function (meta) {
      var a = document.createElement("a");
      a.className = "menu-item";
      a.href = BOOT.playBase + meta.key + "/" + location.search;
      a.innerHTML = '<span class="game-emoji">' + meta.emoji + "</span>";
      a.appendChild(document.createTextNode(meta.title));
      list.appendChild(a);
    });
    show("menu");
    $("hud").classList.add("hidden");
  }

  function boot() {
    if (!BOOT.gameKey && !startParam) { showMenu(); return; }
    if (!initData) { fail(errorText("auth_missing")); return; }
    game = { key: BOOT.gameKey, matchToken: BOOT.gameKey ? "" : startParam, assets: {} };
    refreshInfo().then(function (res) {
      if (!res.ok) { fail(errorText(res.error)); return null; }
      game.meta = res.game;
      game.key = res.game.key;
      var base = BOOT.staticBase + game.key + "/";
      return loadScript(base + "core.js").then(function () { return loadScript(base + "render.js"); }).then(function () {
        game.core = window.Arcade.cores[game.key];
        var names = game.core.assets || [];
        return Promise.all(names.map(function (name) {
          return fetch(base + name).then(function (r) { return r.json(); }).then(function (data) { game.assets[name] = data; });
        }));
      }).then(function () {
        game.renderer = window.Arcade.renderers[game.key](env);
        // وضعیت نمایشی پشت صفحه‌ی شروع
        game.idleState = game.core.newState(1, { assets: game.assets, variant: game.info.variant || "" });
        if (game.renderer.reset) game.renderer.reset(game.idleState);
        var ready = document.fonts && document.fonts.load ? document.fonts.load("700 20px Vazirmatn").catch(function () {}) : Promise.resolve();
        return Promise.race([ready, new Promise(function (r) { setTimeout(r, 1200); })]);
      }).then(function () {
        if (BOOT.devAuth && query.get("dev_snap")) return devSnapshot();
        renderStart();
      });
    }).catch(function () { fail("بارگذاری بازی انجام نشد. اتصال اینترنت را بررسی کن."); });
  }

  /* فقط توسعه: یک لاگ ورودی آزمایشی را تا تیک مشخص اجرا می‌کند و یک فریم می‌کشد
     (?dev_snap=<tick>&dev_case=<index>) — برای بررسی رندر بدون نیاز به انیمیشن. */
  function devSnapshot() {
    var ticks = parseInt(query.get("dev_snap"), 10) || 300;
    var index = parseInt(query.get("dev_case") || "0", 10);
    return fetch(BOOT.apiBase.replace(/api\/$/, "") + "dev/fixtures/" + game.key + ".json")
      .then(function (r) { return r.json(); })
      .then(function (cases) {
        var c = cases[index];
        var config = Object.assign({ assets: game.assets }, c.options || {});
        var state = game.core.newState(c.seed, config);
        var tickMs = game.core.TICK_MS, i = 0;
        if (game.renderer.reset) game.renderer.reset(state);
        run = { state: state, queue: [], log: [], tick: 0, acc: 0, ended: false };
        var drain = function () {
          for (var e = 0; e < state.events.length; e++) if (game.renderer.event) game.renderer.event(state.events[e], state);
          state.events.length = 0;
        };
        for (var tick = 0; tick < ticks && !state.over; tick++) {
          while (i < c.inputs.length && Math.floor(c.inputs[i][0] / tickMs) <= tick) {
            if (!state.over) game.core.applyInput(state, c.inputs[i]);
            drain();
            i++;
          }
          if (state.over) break;
          game.core.step(state);
          drain();
          if (tick % 4 === 0) { fx.update(64); beginFrame(); game.renderer.draw(ctx, state, 0); endFrame(); }
        }
        run.tick = tick;
        show(null);
        beginFrame();
        game.renderer.draw(ctx, state, 0);
        endFrame();
        updateHud();
        window.__snap = { tick: tick, score: state.score, over: state.over, cause: state.cause };
        run = null;
      });
  }

  boot();
})();
