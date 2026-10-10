/* «آجرشکن» — منطق قطعی با اعداد صحیح. معادل پایتونی: arcade/sim/breakout.py
   زمین ۳۶۰۰×۶۴۰۰ واحد، y رو به پایین. ورودی: موقعیت مرکز راکت (حداکثر ۳۰ بار در ثانیه).
   آیتم‌ها: ۰ راکت پهن، ۱ جان اضافه، ۲ امتیاز. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(require("../common/rng.js"));
  else root.Arcade.registerCore("breakout", factory(root.ArcadeRng));
})(typeof self !== "undefined" ? self : this, function (R) {
  "use strict";
  var Rng = R.Rng, idiv = R.idiv;

  var TICK_MS = 16;
  var WIDTH = 3600, HEIGHT = 6400;
  var COLS = 8, ROWS = 8;
  var BRICK_W = 420, BRICK_H = 200, STEP_X = 444, STEP_Y = 224, LEFT = 36, TOP = 900;
  var PADDLE_Y = 5700, PADDLE_W = 760, PADDLE_WIDE = 1100;
  var BALL_R = 70;
  var MAX_VX = 44;
  var ATTACH_TICKS = 45, PAUSE_TICKS = 40, WIDE_TICKS = 600;
  var ITEM_SPEED = 22;
  var START_LIVES = 3, MAX_LIVES = 5;

  function paddleWidth(state) { return state.wide > 0 ? PADDLE_WIDE : PADDLE_W; }
  function ballSpeed(state) { return 58 + Math.min(state.level, 8) * 3; }
  function clampPaddle(state) {
    var max = WIDTH - paddleWidth(state);
    if (state.px < 0) state.px = 0;
    if (state.px > max) state.px = max;
  }

  function loadLevel(state) {
    var layouts = state.levels;
    var layout = layouts[state.level % layouts.length];
    var extra = idiv(state.level, layouts.length);
    state.bricks = [];
    state.remaining = 0;
    for (var r = 0; r < ROWS; r++) {
      for (var c = 0; c < COLS; c++) {
        var hp = r < layout.length ? layout[r].charCodeAt(c) - 48 : 0;
        if (hp > 0) {
          hp = Math.min(3, hp + extra);
          state.remaining++;
        }
        state.bricks.push(hp);
      }
    }
    state.items = [];
    state.wide = 0;
    state.attach = ATTACH_TICKS;
    state.vx = 0;
    state.vy = 0;
    clampPaddle(state);
  }

  /* اولین آجری که مرکز توپ (با احتساب شعاع) داخلش است؛ ۱- یعنی هیچ */
  function brickAt(state, x, y) {
    var c0 = Math.max(0, idiv(x - BALL_R - LEFT - BRICK_W, STEP_X));
    var c1 = Math.min(COLS - 1, idiv(x + BALL_R - LEFT, STEP_X));
    var r0 = Math.max(0, idiv(y - BALL_R - TOP - BRICK_H, STEP_Y));
    var r1 = Math.min(ROWS - 1, idiv(y + BALL_R - TOP, STEP_Y));
    for (var r = r0; r <= r1; r++) {
      for (var c = c0; c <= c1; c++) {
        if (state.bricks[r * COLS + c] <= 0) continue;
        var bx = LEFT + c * STEP_X, by = TOP + r * STEP_Y;
        if (x >= bx - BALL_R && x <= bx + BRICK_W + BALL_R && y >= by - BALL_R && y <= by + BRICK_H + BALL_R) {
          return r * COLS + c;
        }
      }
    }
    return -1;
  }

  function damage(state, index) {
    state.bricks[index]--;
    state.score += 5;
    state.lastHit = index;
    if (state.bricks[index] > 0) {
      state.events.push("crack");
      return;
    }
    state.remaining--;
    state.score += 10;
    state.events.push("break");
    if (state.rng.int(100) < 12) {
      state.items.push({
        x: LEFT + (index % COLS) * STEP_X + idiv(BRICK_W, 2),
        y: TOP + idiv(index, COLS) * STEP_Y + BRICK_H,
        type: state.rng.int(3),
      });
    }
    if (state.remaining === 0) {
      state.level++;
      state.score += 100;
      state.pause = PAUSE_TICKS;
      state.events.push("clear");
    }
  }

  var core = {
    key: "breakout",
    TICK_MS: TICK_MS,
    MAX_INPUTS: 40000,
    assets: ["levels.json"],
    WIDTH: WIDTH, HEIGHT: HEIGHT, COLS: COLS, ROWS: ROWS,
    BRICK_W: BRICK_W, BRICK_H: BRICK_H, STEP_X: STEP_X, STEP_Y: STEP_Y, LEFT: LEFT, TOP: TOP,
    PADDLE_Y: PADDLE_Y, BALL_R: BALL_R,
    paddleWidth: paddleWidth,

    newState: function (seed, config) {
      var state = {
        seed: seed >>> 0, rng: new Rng(seed), tick: 0, over: false, cause: "", score: 0, level: 0,
        levels: (config.assets && config.assets["levels.json"]) || [["11111111"]],
        lives: START_LIVES, px: idiv(WIDTH - PADDLE_W, 2), bx: idiv(WIDTH, 2), by: PADDLE_Y - BALL_R,
        vx: 0, vy: 0, pause: 0, wide: 0, attach: 0, bricks: [], remaining: 0, items: [], lastHit: -1, events: [],
      };
      loadLevel(state);
      return state;
    },

    /* ورودی: [t_ms, x] — موقعیت مرکز راکت */
    applyInput: function (state, ev) {
      var x = ev[1];
      if (state.over || typeof x !== "number") return;
      state.px = x - idiv(paddleWidth(state), 2);
      clampPaddle(state);
    },

    step: function (state) {
      if (state.pause > 0) {
        state.pause--;
        if (state.pause === 0) loadLevel(state);
        state.tick++;
        return;
      }
      if (state.wide > 0) {
        state.wide--;
        if (state.wide === 0) clampPaddle(state);
      }
      var w = paddleWidth(state);
      if (state.attach > 0) {
        state.attach--;
        state.bx = state.px + idiv(w, 2);
        state.by = PADDLE_Y - BALL_R;
        if (state.attach === 0) {
          state.vx = (state.rng.int(5) - 2) * 8;
          state.vy = -ballSpeed(state);
          state.events.push("launch");
        }
      } else {
        var hit;
        // حرکت افقی
        state.bx += state.vx;
        if (state.bx < BALL_R) { state.bx = BALL_R; state.vx = -state.vx; state.events.push("wall"); }
        else if (state.bx > WIDTH - BALL_R) { state.bx = WIDTH - BALL_R; state.vx = -state.vx; state.events.push("wall"); }
        hit = brickAt(state, state.bx, state.by);
        if (hit >= 0) {
          state.bx -= state.vx;
          state.vx = -state.vx;
          damage(state, hit);
        }
        // حرکت عمودی
        if (state.pause === 0) {
          state.by += state.vy;
          if (state.by < BALL_R) { state.by = BALL_R; state.vy = -state.vy; state.events.push("wall"); }
          hit = brickAt(state, state.bx, state.by);
          if (hit >= 0) {
            state.by -= state.vy;
            state.vy = -state.vy;
            damage(state, hit);
          }
        }
        // راکت
        if (state.pause === 0 && state.vy > 0 && state.by + BALL_R >= PADDLE_Y && state.by + BALL_R - state.vy <= PADDLE_Y
            && state.bx >= state.px - BALL_R && state.bx <= state.px + w + BALL_R) {
          var half = idiv(w, 2);
          var rel = idiv((state.bx - (state.px + half)) * 100, half + BALL_R);
          if (rel > 100) rel = 100;
          if (rel < -100) rel = -100;
          state.by = PADDLE_Y - BALL_R;
          state.vx = idiv(rel * MAX_VX, 100);
          if (state.vx === 0) state.vx = state.tick % 2 === 0 ? 6 : -6; // هیچ‌وقت کاملاً عمودی نمی‌شود
          state.vy = -ballSpeed(state);
          state.events.push("paddle");
        } else if (state.by - BALL_R > HEIGHT) {
          state.lives--;
          state.events.push("lose");
          if (state.lives <= 0) {
            state.over = true;
            state.cause = "out";
            state.events.push("fail");
          } else {
            state.attach = ATTACH_TICKS;
          }
        }
      }
      // آیتم‌های در حال سقوط
      for (var i = state.items.length - 1; i >= 0; i--) {
        var item = state.items[i];
        item.y += ITEM_SPEED;
        if (item.y >= PADDLE_Y && item.y <= PADDLE_Y + 150 && item.x >= state.px && item.x <= state.px + w) {
          if (item.type === 0) { state.wide = WIDE_TICKS; clampPaddle(state); }
          else if (item.type === 1) { if (state.lives < MAX_LIVES) state.lives++; }
          else state.score += 50;
          state.lastItem = item.type;
          state.events.push("item");
          state.items.splice(i, 1);
        } else if (item.y > HEIGHT) {
          state.items.splice(i, 1);
        }
      }
      state.tick++;
    },
  };
  return core;
});
