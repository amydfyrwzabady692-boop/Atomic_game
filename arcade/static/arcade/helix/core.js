/* «مارپیچ سقوط» — منطق قطعی. معادل پایتونی: arcade/sim/helix.py
   زاویه‌ها: ۱۰۰۰ واحد = یک درجه. y رو به پایین زیاد می‌شود. توپ همیشه در زاویه‌ی ثابت جلو است
   و بازیکن برج را می‌چرخاند. بخش هر طبقه: ۰ شکاف، ۱ سکو، ۲ قرمز. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(require("../common/rng.js"));
  else root.Arcade.registerCore("helix", factory(root.ArcadeRng));
})(typeof self !== "undefined" ? self : this, function (R) {
  "use strict";
  var Rng = R.Rng, idiv = R.idiv, mod = R.mod;

  var TICK_MS = 16;
  var CIRCLE = 360000;
  var BALL_ANGLE = 90000;
  var FLOOR_H = 1800;
  var GRAVITY = 6, BOUNCE = -108, MAX_VY = 150;
  var PAUSE_TICKS = 30;
  var MAX_TURN = 12000; // بیشترین چرخش در یک ورودی
  var FIRE_STREAK = 3;

  function buildLevel(state) {
    var level = Math.min(state.level, 10);
    var count = 10 + level * 2;
    var floors = [];
    for (var k = 1; k <= count; k++) {
      var rng = new Rng((state.seed + state.level * 1009 + k * 31) >>> 0);
      var floor = { gapStart: rng.int(360) * 1000, gapSize: Math.max(42000, 78000 - level * 4000), reds: [] };
      if (k > 1) {
        var reds = Math.min(3, 1 + idiv(level + rng.int(2), 2));
        for (var j = 0; j < reds; j++) {
          var start = rng.int(360) * 1000;
          floor.reds.push([start, 30000 + rng.int(21) * 1000]);
        }
      }
      floors.push(floor);
    }
    state.floors = floors;
    state.count = count;
    state.y = 0;
    state.vy = 0;
    state.floorIdx = 1;
    state.streak = 0;
    // شروع امن: توپ روبه‌روی شکاف طبقه‌ی اول (روی سکو) قرار می‌گیرد
    state.rot = mod(BALL_ANGLE - (floors[0].gapStart + 180000), CIRCLE);
  }

  function sector(floor, local) {
    if (mod(local - floor.gapStart, CIRCLE) < floor.gapSize) return 0;
    for (var i = 0; i < floor.reds.length; i++) {
      if (mod(local - floor.reds[i][0], CIRCLE) < floor.reds[i][1]) return 2;
    }
    return 1;
  }

  var core = {
    key: "helix",
    TICK_MS: TICK_MS,
    MAX_INPUTS: 40000,
    CIRCLE: CIRCLE, BALL_ANGLE: BALL_ANGLE, FLOOR_H: FLOOR_H, MAX_TURN: MAX_TURN, FIRE_STREAK: FIRE_STREAK,
    sector: sector,

    newState: function (seed, config) {
      var state = {
        seed: seed >>> 0, tick: 0, over: false, cause: "", score: 0, level: 0,
        pause: 0, floors: [], count: 0, y: 0, vy: 0, floorIdx: 1, streak: 0, rot: 0, events: [],
      };
      buildLevel(state);
      return state;
    },

    /* ورودی: [t_ms, drot] — چرخش برج (مثبت = ساعت‌گرد) */
    applyInput: function (state, ev) {
      var turn = ev[1];
      if (state.over || state.pause > 0 || typeof turn !== "number") return;
      if (turn > MAX_TURN) turn = MAX_TURN;
      if (turn < -MAX_TURN) turn = -MAX_TURN;
      state.rot = mod(state.rot + turn, CIRCLE);
    },

    step: function (state) {
      if (state.pause > 0) {
        state.pause--;
        if (state.pause === 0) buildLevel(state);
        state.tick++;
        return;
      }
      state.vy = Math.min(state.vy + GRAVITY, MAX_VY);
      state.y += state.vy;
      var floorY = state.floorIdx * FLOOR_H;
      if (state.vy > 0 && state.y >= floorY) {
        if (state.floorIdx > state.count) {
          // کف برج: مرحله تمام شد
          state.y = floorY;
          state.vy = 0;
          state.score += 20 + state.level * 5;
          state.level++;
          state.pause = PAUSE_TICKS;
          state.events.push("clear");
        } else {
          var kind = sector(state.floors[state.floorIdx - 1], mod(BALL_ANGLE - state.rot, CIRCLE));
          if (kind === 0) {
            state.floorIdx++;
            state.streak++;
            state.score += state.streak;
            state.events.push("pass");
          } else if (state.streak >= FIRE_STREAK) {
            // حالت آتشین: طبقه را می‌شکند، حتی اگر قرمز باشد
            state.floors[state.floorIdx - 1].broken = true;
            state.floorIdx++;
            state.streak = 0;
            state.score += 3;
            state.events.push("smash");
          } else if (kind === 2) {
            state.y = floorY;
            state.over = true;
            state.cause = "red";
            state.events.push("fail");
          } else {
            state.y = floorY;
            state.vy = BOUNCE;
            state.streak = 0;
            state.events.push("bounce");
          }
        }
      }
      state.tick++;
    },
  };
  return core;
});
