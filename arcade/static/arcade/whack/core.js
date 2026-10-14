/* «موش‌زن» — منطق قطعی. معادل پایتونی: arcade/sim/whack.py
   نوع هر سوراخ: ۰ خالی، ۱ عادی، ۲ بمب‌دار، ۳ طلایی. ترتیب و زمان ظاهر شدن از seed می‌آید. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(require("../common/rng.js"));
  else root.Arcade.registerCore("whack", factory(root.ArcadeRng));
})(typeof self !== "undefined" ? self : this, function (R) {
  "use strict";
  var Rng = R.Rng, idiv = R.idiv;

  var TICK_MS = 16;
  var LIMIT_TICKS = 3750; // ۶۰ ثانیه
  var HOLES = 9;

  var core = {
    key: "whack",
    TICK_MS: TICK_MS,
    LIMIT_TICKS: LIMIT_TICKS,
    MAX_DURATION_MS: 61000,

    newState: function (seed, config) {
      var holes = [];
      for (var i = 0; i < HOLES; i++) holes.push({ type: 0, until: 0, born: 0 });
      return {
        seed: seed >>> 0, rng: new Rng(seed), tick: 0, over: false, cause: "", score: 0, level: 0,
        hits: 0, holes: holes, nextSpawn: 30, lastHole: -1, events: [],
      };
    },

    /* ورودی: [t_ms, hole] — شماره‌ی سوراخ ۰ تا ۸ (ردیف‌به‌ردیف از بالا-چپ) */
    applyInput: function (state, ev) {
      var index = ev[1];
      if (state.over || typeof index !== "number" || index < 0 || index >= HOLES || index !== Math.floor(index)) return;
      var hole = state.holes[index];
      state.lastHole = index;
      if (hole.type === 0) {
        state.events.push("empty");
        return;
      }
      if (hole.type === 2) {
        state.score = Math.max(0, state.score - 15);
        state.events.push("bomb");
      } else {
        state.score += hole.type === 3 ? 30 : 10;
        state.hits++;
        state.level = state.hits;
        state.events.push(hole.type === 3 ? "gold" : "hit");
      }
      hole.type = 0;
    },

    step: function (state) {
      var tick = state.tick, i;
      for (i = 0; i < HOLES; i++) {
        if (state.holes[i].type !== 0 && tick >= state.holes[i].until) state.holes[i].type = 0;
      }
      if (tick >= state.nextSpawn) {
        var progress = idiv(tick * 100, LIMIT_TICKS);
        var free = [];
        for (i = 0; i < HOLES; i++) if (state.holes[i].type === 0) free.push(i);
        if (free.length) {
          var index = free[state.rng.int(free.length)];
          var r = state.rng.int(100);
          var type = r < 16 + idiv(progress, 6) ? 2 : r >= 95 ? 3 : 1;
          var hole = state.holes[index];
          hole.type = type;
          hole.born = tick;
          hole.until = tick + 55 - idiv(progress * 28, 100);
        }
        state.nextSpawn = tick + 42 - idiv(progress * 26, 100);
      }
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
