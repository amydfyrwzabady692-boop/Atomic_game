/* «پرنده‌ی پرشی» — رندر و افکت‌ها */
(function () {
  "use strict";
  Arcade.registerRenderer("flappy", function (env) {
    var core = Arcade.cores.flappy;
    var wing = 0;

    function layout() {
      var scale = Math.min(env.W / core.FIELD_W, env.H / core.FIELD_H);
      return { s: scale, ox: (env.W - core.FIELD_W * scale) / 2, oy: env.H - core.FIELD_H * scale };
    }

    return {
      controls: "tap",
      input: function (kind) {
        return kind === "tap" ? [] : null;
      },
      hud: function (state) {
        return state && !state.started ? "برای شروع تپ کن" : "";
      },
      event: function (name, state) {
        var l = layout();
        var bx = l.ox + core.BIRD_X * l.s, by = l.oy + state.y * l.s;
        if (name === "flap") {
          wing = 1;
          env.sound("tick");
        } else if (name === "score") {
          env.fx.text(bx + 30, by - 26, "+۱", env.colors.gold);
          env.haptic("light");
          env.sound("good");
        } else if (name === "fail") {
          env.fx.burst(bx, by, env.colors.gold, 26, 5);
          env.fx.flash(env.colors.danger, 0.5);
          env.fx.shake(14);
          env.haptic("error");
          env.sound("bad");
        }
      },
      draw: function (c, state, alpha) {
        var l = layout(), s = l.s;
        var moving = state.started && !state.over;
        var speed = moving ? core.speedFor(state.score) * alpha : 0;

        // آسمان و تپه‌های پس‌زمینه
        var sky = c.createLinearGradient(0, 0, 0, env.H);
        sky.addColorStop(0, "rgba(27,20,70,.2)");
        sky.addColorStop(1, "rgba(56,120,190,.55)");
        c.fillStyle = sky;
        c.fillRect(0, 0, env.W, env.H);
        c.fillStyle = "rgba(255,255,255,.05)";
        var drift = (state.tick * 0.3) % 180;
        for (var h = -1; h < 4; h++) {
          c.beginPath();
          c.arc(h * 180 - drift + 90, env.H - 20, 130, Math.PI, 0);
          c.fill();
        }

        for (var i = 0; i < state.pipes.length; i++) {
          var p = state.pipes[i];
          var x = l.ox + (p.x - speed) * s, w = core.PIPE_W * s;
          var top = l.oy + p.gapY * s, bottom = l.oy + (p.gapY + p.gapH) * s;
          var pg = c.createLinearGradient(x, 0, x + w, 0);
          pg.addColorStop(0, "#7af0bd");
          pg.addColorStop(0.5, "#34d399");
          pg.addColorStop(1, "#0f9f6e");
          c.fillStyle = pg;
          env.roundRect(c, x, -20, w, top + 20, 8);
          c.fill();
          env.roundRect(c, x, bottom, w, env.H - bottom + 20, 8);
          c.fill();
          c.fillStyle = "rgba(0,0,0,.18)";
          c.fillRect(x + w - 10, 0, 10, top - 6);
          c.fillRect(x + w - 10, bottom + 6, 10, env.H);
          c.fillStyle = "#a7f3d0";
          env.roundRect(c, x - 4, top - 18, w + 8, 18, 6);
          c.fill();
          env.roundRect(c, x - 4, bottom, w + 8, 18, 6);
          c.fill();
        }

        // پرنده
        var vy = state.vy;
        var by = l.oy + (state.y + (moving ? vy * alpha : 0)) * s;
        if (!state.started) by += Math.sin(env.now() / 220) * 5;
        var bx = l.ox + core.BIRD_X * s, r = core.RADIUS * s;
        wing *= 0.86;
        c.save();
        c.translate(bx, by);
        c.rotate(Math.max(-0.5, Math.min(1.1, vy / 170)));
        c.fillStyle = env.colors.gold;
        env.glow(c, env.colors.gold, 16);
        c.beginPath();
        c.arc(0, 0, r, 0, 6.2832);
        c.fill();
        env.glow(c);
        c.fillStyle = "#ffd98a";
        c.beginPath();
        c.ellipse(-r * 0.25, r * 0.15 - wing * 6, r * 0.55, r * 0.34, -0.3, 0, 6.2832);
        c.fill();
        c.fillStyle = "#fff";
        c.beginPath();
        c.arc(r * 0.38, -r * 0.3, r * 0.3, 0, 6.2832);
        c.fill();
        c.fillStyle = "#1a2238";
        c.beginPath();
        c.arc(r * 0.46, -r * 0.3, r * 0.13, 0, 6.2832);
        c.fill();
        c.fillStyle = env.colors.danger;
        c.beginPath();
        c.moveTo(r * 0.8, -r * 0.05);
        c.lineTo(r * 1.45, r * 0.12);
        c.lineTo(r * 0.8, r * 0.34);
        c.closePath();
        c.fill();
        c.restore();

        c.fillStyle = "#16203f";
        c.fillRect(0, env.H - 6, env.W, 6);
      },
    };
  });
})();
