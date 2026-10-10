/* «۲۰۴۸ سرعتی» — منطق قطعی. معادل پایتونی: arcade/sim/g2048.py
   کاشی‌های تصادفی از seed می‌آیند؛ همه‌ی بازیکن‌ها با حرکت‌های یکسان همان کاشی‌ها را می‌گیرند. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(require("../common/rng.js"));
  else root.Arcade.registerCore("g2048", factory(root.ArcadeRng));
})(typeof self !== "undefined" ? self : this, function (R) {
  "use strict";
  var Rng = R.Rng;

  var TICK_MS = 16;
  var LIMIT_TICKS = 7500; // ۲ دقیقه

  /* خانه‌ی k‌اُم از خط line در جهت حرکت dir (۰ بالا، ۱ راست، ۲ پایین، ۳ چپ) */
  function cellIndex(dir, line, k) {
    if (dir === 3) return line * 4 + k;
    if (dir === 1) return line * 4 + (3 - k);
    if (dir === 0) return k * 4 + line;
    return (3 - k) * 4 + line;
  }

  function spawn(state) {
    var empty = [];
    for (var i = 0; i < 16; i++) if (state.grid[i] === 0) empty.push(i);
    if (!empty.length) return;
    var cell = empty[state.rng.int(empty.length)];
    state.grid[cell] = state.rng.int(10) === 0 ? 4 : 2;
    state.spawned = cell;
  }

  function stuck(grid) {
    for (var i = 0; i < 16; i++) {
      if (grid[i] === 0) return false;
      if (i % 4 < 3 && grid[i] === grid[i + 1]) return false;
      if (i < 12 && grid[i] === grid[i + 4]) return false;
    }
    return true;
  }

  var core = {
    key: "g2048",
    TICK_MS: TICK_MS,
    LIMIT_TICKS: LIMIT_TICKS,
    MAX_DURATION_MS: 121000,
    cellIndex: cellIndex,

    newState: function (seed, config) {
      var state = {
        seed: seed >>> 0, rng: new Rng(seed), tick: 0, over: false, cause: "", score: 0, level: 1,
        grid: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], spawned: -1, merged: [], events: [],
      };
      spawn(state);
      spawn(state);
      return state;
    },

    /* ورودی: [t_ms, dir] */
    applyInput: function (state, ev) {
      var dir = ev[1];
      if (state.over || !(dir === 0 || dir === 1 || dir === 2 || dir === 3)) return;
      var grid = state.grid, moved = false, gained = 0, merged = [];
      for (var line = 0; line < 4; line++) {
        var values = [], k;
        for (k = 0; k < 4; k++) {
          var v = grid[cellIndex(dir, line, k)];
          if (v) values.push(v);
        }
        var out = [], mergedAt = [];
        for (k = 0; k < values.length; k++) {
          if (k + 1 < values.length && values[k] === values[k + 1]) {
            out.push(values[k] * 2);
            mergedAt.push(out.length - 1);
            gained += values[k] * 2;
            k++;
          } else {
            out.push(values[k]);
          }
        }
        for (k = 0; k < 4; k++) {
          var idx = cellIndex(dir, line, k);
          var nv = k < out.length ? out[k] : 0;
          if (grid[idx] !== nv) moved = true;
          grid[idx] = nv;
        }
        for (k = 0; k < mergedAt.length; k++) merged.push(cellIndex(dir, line, mergedAt[k]));
      }
      if (!moved) return;
      state.score += gained;
      state.merged = merged;
      spawn(state);
      var max = 0;
      for (var i = 0; i < 16; i++) if (grid[i] > max) max = grid[i];
      var level = 0;
      while (max > 1) { max = max / 2; level++; }
      state.level = level;
      state.events.push(gained ? "merge" : "move");
      if (stuck(grid)) {
        state.over = true;
        state.cause = "stuck";
        state.events.push("fail");
      }
    },

    step: function (state) {
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
