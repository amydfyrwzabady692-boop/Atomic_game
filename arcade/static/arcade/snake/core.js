/* «مار کلاسیک» — منطق قطعی. معادل پایتونی: arcade/sim/snake.py
   جهت‌ها: ۰ بالا، ۱ راست، ۲ پایین، ۳ چپ. محل غذاها از seed می‌آید. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(require("../common/rng.js"));
  else root.Arcade.registerCore("snake", factory(root.ArcadeRng));
})(typeof self !== "undefined" ? self : this, function (R) {
  "use strict";
  var Rng = R.Rng, idiv = R.idiv;

  var TICK_MS = 16;
  var COLS = 15, ROWS = 20;
  var DX = [0, 1, 0, -1], DY = [-1, 0, 1, 0];

  function placeFood(state) {
    var free = COLS * ROWS - state.body.length;
    if (free <= 0) return false;
    var target = state.rng.int(free);
    for (var cell = 0; cell < COLS * ROWS; cell++) {
      if (state.occupied[cell]) continue;
      if (target === 0) { state.food = cell; return true; }
      target--;
    }
    return false;
  }
  function stepEvery(foods) { return Math.max(3, 7 - idiv(foods, 3)); }

  var core = {
    key: "snake",
    TICK_MS: TICK_MS,
    COLS: COLS, ROWS: ROWS,
    stepEvery: stepEvery,

    newState: function (seed, config) {
      var head = idiv(ROWS, 2) * COLS + idiv(COLS, 2);
      var state = {
        seed: seed >>> 0, rng: new Rng(seed), tick: 0, over: false, cause: "", score: 0, level: 0,
        body: [head - 2, head - 1, head], // آخرین عنصر سر مار است
        occupied: [], dir: 1, queue: [], counter: 0, foods: 0, food: -1, events: [],
      };
      for (var i = 0; i < COLS * ROWS; i++) state.occupied.push(false);
      for (i = 0; i < state.body.length; i++) state.occupied[state.body[i]] = true;
      placeFood(state);
      return state;
    },

    /* ورودی: [t_ms, dir] — حداکثر دو تغییر جهت در صف می‌ماند؛ برگشت ۱۸۰ درجه مجاز نیست */
    applyInput: function (state, ev) {
      var dir = ev[1];
      if (state.over || !(dir === 0 || dir === 1 || dir === 2 || dir === 3)) return;
      if (state.queue.length >= 2) return;
      var last = state.queue.length ? state.queue[state.queue.length - 1] : state.dir;
      if (dir === last || dir === (last + 2) % 4) return;
      state.queue.push(dir);
    },

    step: function (state) {
      state.counter++;
      if (state.counter >= stepEvery(state.foods)) {
        state.counter = 0;
        if (state.queue.length) state.dir = state.queue.shift();
        var head = state.body[state.body.length - 1];
        var x = head % COLS + DX[state.dir], y = idiv(head, COLS) + DY[state.dir];
        if (x < 0 || x >= COLS || y < 0 || y >= ROWS) {
          state.over = true;
          state.cause = "wall";
          state.events.push("fail");
        } else {
          var next = y * COLS + x;
          var eating = next === state.food;
          if (!eating) state.occupied[state.body.shift()] = false; // دم جلو می‌رود
          if (state.occupied[next]) {
            state.over = true;
            state.cause = "self";
            state.events.push("fail");
          } else {
            state.body.push(next);
            state.occupied[next] = true;
            if (eating) {
              state.foods++;
              state.score += 10;
              state.level = state.foods;
              state.events.push("eat");
              if (!placeFood(state)) {
                state.over = true;
                state.cause = "win";
              }
            }
          }
        }
      }
      state.tick++;
    },
  };
  return core;
});
