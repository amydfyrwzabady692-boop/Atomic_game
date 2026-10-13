/* «هیزم‌شکن» — منطق قطعی. معادل پایتونی: arcade/sim/timber.py
   هر تکه‌ی تنه: b = شاخه (۰ هیچ، ۱ چپ، ۲ راست)، c = آیتم ساعت (۰ هیچ، ۱ چپ، ۲ راست). */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(require("../common/rng.js"));
  else root.Arcade.registerCore("timber", factory(root.ArcadeRng));
})(typeof self !== "undefined" ? self : this, function (R) {
  "use strict";
  var Rng = R.Rng, idiv = R.idiv;

  var TICK_MS = 16;
  var VISIBLE = 9;
  var MAX_TIME = 10000;
  var START_TIME = 5000;
  var GAIN = 360;
  var CLOCK_GAIN = 1500;
  var FAST_TICKS = 14;

  /* قانون تولید: بعد از شاخه‌ی یک طرف، تکه‌ی بعدی نمی‌تواند شاخه‌ی طرف مخالف داشته باشد؛
     پس همیشه یک راه سالم هست. */
  function generate(state) {
    var g = state.gen, rng = state.rng;
    var i = g.index++;
    if (i < 3) return { b: 0, c: 0 };
    var lvl = Math.min(idiv(i, 20), 10);
    var b = 0;
    if (g.run > 0) {
      g.run--;
      b = g.runSide;
    } else if (rng.int(100) < 45 + lvl * 4) {
      var side = rng.int(2) + 1;
      if (g.prev === 0 || g.prev === side) {
        b = side;
        if (lvl >= 2 && rng.int(100) < 10 + lvl * 3) {
          g.run = 1 + rng.int(2);
          g.runSide = side;
        }
      }
    }
    var c = 0;
    if (lvl >= 1 && rng.int(100) < 6) c = b === 0 ? rng.int(2) + 1 : 3 - b;
    g.prev = b;
    return { b: b, c: c };
  }

  function drainFor(level) { return Math.min(60, 20 + level * 4); }

  var core = {
    key: "timber",
    TICK_MS: TICK_MS,
    MAX_TIME: MAX_TIME,
    VISIBLE: VISIBLE,

    newState: function (seed, config) {
      var state = {
        seed: seed >>> 0, rng: new Rng(seed), tick: 0, over: false, cause: "", score: 0, level: 0,
        side: 0, chops: 0, time: START_TIME, started: false, lastChop: -1000, streak: 0,
        gen: { index: 0, prev: 0, run: 0, runSide: 0 }, segs: [], events: [],
      };
      for (var i = 0; i < VISIBLE; i++) state.segs.push(generate(state));
      return state;
    },

    /* ورودی: [t_ms, side] — ۰ یعنی ضربه از چپ، ۱ از راست */
    applyInput: function (state, ev) {
      var side = ev[1];
      if (state.over || (side !== 0 && side !== 1)) return;
      state.started = true;
      state.side = side;
      if (state.segs[0].b === side + 1) {
        state.over = true;
        state.cause = "branch";
        state.events.push("fail");
        return;
      }
      var seg = state.segs.shift();
      state.segs.push(generate(state));
      state.chops++;
      state.score++;
      if (seg.c === side + 1) {
        state.time = Math.min(MAX_TIME, state.time + CLOCK_GAIN);
        state.events.push("clock");
      }
      state.time = Math.min(MAX_TIME, state.time + GAIN);
      if (state.tick - state.lastChop <= FAST_TICKS) {
        state.streak++;
        if (state.streak % 10 === 0) {
          state.score += 5;
          state.events.push("combo");
        }
      } else {
        state.streak = 0;
      }
      state.lastChop = state.tick;
      state.level = idiv(state.chops, 20);
      state.events.push("chop");
      if (state.segs[0].b === side + 1) {
        state.over = true;
        state.cause = "branch";
        state.events.push("fail");
      }
    },

    step: function (state) {
      if (state.started) {
        state.time -= drainFor(state.level);
        if (state.time <= 0) {
          state.time = 0;
          state.over = true;
          state.cause = "time";
          state.events.push("fail");
        }
      }
      state.tick++;
    },
  };
  return core;
});
