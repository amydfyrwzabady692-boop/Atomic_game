/* «زمان‌سنج» — رندر و افکت‌ها */
(function () {
  "use strict";
  Arcade.registerRenderer("timing", function (env) {
    var core = Arcade.cores.timing;
    var pulse = 0;

    function bar() {
      var w = env.W - 48;
      return { x: 24, y: env.H * 0.52, w: w, h: 46 };
    }

    return {
      controls: "tap",
      input: function (kind) {
        return kind === "tap" ? [] : null;
      },
      hud: function (state) {
        if (!state) return "";
        var left = Math.max(0, Math.ceil(((core.LIMIT_TICKS - state.tick) * core.TICK_MS) / 1000));
        return "⏱ " + env.fa(left) + "   " + "❤️".repeat(Math.max(state.lives, 0));
      },
      event: function (name, state) {
        var b = bar();
        var x = b.x + (state.pos / core.BAR) * b.w;
        if (name === "perfect") {
          pulse = 1;
          env.fx.burst(x, b.y + b.h / 2, env.colors.gold, 22, 4);
          env.fx.text(x, b.y - 18, "عالی! +۲۰", env.colors.gold);
          env.haptic("medium");
          env.sound("bonus");
        } else if (name === "hit") {
          pulse = 0.6;
          env.fx.burst(x, b.y + b.h / 2, env.colors.good, 10, 3);
          env.fx.text(x, b.y - 18, "+۱۰", env.colors.good);
          env.haptic("light");
          env.sound("good");
        } else if (name === "miss") {
          env.fx.flash(env.colors.danger, 0.3);
          env.fx.shake(8);
          env.haptic("error");
          env.sound("bad");
        } else if (name === "timeup") {
          env.fx.flash(env.colors.accent, 0.3);
          env.haptic("success");
        }
      },
      draw: function (c, state, alpha) {
        var b = bar();
        var z = state.zone;
        pulse *= 0.9;

        // دایره‌ی زمان باقی‌مانده
        var remain = 1 - state.tick / core.LIMIT_TICKS;
        var cx = env.W / 2, cy = b.y - 130;
        c.lineWidth = 8;
        c.strokeStyle = "rgba(255,255,255,.08)";
        c.beginPath();
        c.arc(cx, cy, 44, 0, 6.2832);
        c.stroke();
        c.strokeStyle = remain < 0.2 ? env.colors.danger : env.colors.accent;
        c.lineCap = "round";
        env.glow(c, c.strokeStyle, 16);
        c.beginPath();
        c.arc(cx, cy, 44, -Math.PI / 2, -Math.PI / 2 + 6.2832 * remain);
        c.stroke();
        env.glow(c);
        c.fillStyle = env.colors.ink;
        c.textAlign = "center";
        c.font = env.font(15, 700);
        c.fillText("مرحله " + env.fa(state.level + 1), cx, cy + 5);

        // نوار
        c.fillStyle = "rgba(10,13,34,.6)";
        env.roundRect(c, b.x, b.y, b.w, b.h, 23);
        c.fill();
        c.strokeStyle = "rgba(255,255,255,.12)";
        c.lineWidth = 1.5;
        c.stroke();
        // ناحیه‌ی هدف و مرکز آن
        var zx = b.x + (z.s / core.BAR) * b.w, zw = (z.w / core.BAR) * b.w;
        c.fillStyle = env.colors.good;
        env.glow(c, env.colors.good, 18 + pulse * 20);
        c.globalAlpha = 0.85 + pulse * 0.15;
        env.roundRect(c, zx, b.y + 4, zw, b.h - 8, 10);
        c.fill();
        c.globalAlpha = 1;
        env.glow(c, env.colors.gold, 14);
        c.fillStyle = env.colors.gold;
        env.roundRect(c, zx + zw * 0.3, b.y + 4, zw * 0.4, b.h - 8, 8);
        c.fill();
        env.glow(c, "#ffffff", 16);

        // نشانگر
        var pos = state.pos;
        if (!state.over) pos = Math.max(0, Math.min(core.BAR, pos + state.dir * state.speed * alpha));
        var x = b.x + (pos / core.BAR) * b.w;
        c.fillStyle = env.colors.ink;
        env.roundRect(c, x - 4, b.y - 12, 8, b.h + 24, 4);
        c.fill();
        c.beginPath();
        c.moveTo(x - 10, b.y - 22);
        c.lineTo(x + 10, b.y - 22);
        c.lineTo(x, b.y - 8);
        c.closePath();
        c.fill();

        env.glow(c);
        c.fillStyle = env.colors.muted;
        c.font = env.font(14, 500);
        c.fillText("وسط ناحیه = امتیاز دوبرابر", env.W / 2, b.y + b.h + 44);
      },
    };
  });
})();
