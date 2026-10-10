/* «آجرشکن» — رندر و افکت‌ها. موقعیت راکت حداکثر ۳۰ بار در ثانیه به‌عنوان ورودی ثبت می‌شود. */
(function () {
  "use strict";
  Arcade.registerRenderer("breakout", function (env) {
    var core = Arcade.cores.breakout;
    var HP_COLORS = ["", "#38bdf8", "#fbbf24", "#f43f5e"];
    var ITEM_ICONS = ["↔", "♥", "★"];
    var targetX = null, sentX = null;
    var trail = [];

    function layout() {
      var scale = Math.min(env.W / core.WIDTH, env.H / core.HEIGHT);
      return { s: scale, ox: (env.W - core.WIDTH * scale) / 2, oy: (env.H - core.HEIGHT * scale) / 2 };
    }

    return {
      controls: "drag",
      reset: function () {
        targetX = sentX = null;
        trail = [];
      },
      input: function (kind, data) {
        if (kind === "tap" || kind === "drag") {
          var l = layout();
          targetX = Math.round((data.x - l.ox) / l.s);
        }
        return null;
      },
      sample: function (state) {
        if (targetX === null || state.tick % 2 !== 0) return null;
        var x = Math.max(0, Math.min(core.WIDTH, targetX));
        if (sentX !== null && Math.abs(x - sentX) < 8) return null;
        sentX = x;
        return [x];
      },
      hud: function (state) {
        if (!state) return "";
        return "مرحله " + env.fa(state.level + 1) + "   " + "❤️".repeat(Math.max(state.lives, 0));
      },
      event: function (name, state) {
        var l = layout();
        var bx = l.ox + state.bx * l.s, by = l.oy + state.by * l.s;
        if (name === "break" || name === "crack") {
          var index = state.lastHit;
          var x = l.ox + (core.LEFT + (index % core.COLS) * core.STEP_X + core.BRICK_W / 2) * l.s;
          var y = l.oy + (core.TOP + Math.floor(index / core.COLS) * core.STEP_Y + core.BRICK_H / 2) * l.s;
          if (name === "break") {
            env.fx.burst(x, y, env.colors.gold, 10, 3);
            env.haptic("light");
            env.sound("good");
          } else {
            env.sound("tap");
          }
        } else if (name === "paddle") {
          env.haptic("light");
          env.sound("tick");
        } else if (name === "wall") {
          env.sound("tick");
        } else if (name === "item") {
          env.fx.burst(bx, l.oy + core.PADDLE_Y * l.s, env.colors.good, 16, 4);
          env.fx.text(env.W / 2, l.oy + core.PADDLE_Y * l.s - 20, ["راکت پهن!", "+۱ جان", "+۵۰"][state.lastItem], env.colors.good);
          env.haptic("medium");
          env.sound("bonus");
        } else if (name === "clear") {
          env.fx.burst(env.W / 2, env.H / 2, env.colors.good, 40, 7);
          env.fx.flash(env.colors.good, 0.3);
          env.haptic("success");
          env.sound("clear");
        } else if (name === "lose") {
          env.fx.flash(env.colors.danger, 0.4);
          env.fx.shake(10);
          env.haptic("error");
          env.sound("bad");
        }
      },
      draw: function (c, state, alpha) {
        var l = layout(), s = l.s;
        c.fillStyle = "rgba(10,13,34,.35)";
        c.fillRect(l.ox, l.oy, core.WIDTH * s, core.HEIGHT * s);

        for (var i = 0; i < state.bricks.length; i++) {
          var hp = state.bricks[i];
          if (hp <= 0) continue;
          var x = l.ox + (core.LEFT + (i % core.COLS) * core.STEP_X) * s;
          var y = l.oy + (core.TOP + Math.floor(i / core.COLS) * core.STEP_Y) * s;
          var bg = c.createLinearGradient(0, y, 0, y + core.BRICK_H * s);
          bg.addColorStop(0, "rgba(255,255,255,.1)");
          bg.addColorStop(1, "rgba(8,10,30,.4)");
          c.fillStyle = HP_COLORS[Math.min(hp, 3)];
          env.roundRect(c, x, y, core.BRICK_W * s, core.BRICK_H * s, 6);
          c.fill();
          c.fillStyle = bg;
          c.fill();
          c.fillStyle = "rgba(255,255,255,.35)";
          env.roundRect(c, x + 3, y + 3, core.BRICK_W * s - 6, 3, 2);
          c.fill();
          if (hp > 1) {
            c.fillStyle = "rgba(0,0,0,.35)";
            c.font = env.font(11, 800);
            c.textAlign = "center";
            c.fillText(env.fa(hp), x + (core.BRICK_W * s) / 2, y + core.BRICK_H * s - 5);
          }
        }

        // آیتم‌های در حال سقوط
        c.textAlign = "center";
        for (var k = 0; k < state.items.length; k++) {
          var item = state.items[k];
          var ix = l.ox + item.x * s, iy = l.oy + item.y * s;
          c.fillStyle = env.colors.good;
          c.beginPath();
          c.arc(ix, iy, 12, 0, 6.2832);
          c.fill();
          c.fillStyle = "#0d1324";
          c.font = env.font(14, 800);
          c.fillText(ITEM_ICONS[item.type], ix, iy + 5);
        }

        // راکت
        var w = core.paddleWidth(state) * s;
        var px = l.ox + state.px * s, py = l.oy + core.PADDLE_Y * s;
        var pc = state.wide > 0 ? env.colors.good : env.colors.accent;
        env.glow(c, pc, 18);
        var pgr = c.createLinearGradient(px, 0, px + w, 0);
        pgr.addColorStop(0, pc);
        pgr.addColorStop(1, state.wide > 0 ? "#6ee7ff" : "#a78bfa");
        c.fillStyle = pgr;
        env.roundRect(c, px, py, w, 12, 6);
        c.fill();
        env.glow(c);

        // توپ و ردش
        var moving = state.attach === 0 && state.pause === 0 && !state.over;
        var bx = l.ox + (state.bx + (moving ? state.vx * alpha : 0)) * s;
        var by = l.oy + (state.by + (moving ? state.vy * alpha : 0)) * s;
        trail.push({ x: bx, y: by });
        if (trail.length > 8) trail.shift();
        for (var t = 0; t < trail.length; t++) {
          c.globalAlpha = (t / trail.length) * 0.25;
          c.fillStyle = env.colors.gold;
          c.beginPath();
          c.arc(trail[t].x, trail[t].y, core.BALL_R * s * (t / trail.length), 0, 6.2832);
          c.fill();
        }
        c.globalAlpha = 1;
        c.fillStyle = "#fff6d8";
        env.glow(c, env.colors.gold, 20);
        c.beginPath();
        c.arc(bx, by, core.BALL_R * s, 0, 6.2832);
        c.fill();
        env.glow(c);
      },
    };
  });
})();
