/* «دونده‌ی سه‌خطی» — رندر شبه‌سه‌بعدی و افکت‌ها */
(function () {
  "use strict";
  Arcade.registerRenderer("runner", function (env) {
    var core = Arcade.cores.runner;
    var ACTIONS = { left: 0, right: 1, up: 2 };
    var laneX = 1; // موقعیت نمایشی (نرم) بین خط‌ها
    var FAR = 9000;

    function horizon() { return env.safeTop + 50; }
    function ground() { return env.H - 120; }
    /* عمق z (۰ = بازیکن) → موقعیت و مقیاس روی صفحه */
    function project(z) {
      var t = Math.max(0, Math.min(1, z / FAR));
      var k = 1 / (1 + t * 3.2); // پرسپکتیو
      var hy = horizon(), gy = ground();
      return { y: hy + (gy - hy) * k, scale: k };
    }
    function xFor(lane, scale) {
      return env.W / 2 + (lane - 1) * 96 * scale;
    }

    return {
      controls: "swipe",
      reset: function (state) { laneX = state.lane; },
      input: function (kind, data) {
        if (kind === "swipe" && ACTIONS[data.dir] !== undefined) return [ACTIONS[data.dir]];
        return null;
      },
      hud: function (state) {
        return state ? "سطح " + env.fa(state.level + 1) : "";
      },
      event: function (name, state) {
        var px = xFor(laneX, 1), py = ground();
        if (name === "coin") {
          env.fx.burst(px, py - 40, env.colors.gold, 10, 3);
          env.fx.text(px, py - 70, "+۵", env.colors.gold);
          env.haptic("light");
          env.sound("bonus");
        } else if (name === "jump") {
          env.sound("tick");
        } else if (name === "move") {
          env.sound("tap");
        } else if (name === "fail") {
          env.fx.flash(env.colors.danger, 0.5);
          env.fx.shake(16);
          env.fx.burst(px, py - 30, env.colors.danger, 26, 5);
          env.haptic("error");
          env.sound("bad");
        }
      },
      draw: function (c, state, alpha) {
        var hy = horizon(), gy = ground();
        laneX += (state.lane - laneX) * 0.35;
        var dist = state.dist + (state.over ? 0 : core.speedFor(state.passed) * alpha);

        // آسمان و جاده
        var sky = c.createLinearGradient(0, 0, 0, hy + 40);
        sky.addColorStop(0, "rgba(27,20,70,0)");
        sky.addColorStop(1, "rgba(244,114,182,.45)");
        c.fillStyle = sky;
        c.fillRect(0, 0, env.W, hy + 40);
        c.fillStyle = "#0b0d22";
        c.fillRect(0, hy, env.W, env.H - hy);
        var far = project(FAR), near = { y: env.H, scale: 1.25 };
        c.fillStyle = "#232c4d";
        c.beginPath();
        c.moveTo(xFor(-0.5, far.scale), far.y);
        c.lineTo(xFor(2.5, far.scale), far.y);
        c.lineTo(xFor(2.5, near.scale), near.y);
        c.lineTo(xFor(-0.5, near.scale), near.y);
        c.closePath();
        c.fill();
        c.strokeStyle = "rgba(110,231,255,.55)";
        c.lineWidth = 2;
        env.glow(c, "#6ee7ff", 10);
        for (var e = 0; e < 2; e++) {
          c.beginPath();
          c.moveTo(xFor(e * 3 - 0.5, far.scale), far.y);
          c.lineTo(xFor(e * 3 - 0.5, near.scale), near.y);
          c.stroke();
        }
        env.glow(c);
        c.strokeStyle = "rgba(255,255,255,.14)";
        for (var l = 0; l < 2; l++) {
          c.beginPath();
          c.moveTo(xFor(l + 0.5, far.scale), far.y);
          c.lineTo(xFor(l + 0.5, near.scale), near.y);
          c.stroke();
        }
        // خط‌های عرضی متحرک برای حس سرعت
        var stripe = core.ROW_GAP / 2;
        for (var z = stripe - (dist % stripe); z < FAR; z += stripe) {
          var s = project(z);
          c.strokeStyle = "rgba(255,255,255," + (0.1 * s.scale) + ")";
          c.beginPath();
          c.moveTo(xFor(-0.5, s.scale), s.y);
          c.lineTo(xFor(2.5, s.scale), s.y);
          c.stroke();
        }

        // موانع و سکه‌ها (از دور به نزدیک)
        for (var k = Math.min(state.rows.length - 1, state.passed + 7); k >= state.passed; k--) {
          var rz = 4200 + k * core.ROW_GAP - dist;
          if (rz < -200 || rz > FAR) continue;
          var p = project(rz), row = state.rows[k];
          for (var lane = 0; lane < 3; lane++) {
            var cell = row[lane], x = xFor(lane, p.scale), w = 70 * p.scale;
            if (cell === 1) {
              c.fillStyle = env.colors.gold;
              env.roundRect(c, x - w / 2, p.y - 26 * p.scale, w, 26 * p.scale, 6 * p.scale);
              c.fill();
              c.fillStyle = "rgba(0,0,0,.25)";
              c.fillRect(x - w / 2, p.y - 9 * p.scale, w, 5 * p.scale);
            } else if (cell === 2) {
              c.fillStyle = env.colors.danger;
              env.roundRect(c, x - w / 2, p.y - 92 * p.scale, w, 92 * p.scale, 8 * p.scale);
              c.fill();
              c.fillStyle = "rgba(255,255,255,.22)";
              c.fillRect(x - w / 2 + 6 * p.scale, p.y - 84 * p.scale, w - 12 * p.scale, 10 * p.scale);
            } else if (cell === 3) {
              c.fillStyle = "#ffd166";
              env.glow(c, "#ffc857", 12);
              c.beginPath();
              c.ellipse(x, p.y - 34 * p.scale, 15 * p.scale * Math.abs(Math.cos(env.now() / 220 + k)) + 2, 15 * p.scale, 0, 0, 6.2832);
              c.fill();
              env.glow(c);
            }
          }
        }

        // دونده
        var px = xFor(laneX, 1);
        var lift = state.air > 0 ? Math.sin((1 - (state.air - alpha) / core.JUMP_TICKS) * Math.PI) * 64 : 0;
        var run = Math.sin(env.now() / 70) * (state.over || lift > 0 ? 0 : 1);
        c.fillStyle = "rgba(0,0,0,.35)";
        c.beginPath();
        c.ellipse(px, gy + 4, 22 - lift * 0.12, 7 - lift * 0.04, 0, 0, 6.2832);
        c.fill();
        c.save();
        c.translate(px, gy - lift);
        c.fillStyle = "#1a2238";
        c.fillRect(-11 + run * 4, -16, 9, 16);
        c.fillRect(2 - run * 4, -16, 9, 16);
        c.fillStyle = env.colors.accent;
        env.roundRect(c, -16, -52, 32, 40, 10);
        c.fill();
        c.fillStyle = "#f3c9a0";
        c.beginPath();
        c.arc(0, -64, 14, 0, 6.2832);
        c.fill();
        c.fillStyle = env.colors.violet;
        c.beginPath();
        c.arc(0, -68, 14, Math.PI, 0);
        c.fill();
        c.restore();
      },
    };
  });
})();
