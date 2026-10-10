/* «زمان‌سنج» — منطق قطعی. معادل پایتونی: arcade/sim/timing.py */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(require("../common/rng.js"));
  else root.Arcade.registerCore("timing", factory(root.ArcadeRng));
})(typeof self !== "undefined" ? self : this, function (R) {
  "use strict";
  var Rng = R.Rng, idiv = R.idiv;

  var TICK_MS = 16;
  var BAR = 10000;
  var LIMIT_TICKS = 3750; // ۶۰ ثانیه
  var LIVES = 3;

  function newZone(state) {
    var w = Math.max(700, 2600 - state.level * 80);
    state.zone = { s: state.rng.range(300, BAR - 300 - w), w: w };
    state.speed = Math.min(330, 90 + state.level * 7);
  }

  var core = {
    key: "timing",
    TICK_MS: TICK_MS,
    BAR: BAR,
    LIMIT_TICKS: LIMIT_TICKS,
    MAX_DURATION_MS: 61000,

    newState: function (seed, config) {
      var state = {
        seed: seed >>> 0, rng: new Rng(seed), tick: 0, over: false, cause: "", score: 0, level: 0,
        pos: 0, dir: 1, lives: LIVES, zone: null, speed: 0, events: [],
      };
      newZone(state);
      return state;
    },

    /* ورودی: [t_ms] — توقف نشانگر */
    applyInput: function (state, ev) {
      if (state.over) return;
      var z = state.zone;
      if (state.pos >= z.s && state.pos <= z.s + z.w) {
        var d = Math.abs(state.pos - (z.s + idiv(z.w, 2)));
        var perfect = d * 5 <= z.w;
        state.score += perfect ? 20 : 10;
        state.level++;
        state.events.push(perfect ? "perfect" : "hit");
        newZone(state);
      } else {
        state.lives--;
        state.events.push("miss");
        if (state.lives <= 0) {
          state.over = true;
          state.cause = "miss";
          state.events.push("fail");
        }
      }
    },

    step: function (state) {
      state.pos += state.dir * state.speed;
      if (state.pos >= BAR) { state.pos = BAR; state.dir = -1; }
      else if (state.pos <= 0) { state.pos = 0; state.dir = 1; }
      state.tick++;
      if (state.tick >= LIMIT_TICKS) {
        state.over = true;
        state.cause = "time";
        state.events.push("timeup");
      }
    },
  };
  return core;
});
