/* «کاشی‌های سیاه» — منطق قطعی. معادل پایتونی: arcade/sim/tiles.py
   دو حالت: endless (بی‌پایان، با اسکرول خودکار) و fifty (۵۰ کاشی با کمترین زمان). */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(require("../common/rng.js"));
  else root.Arcade.registerCore("tiles", factory(root.ArcadeRng));
})(typeof self !== "undefined" ? self : this, function (R) {
  "use strict";
  var Rng = R.Rng, idiv = R.idiv;

  var TICK_MS = 16;
  var ROW_H = 1600;
  var VISIBLE_ROWS = 4;
  var START = 2 * ROW_H;
  var TARGET = 50;
  var FIFTY_LIMIT_MS = 60000;

  function ensureRows(state) {
    while (state.cols.length < state.hits + 8) state.cols.push(state.rng.int(4));
  }
  function speedFor(hits) { return Math.min(150, 52 + idiv(hits * 3, 5)); }
  /* فاصله‌ی لبه‌ی پایین ردیف k از پایین صفحه */
  function rowBottom(state, k) { return START + k * ROW_H - state.offset; }

  var core = {
    key: "tiles",
    TICK_MS: TICK_MS,
    ROW_H: ROW_H,
    VISIBLE_ROWS: VISIBLE_ROWS,
    TARGET: TARGET,
    rowBottom: rowBottom,
    speedFor: speedFor,

    newState: function (seed, config) {
      var state = {
        seed: seed >>> 0, rng: new Rng(seed), tick: 0, over: false, cause: "", score: 0, level: 0,
        mode: config.variant === "fifty" ? "fifty" : "endless",
        hits: 0, offset: 0, started: false, startTick: 0, cols: [], wrongCol: -1, events: [],
      };
      ensureRows(state);
      return state;
    },

    /* ورودی: [t_ms, col] — ستون ۰ تا ۳ از چپ */
    applyInput: function (state, ev) {
      var col = ev[1];
      if (state.over || !(col === 0 || col === 1 || col === 2 || col === 3)) return;
      if (state.mode === "endless" && rowBottom(state, state.hits) >= VISIBLE_ROWS * ROW_H) return;
      if (col !== state.cols[state.hits]) {
        state.over = true;
        state.cause = "wrong";
        state.wrongCol = col;
        state.events.push("fail");
        return;
      }
      if (!state.started) {
        state.started = true;
        state.startTick = state.tick;
      }
      state.hits++;
      ensureRows(state);
      state.events.push("hit");
      if (state.mode === "fifty") {
        state.offset = state.hits * ROW_H;
        state.score = state.hits * 10;
        if (state.hits >= TARGET) {
          var elapsed = (state.tick - state.startTick) * TICK_MS;
          state.score = 1000 + Math.max(0, idiv(30000 - elapsed, 10));
          state.over = true;
          state.cause = "done";
          state.events.push("win");
        }
      } else {
        state.score++;
        state.level = idiv(state.hits, 10);
      }
    },

    step: function (state) {
      if (state.started) {
        if (state.mode === "endless") {
          state.offset += speedFor(state.hits);
          if (rowBottom(state, state.hits) + ROW_H <= 0) {
            state.over = true;
            state.cause = "miss";
            state.events.push("fail");
          }
        } else if ((state.tick - state.startTick) * TICK_MS >= FIFTY_LIMIT_MS) {
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
