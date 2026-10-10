/* «دونده‌ی سه‌خطی» — منطق قطعی. معادل پایتونی: arcade/sim/runner.py
   هر ردیف سه خانه دارد: ۰ خالی، ۱ مانع کوتاه (می‌شود پرید)، ۲ مانع بلند، ۳ سکه.
   خط سالم هر ردیف حداکثر یک خط با ردیف قبلی فاصله دارد؛ پس همیشه مسیر سالم هست. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(require("../common/rng.js"));
  else root.Arcade.registerCore("runner", factory(root.ArcadeRng));
})(typeof self !== "undefined" ? self : this, function (R) {
  "use strict";
  var Rng = R.Rng, idiv = R.idiv;

  var TICK_MS = 16;
  var ROW_GAP = 1400;
  var FIRST = 4200;
  var JUMP_TICKS = 30;
  var AHEAD = 8;

  function generate(state) {
    var k = state.rows.length;
    if (k < 2) { state.rows.push([0, 0, 0]); return; }
    var rng = state.rng;
    var lvl = Math.min(idiv(k, 20), 8);
    var safe = state.prevSafe + rng.int(3) - 1;
    if (safe < 0) safe = 0;
    if (safe > 2) safe = 2;
    var row = [0, 0, 0];
    for (var lane = 0; lane < 3; lane++) {
      if (lane === safe) {
        row[lane] = rng.int(100) < 35 ? 3 : 0;
      } else {
        var r = rng.int(100);
        row[lane] = r < 30 - lvl * 2 ? 0 : r < 60 ? 1 : r < 92 ? 2 : 3;
      }
    }
    state.prevSafe = safe;
    state.rows.push(row);
  }
  function speedFor(passed) { return 36 + idiv(Math.min(passed, 136), 4); }
  function rowZ(state, k) { return FIRST + k * ROW_GAP - state.dist; }

  var core = {
    key: "runner",
    TICK_MS: TICK_MS,
    ROW_GAP: ROW_GAP,
    JUMP_TICKS: JUMP_TICKS,
    speedFor: speedFor,
    rowZ: rowZ,

    newState: function (seed, config) {
      var state = {
        seed: seed >>> 0, rng: new Rng(seed), tick: 0, over: false, cause: "", score: 0, level: 0,
        lane: 1, air: 0, dist: 0, passed: 0, prevSafe: 1, rows: [], events: [],
      };
      while (state.rows.length < AHEAD) generate(state);
      return state;
    },

    /* ورودی: [t_ms, action] — ۰ چپ، ۱ راست، ۲ پرش */
    applyInput: function (state, ev) {
      var action = ev[1];
      if (state.over) return;
      if (action === 0) { if (state.lane > 0) { state.lane--; state.events.push("move"); } }
      else if (action === 1) { if (state.lane < 2) { state.lane++; state.events.push("move"); } }
      else if (action === 2) { if (state.air === 0) { state.air = JUMP_TICKS; state.events.push("jump"); } }
    },

    step: function (state) {
      state.dist += speedFor(state.passed);
      if (state.air > 0) state.air--;
      while (!state.over && rowZ(state, state.passed) <= 0) {
        var cell = state.rows[state.passed][state.lane];
        if (cell === 2 || (cell === 1 && state.air === 0)) {
          state.over = true;
          state.cause = "crash";
          state.events.push("fail");
          break;
        }
        if (cell === 3) {
          state.score += 5;
          state.rows[state.passed][state.lane] = 0;
          state.events.push("coin");
        }
        state.score++;
        state.passed++;
        while (state.rows.length < state.passed + AHEAD) generate(state);
      }
      state.level = idiv(state.passed, 20);
      state.tick++;
    },
  };
  return core;
});
