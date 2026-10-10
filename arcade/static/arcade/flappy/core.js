/* «پرنده‌ی پرشی» — منطق قطعی. معادل پایتونی: arcade/sim/flappy.py
   زمین ۳۶۰۰×۶۴۰۰ واحد (۱۰ واحد = یک پیکسل منطقی). */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(require("../common/rng.js"));
  else root.Arcade.registerCore("flappy", factory(root.ArcadeRng));
})(typeof self !== "undefined" ? self : this, function (R) {
  "use strict";
  var Rng = R.Rng, idiv = R.idiv;

  var TICK_MS = 16;
  var FIELD_W = 3600, FIELD_H = 6400;
  var BIRD_X = 1000, RADIUS = 130, PIPE_W = 560;
  var GRAVITY = 7, JUMP = -105, MAX_VY = 200;

  function spacingFor(score) { return Math.max(1700, 2300 - score * 12); }
  function gapFor(score) { return Math.max(1350, 1900 - score * 15); }
  function speedFor(score) { return 26 + idiv(Math.min(score, 60), 5); }

  var core = {
    key: "flappy",
    TICK_MS: TICK_MS,
    FIELD_W: FIELD_W, FIELD_H: FIELD_H, BIRD_X: BIRD_X, RADIUS: RADIUS, PIPE_W: PIPE_W,
    speedFor: speedFor,

    newState: function (seed, config) {
      return {
        seed: seed >>> 0, rng: new Rng(seed), tick: 0, over: false, cause: "", score: 0, level: 0,
        started: false, y: idiv(FIELD_H, 2) - 400, vy: 0, pipes: [], dist: spacingFor(0) - 1400, events: [],
      };
    },

    /* ورودی: [t_ms] — یک پرش */
    applyInput: function (state, ev) {
      if (state.over) return;
      state.started = true;
      state.vy = JUMP;
      state.events.push("flap");
    },

    step: function (state) {
      if (!state.started) { state.tick++; return; }
      var speed = speedFor(state.score);
      state.vy = Math.min(state.vy + GRAVITY, MAX_VY);
      state.y += state.vy;
      if (state.y < RADIUS) { state.y = RADIUS; state.vy = 0; }

      state.dist += speed;
      var spacing = spacingFor(state.score);
      if (state.dist >= spacing) {
        state.dist -= spacing;
        var gapH = gapFor(state.score);
        state.pipes.push({ x: FIELD_W, gapY: state.rng.range(700, FIELD_H - 1100 - gapH), gapH: gapH, passed: false });
      }
      var i, p;
      for (i = 0; i < state.pipes.length; i++) state.pipes[i].x -= speed;
      if (state.pipes.length && state.pipes[0].x + PIPE_W < -200) state.pipes.shift();

      if (state.y + RADIUS >= FIELD_H) {
        state.over = true;
        state.cause = "ground";
        state.events.push("fail");
      }
      for (i = 0; i < state.pipes.length && !state.over; i++) {
        p = state.pipes[i];
        if (BIRD_X + RADIUS > p.x && BIRD_X - RADIUS < p.x + PIPE_W) {
          if (state.y - RADIUS < p.gapY || state.y + RADIUS > p.gapY + p.gapH) {
            state.over = true;
            state.cause = "pipe";
            state.events.push("fail");
          }
        } else if (!p.passed && p.x + PIPE_W <= BIRD_X - RADIUS) {
          p.passed = true;
          state.score++;
          state.level = state.score;
          state.events.push("score");
        }
      }
      state.tick++;
    },
  };
  return core;
});
