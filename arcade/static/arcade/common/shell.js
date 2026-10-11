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

  /* کیفیت تطبیقی: اگر دستگاه نتواند نرخ فریم را نگه دارد، اول وضوح بوم و بعد افکت‌های سنگین
     کم می‌شوند. سطح انتخاب‌شده فقط تا یک روز به خاطر سپرده می‌شود تا کندی موقتی (مثلاً حالت
     صرفه‌جویی باتری) برای همیشه کیفیت را پایین نگه ندارد. ۲ = کامل، ۱ = متوسط، ۰ = سبک */
  var QUALITY = [
    { dpr: 1, particles: 60 },
    { dpr: 1.5, particles: 120 },
    { dpr: 2, particles: 220 },
  ];
  var QUALITY_MEMORY_MS = 24 * 60 * 60 * 1000;
  var quality = { level: 2, frames: 0, total: 0, slow: 0 };
  try {
    var savedQuality = JSON.parse(localStorage.getItem("arcade_quality") || "null");
    if (savedQuality && (savedQuality.level === 0 || savedQuality.level === 1) && Date.now() - savedQuality.at < QUALITY_MEMORY_MS) {
      quality.level = savedQuality.level;
    }
  } catch (e) { /* ممکن است در دسترس نباشد یا مقدار قدیمی باشد */ }

  var sprites = {};
  var spriteCount = 0;

  function resize() {
    var w = window.innerWidth, h = window.innerHeight;
    view.dpr = Math.min(window.devicePixelRatio || 1, QUALITY[quality.level].dpr);
    view.scale = Math.min(w / 360, h / 520);
    view.W = 360;
    view.H = h / view.scale;
    view.offsetX = (w - 360 * view.scale) / 2;
    canvas.width = Math.round(w * view.dpr);
    canvas.height = Math.round(h * view.dpr);
    env.W = view.W;
    env.H = view.H;
    env.res = Math.min(view.scale * view.dpr, 3);
    env.quality = quality.level;
    env.safeTop = (parseFloat(css("--tg-content-safe-area-inset-top", "0")) || 0) / view.scale + 96;
    // اندازه‌ها عوض شده: اسپرایت‌های کش‌شده دوباره (و فقط در صورت نیاز) ساخته می‌شوند
    sprites = {};
    spriteCount = 0;
  }

  function watchFrameRate(dt) {
    if (quality.level === 0) return;
    quality.frames++;
    if (quality.frames <= 45) return; // فریم‌های اول صرف ساخت اسپرایت‌ها می‌شوند
    quality.total += Math.min(dt, 100);
    if (quality.frames < 45 + 120) return;
    var average = quality.total / 120;
    quality.frames = 45;
    quality.total = 0;
    // کمتر از حدود ۴۳ فریم در ثانیه در دو بازه‌ی پیاپی
    quality.slow = average > 23 ? quality.slow + 1 : 0;
    if (quality.slow >= 2) {
      quality.slow = 0;
      quality.frames = 0; // اسپرایت‌ها دوباره ساخته می‌شوند؛ آن فریم‌ها در سنجش بعدی حساب نشوند
      quality.level--;
      try {
        localStorage.setItem("arcade_quality", JSON.stringify({ level: quality.level, at: Date.now() }));
      } catch (e) { /* مهم نیست */ }
      resize();
    }
  }

  function paintDot(color) {
    return function (s) {
      var g = s.createRadialGradient(16, 16, 0, 16, 16, 16);
      g.addColorStop(0, "rgba(255,255,255,1)");
      g.addColorStop(0.4, "rgba(255,255,255,.8)");
      g.addColorStop(1, "rgba(255,255,255,0)");
      s.fillStyle = g;
      s.fillRect(0, 0, 32, 32);
      s.globalCompositeOperation = "source-in";
      s.fillStyle = color;
      s.fillRect(0, 0, 32, 32);
    };
  }
  function dotSprite(color) {
    return env.sprite("fx:dot:" + color, 32, 32, paintDot(color));
  }

  var fx = {
    particles: [], chunks: [], rings: [], texts: [], shakeMag: 0, flashAlpha: 0, flashColor: "#fff",
    burst: function (x, y, color, count, speed) {
      count = count || 12;
      speed = speed || 3;
      var cap = QUALITY[quality.level].particles;
      for (var i = 0; i < count && this.particles.length < cap; i++) {
        var a = Math.random() * Math.PI * 2, s = (0.4 + Math.random()) * speed;
        this.particles.push({ x: x, y: y, vx: Math.cos(a) * s, vy: Math.sin(a) * s - 1, life: 1, color: color, size: 2 + Math.random() * 3 });
      }
    },
    /* خرده‌های جامد چرخان (چوب، آجر، سنگ) که با جاذبه می‌افتند */
    debris: function (x, y, color, count, speed, size) {
      count = count || 8;
      speed = speed || 4;
      size = size || 5;
      var cap = QUALITY[quality.level].particles;
      for (var i = 0; i < count && this.chunks.length < cap / 2; i++) {
        var a = Math.random() * Math.PI * 2, s = (0.5 + Math.random()) * speed;
        this.chunks.push({
          x: x, y: y, vx: Math.cos(a) * s, vy: Math.sin(a) * s - speed * 0.6, life: 1, color: color,
          w: size * (0.5 + Math.random()), h: size * (0.3 + Math.random() * 0.5), rot: Math.random() * 6.28, spin: (Math.random() - 0.5) * 0.5,
        });
      }
    },
    /* حلقه‌ی موج ضربه */
    ring: function (x, y, color, from, to) {
      if (this.rings.length < 12) this.rings.push({ x: x, y: y, color: color, from: from || 6, to: to || 46, life: 1 });
    },
    shake: function (magnitude) { this.shakeMag = Math.min(10, Math.max(this.shakeMag, magnitude)); },
    flash: function (color, alpha) { this.flashColor = color; this.flashAlpha = alpha || 0.5; },
    text: function (x, y, text, color) { this.texts.push({ x: x, y: y, text: text, color: color || colors.gold, life: 1 }); },
    reset: function () { this.particles = []; this.chunks = []; this.rings = []; this.texts = []; this.shakeMag = 0; this.flashAlpha = 0; },
    update: function (dt) {
      var k = dt / 16.7, i, p;
      for (i = this.particles.length - 1; i >= 0; i--) {
        p = this.particles[i];
        p.x += p.vx * k; p.y += p.vy * k; p.vy += 0.16 * k; p.life -= 0.022 * k;
        if (p.life <= 0) this.particles.splice(i, 1);
      }
      for (i = this.chunks.length - 1; i >= 0; i--) {
        p = this.chunks[i];
        p.x += p.vx * k; p.y += p.vy * k; p.vy += 0.34 * k; p.rot += p.spin * k; p.life -= 0.018 * k;
        if (p.life <= 0) this.chunks.splice(i, 1);
      }
      for (i = this.rings.length - 1; i >= 0; i--) {
        p = this.rings[i];
        p.life -= 0.05 * k;
        if (p.life <= 0) this.rings.splice(i, 1);
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
      for (i = 0; i < this.chunks.length; i++) {
        p = this.chunks[i];
        c.globalAlpha = clamp(p.life * 2.5, 0, 1);
        c.fillStyle = p.color;
        var cos = Math.cos(p.rot), sin = Math.sin(p.rot);
        c.beginPath();
        c.moveTo(p.x - cos * p.w + sin * p.h, p.y - sin * p.w - cos * p.h);
        c.lineTo(p.x + cos * p.w + sin * p.h, p.y + sin * p.w - cos * p.h);
        c.lineTo(p.x + cos * p.w - sin * p.h, p.y + sin * p.w + cos * p.h);
        c.lineTo(p.x - cos * p.w - sin * p.h, p.y - sin * p.w + cos * p.h);
        c.fill();
      }
      for (i = 0; i < this.rings.length; i++) {
        p = this.rings[i];
        c.globalAlpha = clamp(p.life, 0, 1) * 0.8;
        c.strokeStyle = p.color;
        c.lineWidth = 1 + p.life * 3;
        c.beginPath();
        c.arc(p.x, p.y, p.from + (p.to - p.from) * (1 - p.life * p.life), 0, 6.2832);
        c.stroke();
      }
      // جرقه‌ها: یک نقطه‌ی نرمِ کش‌شده برای هر رنگ (خیلی ارزان‌تر از کشیدن دایره در هر فریم)
      c.globalCompositeOperation = "lighter";
      for (i = 0; i < this.particles.length; i++) {
        p = this.particles[i];
        c.globalAlpha = clamp(p.life, 0, 1);
        var d = p.size * 3.4;
        c.drawImage(dotSprite(p.color).canvas, p.x - d / 2, p.y - d / 2, d, d);
      }
      c.globalCompositeOperation = "source-over";
      c.textAlign = "center";
      c.font = "900 21px Vazirmatn, Tahoma, sans-serif";
      c.lineJoin = "round";
      c.lineWidth = 4;
      c.strokeStyle = "rgba(8,10,24,.7)";
      for (i = 0; i < this.texts.length; i++) {
        p = this.texts[i];
        c.globalAlpha = clamp(p.life * 1.4, 0, 1);
        c.strokeText(p.text, p.x, p.y);
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
    /* درخشش با سایه‌ی بوم: glow(c, color, blur) و برای خاموش کردن glow(c).
       گران است؛ فقط داخل اسپرایت‌های کش‌شده استفاده شود. در کیفیت سبک خاموش است. */
    glow: function (c, color, blur) {
      var on = color && quality.level > 0;
      c.shadowColor = on ? color : "transparent";
      c.shadowBlur = on ? (blur || 14) * env.res : 0;
      c.shadowOffsetX = c.shadowOffsetY = 0;
    },
    /* سایه‌ی افتاده برای استفاده داخل اسپرایت‌ها؛ dropShadow(c) خاموشش می‌کند */
    dropShadow: function (c, blur, dy, a) {
      if (!blur) { c.shadowColor = "transparent"; c.shadowBlur = 0; c.shadowOffsetY = 0; return; }
      c.shadowColor = "rgba(0,0,0," + (a === undefined ? 0.45 : a) + ")";
      c.shadowBlur = blur * env.res;
      c.shadowOffsetX = 0;
      c.shadowOffsetY = (dy === undefined ? blur * 0.5 : dy) * env.res;
    },
    /* اسپرایت کش‌شده: paint(c, w, h) فقط یک بار (تا تغییر اندازه‌ی صفحه) اجرا می‌شود.
       pad حاشیه‌ی اضافه برای سایه و هاله است. کلید باید هر چیزی را که شکل را عوض می‌کند داشته باشد. */
    sprite: function (key, w, h, paint, pad) {
      var sp = sprites[key];
      if (sp) return sp;
      if (spriteCount > 400) { sprites = {}; spriteCount = 0; } // محافظ در برابر کلیدهای بی‌شمار
      pad = pad || 0;
      var res = env.res;
      var cv = document.createElement("canvas");
      cv.width = Math.max(1, Math.ceil((w + pad * 2) * res));
      cv.height = Math.max(1, Math.ceil((h + pad * 2) * res));
      var sc = cv.getContext("2d");
      sc.scale(res, res);
      sc.translate(pad, pad);
      paint(sc, w, h);
      sp = sprites[key] = { canvas: cv, w: w, h: h, pad: pad, fw: w + pad * 2, fh: h + pad * 2 };
      spriteCount++;
      return sp;
    },
    /* آزاد کردن اسپرایتی که دیگر لازم نیست (برای اسپرایت‌های موقتی مثل طبقه‌های رد‌شده) */
    forget: function (key) {
      if (sprites[key]) {
        delete sprites[key];
        spriteCount--;
      }
    },
    /* کشیدن اسپرایت با گوشه‌ی بالا-چپ در (x, y) */
    blit: function (c, sp, x, y) {
      c.drawImage(sp.canvas, x - sp.pad, y - sp.pad, sp.fw, sp.fh);
    },
    /* کشیدن اسپرایت با مرکز در (x, y)، با چرخش و مقیاس دلخواه */
    blitC: function (c, sp, x, y, rot, sx, sy) {
      if (sx === undefined) sx = 1;
      if (sy === undefined) sy = sx;
      if (!rot && sx === 1 && sy === 1) {
        c.drawImage(sp.canvas, x - sp.fw / 2, y - sp.fh / 2, sp.fw, sp.fh);
        return;
      }
      c.save();
      c.translate(x, y);
      if (rot) c.rotate(rot);
      c.drawImage(sp.canvas, (-sp.fw / 2) * sx, (-sp.fh / 2) * sy, sp.fw * sx, sp.fh * sy);
      c.restore();
    },
    /* پس‌زمینه‌ی تمام‌صفحه‌ی ثابت یک بازی. paint(c, w, h, bleed) باید از ‎-bleed تا w+bleed را پر کند
       تا لرزش صفحه لبه‌ی خالی نشان ندهد. */
    scene: function (c, key, paint) {
      var bleed = 12;
      var sp = env.sprite("scene:" + key, env.W, env.H, function (s, w, h) { paint(s, w, h, bleed); }, bleed);
      c.drawImage(sp.canvas, -bleed, -bleed, sp.fw, sp.fh);
    },
    clamp: clamp,
    lerp: function (a, b, t) { return a + (b - a) * t; },
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
  env.art = window.ArcadeArt(env);
  resize();
  var icons = window.ArcadeIcons ? window.ArcadeIcons(env) : null;
  /* نماد تصویری بازی را در el می‌گذارد؛ اگر نمادی نباشد همان ایموجی می‌ماند */
  function setIcon(el, key, emoji, px) {
    el.textContent = "";
    var canvas = icons && icons.has(key) ? icons.element(key, px) : null;
    if (canvas) el.appendChild(canvas);
    else el.textContent = emoji;
  }
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

  var frameClipped = false;
  function beginFrame() {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.shadowBlur = 0;
    ctx.shadowColor = "transparent";
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
    // بازی‌هایی که خودشان کل صفحه را می‌کشند پس‌زمینه‌ی مشترک لازم ندارند (مگر در صفحه‌های پهن)
    var own = game && game.renderer && game.renderer.ownBackground;
    if (!own || view.offsetX > 0.5) paintBackdrop();
    var s = view.dpr * view.scale;
    var sx = 0, sy = 0;
    if (fx.shakeMag) {
      sx = (Math.random() - 0.5) * fx.shakeMag;
      sy = (Math.random() - 0.5) * fx.shakeMag;
    }
    ctx.setTransform(s, 0, 0, s, (view.offsetX + sx * view.scale) * view.dpr, sy * view.scale * view.dpr);
    // در صفحه‌های پهن، بازی فقط داخل ستون خودش کشیده می‌شود
    frameClipped = view.offsetX > 0.5;
    if (frameClipped) {
      ctx.save();
      ctx.beginPath();
      ctx.rect(0, -20, view.W, view.H + 40);
      ctx.clip();
    }
  }
  function endFrame() {
    ctx.shadowBlur = 0;
    ctx.globalAlpha = 1;
    fx.draw(ctx);
    if (frameClipped) {
      ctx.restore();
      frameClipped = false;
    }
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

  var hudScoreEl = $("hud-score"), hudSubEl = $("hud-sub");
  var hudShown = { score: null, sub: null };
  function updateHud() {
    var state = run ? run.state : game.idleState;
    var score = state ? state.score : 0;
    if (score !== hudShown.score) {
      hudShown.score = score;
      hudScoreEl.textContent = fa(score);
    }
    var sub = game.renderer.hud ? game.renderer.hud(state) : "";
    if (run && run.deadline) {
      var left = Math.max(0, Math.ceil((run.deadline - Date.now()) / 1000));
      if (left <= 60) sub = (sub ? sub + " · " : "") + "⏳ " + fa(left);
    }
    if (sub !== hudShown.sub) {
      hudShown.sub = sub;
      hudSubEl.textContent = sub;
    }
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
    if (!run.ended) watchFrameRate(dt);

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
      quality.frames = 0;
      quality.total = 0;
      quality.slow = 0;
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

  var countTimer = null;
  /* امتیاز از صفر تا مقدار نهایی بالا می‌رود */
  function countUp(el, value) {
    clearInterval(countTimer);
    if (value <= 0) { el.textContent = fa(0); return; }
    var started = performance.now(), duration = Math.min(900, 300 + value * 4);
    countTimer = setInterval(function () {
      var t = Math.min(1, (performance.now() - started) / duration);
      el.textContent = fa(Math.round(value * (1 - Math.pow(1 - t, 3))));
      if (t >= 1) clearInterval(countTimer);
    }, 30);
  }
  function confetti() {
    var box = $("confetti");
    box.innerHTML = "";
    var palette = ["#ffd257", "#6ee7ff", "#ff5c7a", "#5ee6a8", "#a78bfa"];
    for (var i = 0; i < 26; i++) {
      var piece = document.createElement("i");
      piece.style.left = Math.random() * 100 + "%";
      piece.style.background = palette[i % palette.length];
      piece.style.animationDelay = Math.random() * 0.5 + "s";
      piece.style.animationDuration = 1.3 + Math.random() * 0.9 + "s";
      piece.style.transform = "rotate(" + Math.random() * 360 + "deg)";
      box.appendChild(piece);
    }
  }

  function renderOver(current) {
    var res = current.result;
    var local = current.state.score;
    var again = $("again-btn");
    $("over-note").textContent = "";
    $("over-badge").classList.add("hidden");
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
      if (!current.celebrated) {
        current.celebrated = true;
        countUp($("over-score"), res.verified_score);
        // رکورد شخصی تازه (نسبت به رکوردی که هنگام شروع این تلاش داشت)
        if (res.verified_score > 0 && res.verified_score > (game.info.record || 0)) {
          $("over-badge").classList.remove("hidden");
          confetti();
        }
      } else {
        $("over-score").textContent = fa(res.verified_score);
      }
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
    setIcon($("start-emoji"), game.meta.key, game.meta.emoji, 92);
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
      var badge = document.createElement("span");
      badge.className = "game-emoji";
      setIcon(badge, meta.key, meta.emoji, 76);
      a.appendChild(badge);
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
      var ver = "?v=" + (BOOT.version || "1");
      return loadScript(base + "core.js" + ver).then(function () { return loadScript(base + "render.js" + ver); }).then(function () {
        game.core = window.Arcade.cores[game.key];
        var names = game.core.assets || [];
        return Promise.all(names.map(function (name) {
          return fetch(base + name + ver).then(function (r) { return r.json(); }).then(function (data) { game.assets[name] = data; });
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
        // میانگین زمان کشیدن یک فریم (میلی‌ثانیه) برای مقایسه‌ی سرعت رندر
        window.__bench = function (frames) {
          var t0 = performance.now();
          for (var n = 0; n < frames; n++) {
            fx.update(16.7);
            beginFrame();
            game.renderer.draw(ctx, state, (n % 4) / 4);
            endFrame();
          }
          ctx.getImageData(0, 0, 1, 1);
          return (performance.now() - t0) / frames;
        };
        run = null;
      });
  }

  boot();
})();
