/* «برج‌ساز» — رندر و افکت‌ها */
(function () {
  "use strict";
  Arcade.registerRenderer("stack", function (env) {
    var BLOCK_H = 30;
    var camera = 0; // تعداد بلوک‌هایی که دوربین بالا رفته (نرم)
    var falling = []; // تکه‌های بریده‌شده‌ی در حال سقوط

    function colorOf(index) {
      return "hsl(" + ((index * 11 + 190) % 360) + ", 85%, " + (62 - (index % 2) * 5) + "%)";
    }
    function baseY() {
      return env.H - 110;
    }
    function drawBlock(c, x, w, y, color, alpha) {
      c.globalAlpha = alpha === undefined ? 1 : alpha;
      var grad = c.createLinearGradient(0, y, 0, y + BLOCK_H);
      grad.addColorStop(0, "rgba(255,255,255,.12)");
      grad.addColorStop(1, "rgba(10,12,32,.5)");
      c.fillStyle = color;
      env.roundRect(c, x / 10, y, Math.max(w / 10, 1), BLOCK_H - 2, 7);
      c.fill();
      c.fillStyle = grad;
      c.fill();
      c.fillStyle = "rgba(255,255,255,.3)";
      env.roundRect(c, x / 10 + 3, y + 3, Math.max(w / 10 - 6, 0), 4, 2);
      c.fill();
      c.globalAlpha = 1;
    }

    return {
      controls: "tap",
      reset: function () {
        camera = 0;
        falling = [];
      },
      input: function (kind) {
        return kind === "tap" ? [] : null;
      },
      hud: function (state) {
        return state && state.combo > 1 ? "کمبو ×" + env.fa(state.combo) : "";
      },
      event: function (name, state) {
        var top = state.blocks[state.blocks.length - 1];
        var y = baseY() - (state.blocks.length - 1 - camera) * BLOCK_H;
        if (name === "perfect") {
          env.fx.burst((top.x + top.w / 2) / 10, y, env.colors.gold, 14, 3);
          env.fx.text(env.W / 2, y - 24, "عالی!", env.colors.gold);
          env.haptic("medium");
          env.sound("bonus");
        } else if (name === "cut") {
          if (state.lastCut) falling.push({ x: state.lastCut.x, w: state.lastCut.w, y: y, vy: 0, index: state.blocks.length - 1 });
          env.haptic("light");
          env.sound("tap");
        } else if (name === "fail") {
          if (state.lastCut) falling.push({ x: state.lastCut.x, w: state.lastCut.w, y: y - BLOCK_H, vy: 0, index: state.blocks.length });
          env.fx.flash(env.colors.danger, 0.45);
          env.fx.shake(12);
          env.haptic("error");
          env.sound("bad");
        }
      },
      draw: function (c, state, alpha) {
        var count = state.blocks.length;
        var target = Math.max(0, count - 7);
        camera += (target - camera) * 0.12;
        var by = baseY();

        for (var i = Math.max(0, Math.floor(camera) - 1); i < count; i++) {
          var b = state.blocks[i];
          drawBlock(c, b.x, b.w, by - (i - camera) * BLOCK_H, colorOf(i));
        }
        // پایه
        var gy0 = by + BLOCK_H - (0 - camera) * BLOCK_H - 2;
        var ground = c.createLinearGradient(0, gy0, 0, gy0 + 120);
        ground.addColorStop(0, "rgba(110,231,255,.3)");
        ground.addColorStop(0.04, "rgba(28,33,69,.95)");
        ground.addColorStop(1, "rgba(9,11,28,1)");
        c.fillStyle = ground;
        c.fillRect(0, gy0, env.W, env.H);

        if (!state.over && state.cur) {
          var cur = state.cur;
          var x = cur.x + cur.dir * cur.speed * alpha;
          env.glow(c, colorOf(count), 22);
          drawBlock(c, x, cur.w, by - (count - camera) * BLOCK_H, colorOf(count));
          env.glow(c);
        }
        for (var f = falling.length - 1; f >= 0; f--) {
          var piece = falling[f];
          piece.vy += 0.6;
          piece.y += piece.vy;
          drawBlock(c, piece.x, piece.w, piece.y, colorOf(piece.index), 0.8);
          if (piece.y > env.H + 40) falling.splice(f, 1);
        }
      },
    };
  });
})();
