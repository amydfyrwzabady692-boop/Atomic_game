/* «مار کلاسیک» — رندر و افکت‌ها */
(function () {
  "use strict";
  Arcade.registerRenderer("snake", function (env) {
    var core = Arcade.cores.snake;
    var DIRS = { up: 0, right: 1, down: 2, left: 3 };
    var DX = [0, 1, 0, -1], DY = [-1, 0, 1, 0];

    function board() {
      var top = env.safeTop + 6;
      var cell = Math.floor(Math.min((env.W - 16) / core.COLS, (env.H - top - 16) / core.ROWS));
      var w = cell * core.COLS, h = cell * core.ROWS;
      return { x: (env.W - w) / 2, y: top + Math.max(0, (env.H - top - 16 - h) / 2), cell: cell, w: w, h: h };
    }
    function pos(b, index) {
      return { x: b.x + (index % core.COLS) * b.cell, y: b.y + Math.floor(index / core.COLS) * b.cell };
    }

    return {
      controls: "swipe",
      input: function (kind, data) {
        if (kind !== "swipe") return null;
        return [DIRS[data.dir]];
      },
      hud: function (state) {
        return state ? "طول " + env.fa(state.body.length) : "";
      },
      event: function (name, state) {
        var b = board();
        var head = pos(b, state.body[state.body.length - 1]);
        if (name === "eat") {
          env.fx.burst(head.x + b.cell / 2, head.y + b.cell / 2, env.colors.danger, 12, 3);
          env.fx.text(head.x + b.cell / 2, head.y - 6, "+۱۰", env.colors.gold);
          env.haptic("light");
          env.sound("good");
        } else if (name === "fail") {
          env.fx.flash(env.colors.danger, 0.5);
          env.fx.shake(14);
          env.fx.burst(head.x + b.cell / 2, head.y + b.cell / 2, env.colors.good, 26, 5);
          env.haptic("error");
          env.sound("bad");
        }
      },
      draw: function (c, state, alpha) {
        var b = board(), cell = b.cell;
        c.fillStyle = "rgba(10,13,34,.62)";
        env.roundRect(c, b.x - 5, b.y - 5, b.w + 10, b.h + 10, 16);
        c.fill();
        c.strokeStyle = "rgba(110,231,255,.25)";
        c.lineWidth = 1.5;
        c.stroke();
        c.fillStyle = "rgba(255,255,255,.03)";
        for (var gy = 0; gy < core.ROWS; gy++) {
          for (var gx = gy % 2; gx < core.COLS; gx += 2) c.fillRect(b.x + gx * cell, b.y + gy * cell, cell, cell);
        }

        // غذا
        if (state.food >= 0) {
          var f = pos(b, state.food);
          var pulse = 1 + Math.sin(env.now() / 160) * 0.1;
          c.fillStyle = env.colors.danger;
          env.glow(c, env.colors.danger, 16);
          c.beginPath();
          c.arc(f.x + cell / 2, f.y + cell / 2, cell * 0.36 * pulse, 0, 6.2832);
          c.fill();
          env.glow(c);
          c.fillStyle = env.colors.good;
          c.fillRect(f.x + cell / 2 - 1, f.y + cell * 0.1, 3, cell * 0.2);
        }

        // بدن مار (حرکت نرم سر بین دو خانه)
        var n = state.body.length;
        var progress = state.over ? 0 : (state.counter + alpha) / core.stepEvery(state.foods);
        for (var i = 0; i < n; i++) {
          var p = pos(b, state.body[i]);
          var isHead = i === n - 1;
          var t = i / Math.max(1, n - 1);
          c.fillStyle = isHead ? "#b5ffe0" : "hsl(" + (165 - t * 25) + ", 85%, " + (36 + t * 26) + "%)";
          env.glow(c, isHead ? "#5ee6a8" : null, 16);
          var ox = 0, oy = 0;
          if (isHead) {
            var d = state.queue.length ? state.queue[0] : state.dir;
            ox = DX[d] * cell * progress * 0.5;
            oy = DY[d] * cell * progress * 0.5;
          }
          env.roundRect(c, p.x + 1 + ox, p.y + 1 + oy, cell - 2, cell - 2, isHead ? cell * 0.4 : cell * 0.3);
          c.fill();
          env.glow(c);
          if (isHead) {
            c.fillStyle = "#0d1324";
            var ex = DX[state.dir], ey = DY[state.dir];
            c.beginPath();
            c.arc(p.x + cell / 2 + ox + ex * cell * 0.18 - ey * cell * 0.18, p.y + cell / 2 + oy + ey * cell * 0.18 - ex * cell * 0.18, cell * 0.09, 0, 6.2832);
            c.arc(p.x + cell / 2 + ox + ex * cell * 0.18 + ey * cell * 0.18, p.y + cell / 2 + oy + ey * cell * 0.18 + ex * cell * 0.18, cell * 0.09, 0, 6.2832);
            c.fill();
          }
        }
      },
    };
  });
})();
