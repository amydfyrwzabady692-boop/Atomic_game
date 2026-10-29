/* صداهای کوتاه صفحه‌های بازی (شطرنج، پوکر، دوز) بدون هیچ فایل صوتی: همه با WebAudio ساخته می‌شوند.
   مرورگرها تا اولین لمس کاربر اجازه‌ی پخش صدا نمی‌دهند؛ همین فایل با اولین لمس صدا را باز می‌کند.
   روشن/خاموش بودن صدا برای همه‌ی بازی‌ها یکی است و در localStorage می‌ماند. */
(function () {
  "use strict";

  var KEY = "arcade.muted";
  var muted = false;
  try {
    var saved = window.localStorage.getItem(KEY);
    if (saved === null) saved = window.localStorage.getItem("chess.muted"); // تنظیم نسخه‌ی قبلی صفحه‌ی شطرنج
    muted = saved === "1";
  } catch (e) { /* حالت خصوصی */ }

  var ctx = null;
  function context() {
    if (ctx) return ctx;
    var Ctor = window.AudioContext || window.webkitAudioContext;
    if (!Ctor) return null;
    try { ctx = new Ctor(); } catch (e) { ctx = null; }
    return ctx;
  }
  function unlock() {
    if (muted) return;
    var audio = context();
    if (audio && audio.state === "suspended") { try { audio.resume(); } catch (e) { /* قدیمی */ } }
  }

  function tone(at, freq, length, gain, type, endFreq) {
    var osc = ctx.createOscillator();
    osc.type = type || "sine";
    osc.frequency.setValueAtTime(freq, at);
    if (endFreq) osc.frequency.exponentialRampToValueAtTime(endFreq, at + length);
    var level = ctx.createGain();
    level.gain.setValueAtTime(0.0001, at);
    level.gain.exponentialRampToValueAtTime(gain, at + 0.008);
    level.gain.exponentialRampToValueAtTime(0.0001, at + length);
    osc.connect(level);
    level.connect(ctx.destination);
    osc.start(at);
    osc.stop(at + length + 0.02);
  }
  function noise(at, length, kind, freq, gain, endFreq, q) {
    var buffer = ctx.createBuffer(1, Math.max(1, Math.floor(ctx.sampleRate * length)), ctx.sampleRate);
    var data = buffer.getChannelData(0);
    for (var i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / data.length, 3);
    var source = ctx.createBufferSource();
    source.buffer = buffer;
    var filter = ctx.createBiquadFilter();
    filter.type = kind;
    filter.frequency.setValueAtTime(freq, at);
    if (endFreq) filter.frequency.exponentialRampToValueAtTime(endFreq, at + length);
    filter.Q.value = q || 1;
    var level = ctx.createGain();
    level.gain.setValueAtTime(gain, at);
    level.gain.exponentialRampToValueAtTime(0.001, at + length);
    source.connect(filter);
    filter.connect(level);
    level.connect(ctx.destination);
    source.start(at);
    source.stop(at + length);
  }
  // ضربه‌ی چوبی مهره روی تخته
  function knock(at, freq, gain, length) {
    noise(at, length, "bandpass", freq, gain, 0, 1.4);
    tone(at, freq / 7, length, gain * 0.5, "sine", freq / 12);
  }

  var SOUNDS = {
    move: function (t) { knock(t, 1600, 0.55, 0.09); },
    capture: function (t) { knock(t, 1150, 0.9, 0.13); knock(t + 0.045, 2100, 0.45, 0.08); },
    check: function (t) { tone(t, 880, 0.12, 0.16, "triangle"); tone(t + 0.13, 660, 0.2, 0.16, "triangle"); },
    low: function (t) { tone(t, 1250, 0.08, 0.12, "square"); },
    start: function (t) { tone(t, 523, 0.12, 0.14, "triangle"); tone(t + 0.12, 784, 0.18, 0.14, "triangle"); },
    turn: function (t) { tone(t, 988, 0.12, 0.1, "sine"); tone(t + 0.1, 1319, 0.2, 0.09, "sine"); },
    win: function (t) { [523, 659, 784, 1047].forEach(function (f, i) { tone(t + i * 0.11, f, 0.22, 0.16, "triangle"); }); },
    lose: function (t) { [523, 440, 349].forEach(function (f, i) { tone(t + i * 0.16, f, 0.28, 0.14, "sine"); }); },
    draw: function (t) { tone(t, 587, 0.2, 0.14, "triangle"); tone(t + 0.2, 587, 0.25, 0.14, "triangle"); },
    // ژتون‌های سرامیکی پوکر، پخش کارت و فولد
    chip: function (t) { tone(t, 2600, 0.05, 0.12, "triangle", 1900); tone(t + 0.05, 3100, 0.06, 0.1, "triangle", 2300); noise(t, 0.04, "highpass", 4000, 0.2); },
    chips: function (t) { for (var i = 0; i < 4; i++) tone(t + i * 0.045, 2400 + i * 230, 0.05, 0.09, "triangle", 1800); },
    deal: function (t) { noise(t, 0.08, "highpass", 2600, 0.4, 0, 0.7); },
    fold: function (t) { noise(t, 0.2, "bandpass", 1600, 0.3, 380, 0.8); },
    drop: function (t) { tone(t, 330, 0.16, 0.2, "sine", 160); knock(t + 0.02, 900, 0.35, 0.08); },
  };

  function play(kind) {
    if (muted || !SOUNDS[kind]) return;
    var audio = context();
    if (!audio) return;
    if (audio.state !== "running") { unlock(); return; }
    try { SOUNDS[kind](audio.currentTime + 0.01); } catch (e) { /* صدا اختیاری است */ }
  }
  function setMuted(value) {
    muted = !!value;
    try { window.localStorage.setItem(KEY, muted ? "1" : "0"); } catch (e) { /* حالت خصوصی */ }
    if (!muted) unlock();
  }

  ["pointerdown", "touchstart", "keydown"].forEach(function (name) {
    window.addEventListener(name, unlock, { passive: true });
  });
  window.SFX = { play: play, unlock: unlock, setMuted: setMuted, isMuted: function () { return muted; } };
})();
