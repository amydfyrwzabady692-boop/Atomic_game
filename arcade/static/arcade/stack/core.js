/* «برج‌ساز» — منطق قطعی. معادل پایتونی: arcade/sim/stack.py
   واحد افقی: ۱۰ واحد = یک پیکسل منطقی (عرض زمین ۳۶۰۰). */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(require("../common/rng.js"));
  else root.Arcade.registerCore("stack", factory(root.ArcadeRng));
})(typeof self !== "undefined" ? self : this, function (R) {
  "use strict";
  var idiv = R.idiv;

  var TICK_MS = 16;
  var FIELD = 3600;
  var BASE_W = 1800;
  var PERFECT = 60; // خطای مجاز برای ضربه‌ی دقیق

  function spawn(state) {
    var prev = state.blocks[state.blocks.length - 1];
    var count = state.blocks.length - 1;
    var w = prev.w;
    state.cur = {
      w: w,
      x: count % 2 === 0 ? -idiv(w, 2) : FIELD - idiv(w, 2),
      dir: count % 2 === 0 ? 1 : -1,
      speed: 28 + Math.min(count, 52),
    };
  }

  var core = {
    key: "stack",
    TICK_MS: TICK_MS,
    FIELD: FIELD,

    newState: function (seed, config) {
      var state = {
        seed: seed >>> 0, tick: 0, over: false, cause: "", score: 0, level: 0,
        combo: 0, blocks: [{ x: idiv(FIELD - BASE_W, 2), w: BASE_W }], cur: null, lastCut: null, events: [],
      };
      spawn(state);
      return state;
    },

    /* ورودی: [t_ms] — انداختن بلوک */
    applyInput: function (state, ev) {
      if (state.over) return;
      var cur = state.cur, prev = state.blocks[state.blocks.length - 1];
      var diff = cur.x - prev.x;
      if (Math.abs(diff) <= PERFECT) {
        state.combo++;
        state.blocks.push({ x: prev.x, w: prev.w });
        state.score += 10 + Math.min(state.combo, 10) * 5;
        state.lastCut = null;
        state.events.push("perfect");
      } else {
        var left = Math.max(cur.x, prev.x);
        var right = Math.min(cur.x + cur.w, prev.x + prev.w);
        var overlap = right - left;
        if (overlap <= 0) {
          state.over = true;
          state.cause = "miss";
          state.lastCut = { x: cur.x, w: cur.w };
          state.events.push("fail");
          return;
        }
        state.combo = 0;
        state.lastCut = diff > 0 ? { x: right, w: cur.w - overlap } : { x: cur.x, w: cur.w - overlap };
        state.blocks.push({ x: left, w: overlap });
        state.score += 10;
        state.events.push("cut");
      }
      state.level = state.blocks.length - 1;
      spawn(state);
    },

    step: function (state) {
      var cur = state.cur;
      var lo = -idiv(cur.w, 2), hi = FIELD - idiv(cur.w, 2);
      cur.x += cur.dir * cur.speed;
      if (cur.x >= hi) { cur.x = hi; cur.dir = -1; }
      else if (cur.x <= lo) { cur.x = lo; cur.dir = 1; }
      state.tick++;
    },
  };
  return core;
});
