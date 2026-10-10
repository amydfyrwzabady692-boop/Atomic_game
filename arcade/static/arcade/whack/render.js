/* «موش‌زن» — رندر و افکت‌ها. شخصیت‌ها طراحی ساده و اورجینال دارند. */
(function () {
  "use strict";
  Arcade.registerRenderer("whack", function (env) {
    var core = Arcade.cores.whack;
    var bonk = []; // انیمیشن ضربه روی هر سوراخ
    for (var i = 0; i < 9; i++) bonk.push(0);

    function grid() {
      var size = Math.min(env.W - 24, env.H - env.safeTop - 110);
      var top = env.safeTop + 40 + Math.max(0, (env.H - env.safeTop - 110 - size) / 2);
      return { x: (env.W - size) / 2, y: top, cell: size / 3 };
    }
    function center(index) {
      var g = grid();
      return { x: g.x + (index % 3 + 0.5) * g.cell, y: g.y + (Math.floor(index / 3) + 0.5) * g.cell, cell: g.cell };
    }

    function drawCharacter(c, x, y, r, type, rise) {
      var body = type === 2 ? "#3a3f55" : type === 3 ? env.colors.gold : env.colors.pink;
      var top = y + r * 0.55 - rise * r * 1.25;
      if (type === 3) env.glow(c, env.colors.gold, 18);
      c.fillStyle = body;
      c.beginPath();
      c.arc(x, top, r * 0.62, Math.PI, 0);
      c.lineTo(x + r * 0.62, top + r * 1.3);
      c.lineTo(x - r * 0.62, top + r * 1.3);
      c.closePath();
      c.fill();
      env.glow(c);
      // گوش‌ها
      c.beginPath();
      c.arc(x - r * 0.5, top - r * 0.42, r * 0.2, 0, 6.2832);
      c.arc(x + r * 0.5, top - r * 0.42, r * 0.2, 0, 6.2832);
      c.fill();
      // چشم‌ها
      c.fillStyle = "#fff";
      c.beginPath();
      c.arc(x - r * 0.22, top - r * 0.08, r * 0.14, 0, 6.2832);
      c.arc(x + r * 0.22, top - r * 0.08, r * 0.14, 0, 6.2832);
      c.fill();
      c.fillStyle = "#141a2e";
      c.beginPath();
      c.arc(x - r * 0.2, top - r * 0.06, r * 0.07, 0, 6.2832);
      c.arc(x + r * 0.24, top - r * 0.06, r * 0.07, 0, 6.2832);
      c.fill();
      if (type === 2) {
        // بمب روی سر
        c.fillStyle = "#141a2e";
        c.beginPath();
        c.arc(x, top - r * 0.72, r * 0.26, 0, 6.2832);
        c.fill();
        c.strokeStyle = env.colors.gold;
        c.lineWidth = 3;
        c.beginPath();
        c.moveTo(x + r * 0.12, top - r * 0.95);
        c.quadraticCurveTo(x + r * 0.34, top - r * 1.2, x + r * 0.2, top - r * 1.32);
        c.stroke();
        c.fillStyle = env.colors.danger;
        c.beginPath();
        c.arc(x + r * 0.2, top - r * 1.34, r * 0.08 + Math.sin(env.now() / 60) * 1.5, 0, 6.2832);
        c.fill();
      } else if (type === 3) {
        c.fillStyle = "#fff6d8";
        c.font = env.font(r * 0.5, 800);
        c.textAlign = "center";
        c.fillText("★", x, top + r * 0.62);
      }
    }

    return {
      controls: "tap",
      input: function (kind, data) {
        if (kind !== "tap") return null;
        var g = grid();
        var col = Math.floor((data.x - g.x) / g.cell), row = Math.floor((data.y - g.y) / g.cell);
        if (col < 0 || col > 2 || row < 0 || row > 2) return null;
        return [row * 3 + col];
      },
      hud: function (state) {
        if (!state) return "";
        var left = Math.max(0, Math.ceil(((core.LIMIT_TICKS - state.tick) * core.TICK_MS) / 1000));
        return "⏱ " + env.fa(left);
      },
      event: function (name, state) {
        var p = state.lastHole >= 0 ? center(state.lastHole) : { x: env.W / 2, y: env.H / 2 };
        if (state.lastHole >= 0) bonk[state.lastHole] = 1;
        if (name === "hit" || name === "gold") {
          var gold = name === "gold";
          env.fx.burst(p.x, p.y, gold ? env.colors.gold : env.colors.pink, gold ? 26 : 12, gold ? 5 : 3);
          env.fx.text(p.x, p.y - 30, gold ? "+۳۰" : "+۱۰", gold ? env.colors.gold : env.colors.good);
          env.haptic(gold ? "medium" : "light");
          env.sound(gold ? "bonus" : "good");
        } else if (name === "bomb") {
          env.fx.burst(p.x, p.y, env.colors.danger, 30, 6);
          env.fx.flash(env.colors.danger, 0.4);
          env.fx.shake(12);
          env.fx.text(p.x, p.y - 30, "−۱۵", env.colors.danger);
          env.haptic("error");
          env.sound("bad");
        } else if (name === "empty") {
          env.sound("tick");
        } else if (name === "timeup") {
          env.fx.flash(env.colors.accent, 0.3);
          env.haptic("success");
        }
      },
      draw: function (c, state, alpha) {
        var tickNow = state.tick + alpha;
        for (var i = 0; i < 9; i++) {
          var p = center(i), r = p.cell * 0.4;
          bonk[i] *= 0.85;
          // سوراخ
          c.fillStyle = "rgba(28,33,69,.78)";
          env.roundRect(c, p.x - p.cell / 2 + 5, p.y - p.cell / 2 + 5, p.cell - 10, p.cell - 10, 22);
          c.fill();
          c.strokeStyle = "rgba(255,255,255,.1)";
          c.lineWidth = 1.2;
          c.stroke();
          c.fillStyle = "#0b0f1d";
          c.beginPath();
          c.ellipse(p.x, p.y + r * 0.55, r * 0.85, r * 0.34, 0, 0, 6.2832);
          c.fill();

          var hole = state.holes[i];
          if (hole.type !== 0) {
            var age = tickNow - hole.born, left = hole.until - tickNow;
            var rise = Math.max(0, Math.min(1, age / 6, left / 6));
            c.save();
            c.beginPath();
            c.rect(p.x - p.cell / 2, p.y - p.cell / 2 - 20, p.cell, p.cell / 2 + 20 + r * 0.6);
            c.clip();
            drawCharacter(c, p.x, p.y, r, hole.type, rise);
            c.restore();
          }
          // لبه‌ی جلویی سوراخ روی شخصیت
          c.fillStyle = "#1c2145";
          c.beginPath();
          c.ellipse(p.x, p.y + r * 0.86, r * 0.95, r * 0.3, 0, 0, Math.PI);
          c.fill();
          if (bonk[i] > 0.05) {
            c.globalAlpha = bonk[i];
            c.strokeStyle = "#fff";
            c.lineWidth = 3;
            c.beginPath();
            c.arc(p.x, p.y, r * (1.3 - bonk[i] * 0.5), 0, 6.2832);
            c.stroke();
            c.globalAlpha = 1;
          }
        }
      },
    };
  });
})();
