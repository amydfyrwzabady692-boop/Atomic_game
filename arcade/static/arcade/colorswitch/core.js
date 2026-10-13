/* «تعویض رنگ» — منطق قطعی. معادل پایتونی: arcade/sim/colorswitch.py
   محور y رو به بالاست. زاویه‌ها: ۱۰۰۰ واحد = یک درجه (قرارداد صفحه: ۹۰° پایین، ۲۷۰° بالا).
   نوع مانع: ۰ حلقه‌ی چهاررنگ، ۱ دو حلقه‌ی تودرتو با چرخش مخالف، ۲ نوار رنگی متحرک. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(require("../common/rng.js"));
  else root.Arcade.registerCore("colorswitch", factory(root.ArcadeRng));
})(typeof self !== "undefined" ? self : this, function (R) {
  "use strict";
  var Rng = R.Rng, idiv = R.idiv, mod = R.mod;

  var TICK_MS = 16;
  var CIRCLE = 360000;
  var GRAVITY = 5, JUMP = 80, MAX_FALL = -140;
  var BALL_R = 110;
  var SPACING = 4200, FIRST_Y = 2600;
  var RING_R = 820, OUTER_R = 1300, HALF_T = 75;
  var BAND = HALF_T + BALL_R; // نصف پهنای مؤثر برخورد
  var SEG_W = 900;
  var FALL_LIMIT = 2800;

  function specOf(state, k) {
    var spec = state.specs[k];
    if (spec) return spec;
    var rng = new Rng((state.seed + (k + 1) * 977) >>> 0);
    var stage = Math.min(idiv(k, 5), 8);
    var t = rng.int(100);
    spec = {
      type: k < 2 ? 0 : t < 50 ? 0 : t < 80 || stage < 1 ? 2 : 1,
      dir: rng.int(2) === 1 ? 1 : -1,
      speed: 900 + stage * 130 + rng.int(300),
      phase: rng.int(360) * 1000,
      barSpeed: 18 + stage * 2 + rng.int(8),
      next: rng.int(3),
      y: FIRST_Y + k * SPACING,
    };
    state.specs[k] = spec;
    return spec;
  }

  function ringRot(spec, tick) { return mod(spec.phase + spec.dir * spec.speed * tick, CIRCLE); }
  function outerRot(spec, tick) { return mod(spec.phase + 45000 - spec.dir * spec.speed * tick, CIRCLE); }
  function barOffset(spec, tick) { return mod(idiv(spec.phase, 100) + spec.dir * spec.barSpeed * tick, 4 * SEG_W); }
  function arcColor(rot, theta) { return idiv(mod(theta - rot, CIRCLE), 90000); }
  function barColor(offset) { return idiv(mod(2 * SEG_W - offset, 4 * SEG_W), SEG_W); }

  /* آیا توپ در ارتفاع y و تیک tick با مانع k برخورد مرگبار دارد؟ */
  function hits(state, k, y, tick) {
    var spec = specOf(state, k);
    var d = y - spec.y;
    var a = Math.abs(d);
    if (spec.type === 2) return a < BAND && barColor(barOffset(spec, tick)) !== state.color;
    var theta = d < 0 ? 90000 : 270000;
    if (Math.abs(a - RING_R) < BAND && arcColor(ringRot(spec, tick), theta) !== state.color) return true;
    if (spec.type === 1 && Math.abs(a - OUTER_R) < BAND && arcColor(outerRot(spec, tick), theta) !== state.color) return true;
    return false;
  }
  function topOf(spec) {
    return spec.y + (spec.type === 2 ? 0 : spec.type === 1 ? OUTER_R : RING_R) + BAND;
  }

  var core = {
    key: "colorswitch",
    TICK_MS: TICK_MS,
    CIRCLE: CIRCLE, SPACING: SPACING, RING_R: RING_R, OUTER_R: OUTER_R, HALF_T: HALF_T, BALL_R: BALL_R, SEG_W: SEG_W,
    specOf: specOf, ringRot: ringRot, outerRot: outerRot, barOffset: barOffset,

    newState: function (seed, config) {
      var s = seed >>> 0;
      return {
        seed: s, tick: 0, over: false, cause: "", score: 0, level: 0,
        y: 0, vy: 0, maxY: 0, started: false, color: new Rng(s).int(4), passed: 0, switched: 0, specs: [], events: [],
      };
    },

    /* ورودی: [t_ms] — یک پرش */
    applyInput: function (state, ev) {
      if (state.over) return;
      state.started = true;
      state.vy = JUMP;
      state.events.push("jump");
    },

    step: function (state) {
      if (!state.started) { state.tick++; return; }
      state.vy = Math.max(state.vy - GRAVITY, MAX_FALL);
      state.y += state.vy;
      if (state.y > state.maxY) state.maxY = state.y;
      if (state.y <= 0 && state.maxY < 700) {
        state.y = 0; // هنوز روی سکوی شروع است
        state.vy = 0;
      } else if (state.y < state.maxY - FALL_LIMIT) {
        state.over = true;
        state.cause = "fall";
        state.events.push("fail");
      }
      if (!state.over) {
        var nearest = idiv(state.y - FIRST_Y + idiv(SPACING, 2), SPACING);
        for (var k = Math.max(0, nearest - 1); k <= nearest + 1; k++) {
          if (hits(state, k, state.y, state.tick)) {
            state.over = true;
            state.cause = "color";
            state.events.push("fail");
            break;
          }
        }
      }
      if (!state.over) {
        var spec = specOf(state, state.passed);
        if (state.y > topOf(spec)) {
          state.passed++;
          state.score++;
          state.level = idiv(state.passed, 5);
          state.events.push("pass");
        }
        var sw = specOf(state, state.switched);
        if (state.y >= sw.y + idiv(SPACING, 2)) {
          state.color = (state.color + 1 + sw.next) % 4;
          state.switched++;
          state.events.push("switch");
        }
      }
      state.tick++;
    },
  };
  return core;
});
