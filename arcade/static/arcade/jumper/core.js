/* «پرش ابرها» — منطق قطعی. معادل پایتونی: arcade/sim/jumper.py
   y رو به بالاست. زمین افقی ۳۶۰۰ واحد و حلقوی است (از یک طرف بیرون بروی از طرف دیگر می‌آیی).
   نوع سکو: ۰ عادی، ۱ متحرک، ۲ شکننده (بعد از یک پرش می‌شکند). کنترل فقط با تپ چپ/راست. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(require("../common/rng.js"));
  else root.Arcade.registerCore("jumper", factory(root.ArcadeRng));
})(typeof self !== "undefined" ? self : this, function (R) {
  "use strict";
  var Rng = R.Rng, idiv = R.idiv, mod = R.mod;

  var TICK_MS = 16;
  var WIDTH = 3600;
  var GRAVITY = 7, JUMP = 150, SPRING = 230, MAX_FALL = -220;
  var H_SPEED = 30;
  var MAX_SHIFT = 1100; // بیشترین فاصله‌ی افقی سکوی بعدی (تا همیشه با یک پرش قابل‌دسترس باشد)
  var PLAT_W = 620, HALF_BODY = 110;
  var VIEW_BELOW = 2600; // فاصله‌ی دوربین تا بازیکن
  var FALL_MARGIN = 600;
  var GENERATE_AHEAD = 9000;

  function generate(state) {
    var k = state.made++;
    var rng = state.rng;
    var gap = 500 + Math.min(k, 120) * 4 + rng.int(180);
    var x = mod(state.lastX + rng.int(2 * MAX_SHIFT + 1) - MAX_SHIFT, WIDTH);
    state.lastX = x;
    var r = rng.int(100);
    var lvl = Math.min(idiv(k, 25), 6);
    var type = r < 12 + lvl * 4 ? 1 : r < 22 + lvl * 8 ? 2 : 0;
    var s = rng.int(100);
    var phase = rng.int(240);
    state.topY += gap;
    state.plats.push({ y: state.topY, x: x, w: PLAT_W, type: type, spring: type === 0 && s < 8, phase: phase, alive: true });
  }

  function platformX(p, tick) {
    if (p.type !== 1) return p.x;
    var tri = mod(tick + p.phase, 240);
    var off = tri < 120 ? tri : 240 - tri;
    return mod(p.x + (off - 60) * 5, WIDTH);
  }

  var core = {
    key: "jumper",
    TICK_MS: TICK_MS,
    WIDTH: WIDTH, PLAT_W: PLAT_W, VIEW_BELOW: VIEW_BELOW, H_SPEED: H_SPEED,
    platformX: platformX,

    newState: function (seed, config) {
      var state = {
        seed: seed >>> 0, rng: new Rng(seed), tick: 0, over: false, cause: "", score: 0, level: 0,
        x: idiv(WIDTH, 2), y: 0, vy: 0, dir: 1, started: false, maxY: 0, camY: -VIEW_BELOW,
        made: 0, topY: 0, lastX: idiv(WIDTH - PLAT_W, 2), landed: null, events: [],
        plats: [{ y: 0, x: 0, w: WIDTH, type: 0, spring: false, phase: 0, alive: true }], // زمین
      };
      while (state.topY < state.camY + GENERATE_AHEAD) generate(state);
      return state;
    },

    /* ورودی: [t_ms, dir] — ۰ حرکت به چپ، ۱ حرکت به راست */
    applyInput: function (state, ev) {
      var dir = ev[1];
      if (state.over || (dir !== 0 && dir !== 1)) return;
      state.dir = dir === 0 ? -1 : 1;
      state.started = true;
    },

    step: function (state) {
      if (!state.started) { state.tick++; return; }
      state.x = mod(state.x + state.dir * H_SPEED, WIDTH);
      state.vy = Math.max(state.vy - GRAVITY, MAX_FALL);
      var prevY = state.y;
      state.y += state.vy;

      if (state.vy < 0) {
        var best = null;
        for (var i = 0; i < state.plats.length; i++) {
          var p = state.plats[i];
          if (!p.alive || p.y > prevY || p.y <= state.y) continue;
          var dx = mod(state.x - platformX(p, state.tick), WIDTH);
          if (dx <= p.w + HALF_BODY || dx >= WIDTH - HALF_BODY) {
            if (best === null || p.y > best.y) best = p;
          }
        }
        if (best !== null) {
          state.y = best.y;
          state.vy = best.spring ? SPRING : JUMP;
          state.landed = best;
          if (best.type === 2) {
            best.alive = false;
            state.events.push("break");
          } else {
            state.events.push(best.spring ? "spring" : "bounce");
          }
        }
      }

      if (state.y > state.maxY) {
        state.maxY = state.y;
        state.score = idiv(state.maxY, 100);
        state.level = idiv(state.score, 200);
      }
      if (state.y - VIEW_BELOW > state.camY) state.camY = state.y - VIEW_BELOW;
      if (state.y < state.camY - FALL_MARGIN) {
        state.over = true;
        state.cause = "fall";
        state.events.push("fail");
      }
      while (state.topY < state.camY + GENERATE_AHEAD) generate(state);
      while (state.plats.length && state.plats[0].y < state.camY - 800) state.plats.shift();
      state.tick++;
    },
  };
  return core;
});
