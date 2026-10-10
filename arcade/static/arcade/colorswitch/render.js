/* «تعویض رنگ» — رندر و افکت‌ها */
(function () {
  "use strict";
  Arcade.registerRenderer("colorswitch", function (env) {
    var core = Arcade.cores.colorswitch;
    var COLORS = ["#38d9ff", "#ffc857", "#ff5fa2", "#5ee6a8"];
    var RAD = Math.PI / 180000;
    var S = 0.1; // واحد core → پیکسل
    var camera = 0;
    var squash = 0;

    function screenY(worldY) {
      return env.H * 0.68 - (worldY - camera) * S;
    }

    function drawRing(c, cx, cy, radius, rot) {
      c.lineWidth = core.HALF_T * 2 * S;
      c.lineCap = "butt";
      for (var i = 0; i < 4; i++) {
        c.strokeStyle = COLORS[i];
        env.glow(c, COLORS[i], 12);
        c.beginPath();
        c.arc(cx, cy, radius * S, rot * RAD + (i * Math.PI) / 2, rot * RAD + ((i + 1) * Math.PI) / 2);
        c.stroke();
      }
      env.glow(c);
    }

    return {
      controls: "tap",
      reset: function () {
        camera = 0;
      },
      input: function (kind) {
        return kind === "tap" ? [] : null;
      },
      hud: function (state) {
        if (!state) return "";
        return state.started ? "مرحله " + env.fa(state.level + 1) : "برای شروع تپ کن";
      },
      event: function (name, state) {
        var x = env.W / 2, y = screenY(state.y);
        if (name === "jump") {
          squash = 1;
          env.sound("tick");
        } else if (name === "pass") {
          env.fx.text(x, y - 30, "+۱", env.colors.gold);
          env.fx.burst(x, y, "#ffffff", 10, 3);
          env.haptic("light");
          env.sound("good");
        } else if (name === "switch") {
          env.fx.burst(x, y, COLORS[state.color], 18, 4);
          env.haptic("medium");
          env.sound("bonus");
        } else if (name === "fail") {
          for (var i = 0; i < 4; i++) env.fx.burst(x, y, COLORS[i], 10, 6);
          env.fx.flash(env.colors.danger, 0.45);
          env.fx.shake(14);
          env.haptic("error");
          env.sound("bad");
        }
      },
      draw: function (c, state, alpha) {
        var y = state.y + (state.started && !state.over ? state.vy * alpha : 0);
        var target = Math.max(0, state.maxY - 900);
        camera += (target - camera) * 0.12;
        var tick = state.tick + (state.over ? 0 : alpha);
        var cx = env.W / 2;

        var first = Math.max(0, Math.floor((camera - 2600) / core.SPACING) - 1);
        for (var k = first; k < first + 4; k++) {
          var spec = core.specOf(state, k);
          var sy = screenY(spec.y);
          if (sy < -200 || sy > env.H + 200) {
            // مانع بیرون از صفحه است ولی آیتم رنگ بین دو مانع شاید دیده شود
          } else if (spec.type === 2) {
            var offset = core.barOffset(spec, tick);
            var segW = core.SEG_W * S, h = core.HALF_T * 2 * S;
            for (var i = -1; i < 5; i++) {
              var colorIndex = ((i % 4) + 4) % 4;
              c.fillStyle = COLORS[colorIndex];
              var bx = i * segW + offset * S;
              c.fillRect(bx - 4 * segW, sy - h / 2, segW, h);
              c.fillRect(bx, sy - h / 2, segW, h);
            }
          } else {
            drawRing(c, cx, sy, core.RING_R, core.ringRot(spec, tick));
            if (spec.type === 1) drawRing(c, cx, sy, core.OUTER_R, core.outerRot(spec, tick));
          }
          if (k >= state.passed && spec.type !== 2 && sy > -50 && sy < env.H + 50) {
            c.fillStyle = "rgba(255,255,255,.85)";
            c.font = env.font(22, 800);
            c.textAlign = "center";
            c.fillText("★", cx, sy + 8);
          }
          // آیتم تعویض رنگ بین این مانع و بعدی
          if (k >= state.switched) {
            var iy = screenY(spec.y + core.SPACING / 2);
            for (var q = 0; q < 4; q++) {
              c.fillStyle = COLORS[q];
              c.beginPath();
              c.moveTo(cx, iy);
              c.arc(cx, iy, 13, (q * Math.PI) / 2 + env.now() / 400, ((q + 1) * Math.PI) / 2 + env.now() / 400);
              c.closePath();
              c.fill();
            }
          }
        }

        // سکوی شروع
        var gy = screenY(0) + core.BALL_R * S;
        if (gy < env.H + 20) {
          c.fillStyle = env.colors.panel;
          env.roundRect(c, cx - 60, gy, 120, 10, 5);
          c.fill();
        }

        // توپ
        squash *= 0.8;
        var by = screenY(y), r = core.BALL_R * S;
        c.fillStyle = COLORS[state.color];
        env.glow(c, COLORS[state.color], 22);
        c.beginPath();
        c.ellipse(cx, by, r * (1 - squash * 0.15), r * (1 + squash * 0.2), 0, 0, 6.2832);
        c.fill();
        env.glow(c);
        c.fillStyle = "rgba(255,255,255,.35)";
        c.beginPath();
        c.arc(cx - r * 0.3, by - r * 0.3, r * 0.3, 0, 6.2832);
        c.fill();
      },
    };
  });
})();
