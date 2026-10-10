/* «پرش ابرها» — رندر و افکت‌ها */
(function () {
  "use strict";
  Arcade.registerRenderer("jumper", function (env) {
    var core = Arcade.cores.jumper;
    var S = 0.1;
    var camera = -core.VIEW_BELOW;
    var squash = 0;

    function screenY(worldY) {
      return env.H - 60 - (worldY - camera) * S * (env.H / 640);
    }
    function drawCloud(c, x, y, w, color) {
      c.fillStyle = color;
      env.roundRect(c, x, y, w, 16, 8);
      c.fill();
      c.beginPath();
      c.arc(x + w * 0.28, y + 3, 11, Math.PI, 0);
      c.arc(x + w * 0.58, y + 2, 14, Math.PI, 0);
      c.fill();
    }

    return {
      controls: "sides",
      reset: function (state) {
        camera = state.camY;
      },
      input: function (kind, data) {
        if (kind !== "tap") return null;
        return [data.x < env.W / 2 ? 0 : 1];
      },
      hud: function (state) {
        if (!state) return "";
        return state.started ? "" : "چپ یا راست را بزن";
      },
      event: function (name, state) {
        var x = state.x * S, y = screenY(state.y);
        if (name === "bounce") {
          squash = 1;
          env.sound("tick");
        } else if (name === "spring") {
          squash = 1.6;
          env.fx.burst(x, y, env.colors.gold, 14, 4);
          env.haptic("medium");
          env.sound("bonus");
        } else if (name === "break") {
          squash = 1;
          env.fx.burst(x, y + 8, "#c9a27a", 12, 3);
          env.haptic("light");
          env.sound("tap");
        } else if (name === "fail") {
          env.fx.flash(env.colors.danger, 0.45);
          env.fx.shake(12);
          env.haptic("error");
          env.sound("bad");
        }
      },
      draw: function (c, state, alpha) {
        camera += (state.camY - camera) * 0.18;
        var moving = state.started && !state.over;
        var sky = c.createLinearGradient(0, 0, 0, env.H);
        var depth = Math.min(1, state.maxY / 60000);
        sky.addColorStop(0, "hsl(" + (225 + depth * 40) + ", 55%, " + (22 - depth * 10) + "%)");
        sky.addColorStop(1, "hsl(" + (205 + depth * 40) + ", 55%, " + (38 - depth * 14) + "%)");
        c.fillStyle = sky;
        c.fillRect(0, 0, env.W, env.H);

        var tick = state.tick + (moving ? alpha : 0);
        for (var i = 0; i < state.plats.length; i++) {
          var p = state.plats[i];
          if (!p.alive) continue;
          var y = screenY(p.y);
          if (y < -30 || y > env.H + 30) continue;
          if (p.w >= core.WIDTH) {
            c.fillStyle = "#2a5a44";
            c.fillRect(0, y, env.W, env.H - y);
            continue;
          }
          var x = core.platformX(p, Math.floor(tick)) * S, w = p.w * S;
          var color = p.type === 2 ? "#c9a27a" : p.type === 1 ? env.colors.accent : "#f4f6ff";
          drawCloud(c, x, y, w, color);
          if (x + w > env.W) drawCloud(c, x - env.W, y, w, color); // ادامه از لبه‌ی دیگر
          if (p.spring) {
            c.fillStyle = env.colors.gold;
            env.roundRect(c, x + w / 2 - 12, y - 12, 24, 12, 4);
            c.fill();
          }
          if (p.type === 2) {
            c.strokeStyle = "rgba(0,0,0,.3)";
            c.lineWidth = 2;
            c.beginPath();
            c.moveTo(x + w * 0.45, y);
            c.lineTo(x + w * 0.5, y + 8);
            c.lineTo(x + w * 0.56, y + 2);
            c.lineTo(x + w * 0.6, y + 16);
            c.stroke();
          }
        }

        // شخصیت
        squash *= 0.82;
        var px = (state.x + (moving ? state.dir * core.H_SPEED * alpha : 0)) * S;
        var py = screenY(state.y + (moving ? state.vy * alpha : 0));
        for (var copy = -1; copy <= 1; copy++) {
          var cx = px + copy * env.W;
          if (cx < -30 || cx > env.W + 30) continue;
          c.save();
          c.translate(cx, py);
          c.scale(1 + squash * 0.18, 1 - squash * 0.2);
          c.fillStyle = env.colors.pink;
          env.roundRect(c, -15, -40, 30, 40, 13);
          c.fill();
          c.fillStyle = "#fff";
          c.beginPath();
          c.arc(state.dir * 6 - 5, -26, 5, 0, 6.2832);
          c.arc(state.dir * 6 + 6, -26, 5, 0, 6.2832);
          c.fill();
          c.fillStyle = "#141a2e";
          c.beginPath();
          c.arc(state.dir * 8 - 5, -26, 2.2, 0, 6.2832);
          c.arc(state.dir * 8 + 6, -26, 2.2, 0, 6.2832);
          c.fill();
          c.fillStyle = "#1a2238";
          c.fillRect(-11, -3, 8, 5);
          c.fillRect(3, -3, 8, 5);
          c.restore();
        }

        // راهنمای لمس چپ/راست
        if (!state.started) {
          c.fillStyle = "rgba(255,255,255,.5)";
          c.font = env.font(40, 800);
          c.textAlign = "center";
          c.fillText("‹", env.W * 0.18, env.H * 0.55);
          c.fillText("›", env.W * 0.82, env.H * 0.55);
        }
      },
    };
  });
})();
