/* «۲۰۴۸ سرعتی» — رندر و افکت‌ها */
(function () {
  "use strict";
  Arcade.registerRenderer("g2048", function (env) {
    var core = Arcade.cores.g2048;
    var DIRS = { up: 0, right: 1, down: 2, left: 3 };
    var TILE_COLORS = {
      2: "#39447a", 4: "#4c5cb0", 8: "#38bdf8", 16: "#34d399", 32: "#fbbf24", 64: "#fb923c",
      128: "#f472b6", 256: "#a78bfa", 512: "#f43f5e", 1024: "#fde047", 2048: "#ffffff",
    };
    var pop = []; // مقیاس لحظه‌ای هر خانه برای انیمیشن
    var nudge = { x: 0, y: 0 };
    var lastDir = 0;
    for (var i = 0; i < 16; i++) pop.push(0);

    function board() {
      var size = Math.min(env.W - 28, env.H - env.safeTop - 120);
      return { x: (env.W - size) / 2, y: env.safeTop + 60 + Math.max(0, (env.H - env.safeTop - 120 - size) / 2), size: size };
    }

    return {
      controls: "swipe",
      reset: function () {
        for (var i = 0; i < 16; i++) pop[i] = 0;
      },
      input: function (kind, data) {
        if (kind !== "swipe") return null;
        lastDir = DIRS[data.dir];
        return [lastDir];
      },
      hud: function (state) {
        if (!state) return "";
        var left = Math.max(0, Math.ceil(((core.LIMIT_TICKS - state.tick) * core.TICK_MS) / 1000));
        return "⏱ " + env.fa(Math.floor(left / 60)) + ":" + env.fa(String(left % 60).padStart(2, "0"));
      },
      event: function (name, state) {
        var push = [[0, -1], [1, 0], [0, 1], [-1, 0]][lastDir];
        if (name === "move" || name === "merge") {
          nudge.x = push[0] * 7;
          nudge.y = push[1] * 7;
          if (state.spawned >= 0) pop[state.spawned] = -1; // کاشی تازه از کوچک بزرگ می‌شود
          env.sound("tick");
        }
        if (name === "merge") {
          for (var i = 0; i < state.merged.length; i++) pop[state.merged[i]] = 1;
          env.haptic("light");
          env.sound("good");
        } else if (name === "fail") {
          env.fx.flash(env.colors.danger, 0.4);
          env.fx.shake(10);
          env.haptic("error");
          env.sound("bad");
        } else if (name === "timeup") {
          env.fx.flash(env.colors.accent, 0.3);
          env.haptic("success");
        }
      },
      draw: function (c, state) {
        var b = board();
        var gap = 8, cell = (b.size - gap * 5) / 4;
        nudge.x *= 0.7;
        nudge.y *= 0.7;

        c.fillStyle = "rgba(10,13,34,.62)";
        env.roundRect(c, b.x, b.y, b.size, b.size, 22);
        c.fill();
        c.strokeStyle = "rgba(255,255,255,.12)";
        c.lineWidth = 1.5;
        c.stroke();
        c.textAlign = "center";
        c.textBaseline = "middle";
        for (var i = 0; i < 16; i++) {
          var col = i % 4, row = Math.floor(i / 4);
          var x = b.x + gap + col * (cell + gap), y = b.y + gap + row * (cell + gap);
          c.fillStyle = "rgba(255,255,255,.05)";
          env.roundRect(c, x, y, cell, cell, 12);
          c.fill();
          var v = state.grid[i];
          if (!v) { pop[i] = 0; continue; }
          pop[i] *= 0.8;
          var scale = 1 + pop[i] * 0.22;
          var size = cell * scale;
          var tx = x + (cell - size) / 2 + nudge.x, ty = y + (cell - size) / 2 + nudge.y;
          var tileColor = TILE_COLORS[v] || "#ffffff";
          var tg = c.createLinearGradient(tx, ty, tx, ty + size);
          tg.addColorStop(0, "rgba(255,255,255,.1)");
          tg.addColorStop(1, "rgba(8,10,30,.32)");
          if (v >= 8) env.glow(c, tileColor, v >= 128 ? 18 : 10);
          c.fillStyle = tileColor;
          env.roundRect(c, tx, ty, size, size, 14);
          c.fill();
          env.glow(c);
          c.fillStyle = tg;
          c.fill();
          c.fillStyle = "rgba(255,255,255,.22)";
          env.roundRect(c, tx + 5, ty + 4, size - 10, 5, 3);
          c.fill();
          c.fillStyle = v <= 4 ? "#eaf0ff" : "#0d1324";
          c.font = env.font(v < 100 ? 30 : v < 1000 ? 25 : 20, 800);
          c.fillText(String(v), tx + size / 2, ty + size / 2 + 2);
        }
        c.textBaseline = "alphabetic";

        // نوار زمان
        var ratio = Math.max(0, 1 - state.tick / core.LIMIT_TICKS);
        c.fillStyle = "rgba(255,255,255,.08)";
        env.roundRect(c, b.x, b.y + b.size + 16, b.size, 10, 5);
        c.fill();
        c.fillStyle = ratio < 0.2 ? env.colors.danger : env.colors.accent;
        env.roundRect(c, b.x, b.y + b.size + 16, b.size * ratio, 10, 5);
        c.fill();
      },
    };
  });
})();
