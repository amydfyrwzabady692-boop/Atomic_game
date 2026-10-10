/* «سیخ‌زن» — منطق قطعی. معادل پایتونی: arcade/sim/pins.py
   همه‌ی زاویه‌ها عدد صحیح‌اند: ۱۰۰۰ واحد = یک درجه. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(require("../common/rng.js"));
  else root.Arcade.registerCore("pins", factory(root.ArcadeRng));
})(typeof self !== "undefined" ? self : this, function (R) {
  "use strict";
  var Rng = R.Rng, idiv = R.idiv, mod = R.mod;

  var TICK_MS = 16;
  var CIRCLE = 360000;
  var BOTTOM = 90000; // نقطه‌ی برخورد سیخ: پایین دایره
  var THRESHOLD = 11000; // دو سیخ با فاصله‌ی زاویه‌ای کمتر از این برخورد می‌کنند
  var FLIGHT_TICKS = 5;
  var PAUSE_TICKS = 45;
  var PIN_POINTS = 10;

  var PATTERNS = [
    [[1000, 100, 0]],
    [[1800, 100, 0], [1000, -100, 0]],
    [[1200, 100, 0], [400, 0, 0], [700, -100, 0], [400, 0, 0]],
    [[1500, 60, 0], [900, 170, 0]],
    [[2000, 160, 1], [2000, 40, 1]],
    [[900, 100, 0], [600, -140, 0], [600, 60, 0]],
    [[1500, 150, 1], [700, 0, 1], [900, -150, 1], [700, 0, 1]],
  ];

  function loadLevel(state) {
    var index = state.level;
    var rng = new Rng((state.seed + index * 7919) >>> 0);
    var angle = rng.int(360) * 1000;
    var lv, pre = [], i;
    if (index < state.levels.length) {
      var raw = state.levels[index];
      for (i = 0; i < raw.pre.length; i++) pre.push(raw.pre[i] * 1000);
      lv = { pins: raw.pins, speed: raw.speed, pattern: raw.pattern, boss: !!raw.boss };
    } else {
      // تولید رویه‌ای از روی seed برای مراحل بعد از مراحل دست‌ساز
      var pins = 7 + rng.int(6);
      var count = rng.int(5);
      var used = {};
      while (pre.length < count) {
        var slot = rng.int(18);
        if (!used[slot]) {
          used[slot] = true;
          pre.push(slot * 20000);
        }
      }
      var speed = 1500 + Math.min(index, 120) * 10 + rng.int(500);
      lv = { pins: pins, speed: speed, pattern: PATTERNS[rng.int(PATTERNS.length)], boss: index % 5 === 4 };
    }
    var total = 0;
    for (i = 0; i < lv.pattern.length; i++) total += lv.pattern[i][0];
    lv.total = total;
    state.lv = lv;
    state.angle = angle;
    state.pins = pre;
    state.remaining = lv.pins;
    state.flights = [];
    state.ltick = 0;
  }

  function speedAt(lv, ltick) {
    var pattern = lv.pattern, n = pattern.length;
    var ms = mod(ltick * TICK_MS, lv.total);
    var acc = 0;
    for (var i = 0; i < n; i++) {
      var seg = pattern[i];
      if (ms < acc + seg[0]) {
        var pct = seg[1];
        if (seg[2]) {
          var prev = pattern[(i + n - 1) % n][1];
          pct = prev + idiv((seg[1] - prev) * (ms - acc), seg[0]);
        }
        return idiv(lv.speed * pct, 100);
      }
      acc += seg[0];
    }
    return lv.speed;
  }

  function land(state) {
    var local = mod(BOTTOM - state.angle, CIRCLE);
    for (var i = 0; i < state.pins.length; i++) {
      var d = Math.abs(state.pins[i] - local);
      if (d > CIRCLE - d) d = CIRCLE - d;
      if (d < THRESHOLD) {
        state.over = true;
        state.cause = "hit";
        state.hitAngle = local;
        state.events.push("fail");
        return;
      }
    }
    state.pins.push(local);
    state.remaining--;
    state.score += PIN_POINTS;
    state.events.push("stick");
    if (state.remaining === 0) {
      var secs = idiv(state.ltick * TICK_MS, 1000);
      var bonus = 20 - Math.max(0, secs - state.lv.pins);
      if (bonus < 0) bonus = 0;
      state.level++;
      state.score += 100 + 20 * state.level + bonus;
      state.pause = PAUSE_TICKS;
      state.flights = [];
      state.events.push("clear");
    }
  }

  var core = {
    key: "pins",
    TICK_MS: TICK_MS,
    CIRCLE: CIRCLE,
    BOTTOM: BOTTOM,
    FLIGHT_TICKS: FLIGHT_TICKS,
    PAUSE_TICKS: PAUSE_TICKS,
    assets: ["levels.json"],
    speedAt: speedAt,

    newState: function (seed, config) {
      var state = {
        seed: seed >>> 0,
        levels: (config.assets && config.assets["levels.json"]) || [],
        tick: 0,
        over: false,
        cause: "",
        score: 0,
        level: 0,
        pause: 0,
        events: [],
      };
      loadLevel(state);
      return state;
    },

    /* ورودی: [t_ms] — یک تپ یعنی شلیک یک سیخ */
    applyInput: function (state, ev) {
      if (state.over || state.pause > 0) return;
      if (state.remaining - state.flights.length > 0) {
        state.flights.push(state.tick + FLIGHT_TICKS);
        state.events.push("throw");
      }
    },

    step: function (state) {
      if (state.pause > 0) {
        state.pause--;
        if (state.pause === 0) loadLevel(state);
        state.tick++;
        return;
      }
      state.angle = mod(state.angle + speedAt(state.lv, state.ltick), CIRCLE);
      while (state.flights.length && state.flights[0] <= state.tick && !state.over && state.pause === 0) {
        state.flights.shift();
        land(state);
      }
      state.ltick++;
      state.tick++;
    },
  };
  return core;
});
