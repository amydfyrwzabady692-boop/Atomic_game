/* «هیزم‌شکن» — رندر و افکت‌ها */
(function () {
  "use strict";
  Arcade.registerRenderer("timber", function (env) {
    var core = Arcade.cores.timber;
    var SEG_H = 62, TRUNK_W = 78, BRANCH_W = 96;
    var swing = 0, drop = 0;
    var chips = []; // تکه‌چوب‌های پرتاب‌شده
    var fallen = 0;

    function groundY() { return env.H - 96; }

    function drawBranch(c, cx, y, dir) {
      var x = dir < 0 ? cx - TRUNK_W / 2 - BRANCH_W : cx + TRUNK_W / 2;
      c.fillStyle = "#8a5a36";
      env.roundRect(c, x, y + SEG_H * 0.42, BRANCH_W, 14, 7);
      c.fill();
      c.fillStyle = env.colors.good;
      var lx = dir < 0 ? x + 16 : x + BRANCH_W - 16;
      c.beginPath();
      c.arc(lx, y + SEG_H * 0.42 + 4, 20, 0, 6.2832);
      c.arc(lx + dir * 22, y + SEG_H * 0.42 + 10, 15, 0, 6.2832);
      c.fill();
    }

    function drawClock(c, x, y) {
      c.fillStyle = env.colors.gold;
      c.beginPath();
      c.arc(x, y, 13, 0, 6.2832);
      c.fill();
      c.strokeStyle = "#1a2238";
      c.lineWidth = 2.5;
      c.beginPath();
      c.moveTo(x, y - 7);
      c.lineTo(x, y);
      c.lineTo(x + 5, y + 3);
      c.stroke();
    }

    return {
      controls: "sides",
      reset: function () {
        chips = [];
        swing = drop = fallen = 0;
      },
      input: function (kind, data) {
        if (kind !== "tap") return null;
        return [data.x < env.W / 2 ? 0 : 1];
      },
      hud: function (state) {
        if (!state) return "";
        return state.started ? "سطح " + env.fa(state.level + 1) : "چپ یا راست صفحه را بزن";
      },
      event: function (name, state) {
        var cx = env.W / 2;
        if (name === "chop") {
          swing = 1;
          drop = 1;
          chips.push({ x: cx, y: groundY() - SEG_H, vx: state.side === 0 ? 9 : -9, vy: -5, rot: 0 });
          env.fx.shake(2.5);
          env.haptic("light");
          env.sound("tap");
        } else if (name === "clock") {
          env.fx.text(cx, groundY() - SEG_H * 2, "+ زمان ⏱", env.colors.gold);
          env.haptic("medium");
          env.sound("bonus");
        } else if (name === "combo") {
          env.fx.text(cx, groundY() - SEG_H * 3, "سرعتی! +۵", env.colors.accent);
          env.sound("good");
        } else if (name === "fail") {
          fallen = 0.01;
          env.fx.flash(env.colors.danger, 0.5);
          env.fx.shake(14);
          env.haptic("error");
          env.sound("bad");
        }
      },
      draw: function (c, state) {
        var cx = env.W / 2, gy = groundY();
        swing *= 0.78;
        drop *= 0.7;
        if (fallen > 0) fallen = Math.min(1, fallen + 0.06);

        // آسمان
        var sky = c.createLinearGradient(0, 0, 0, env.H);
        sky.addColorStop(0, "rgba(27,20,70,.15)");
        sky.addColorStop(1, "rgba(52,110,160,.6)");
        c.fillStyle = sky;
        c.fillRect(0, 0, env.W, env.H);

        // تنه و شاخه‌ها (از پایین به بالا)، با انیمیشن پایین آمدن بعد از هر ضربه
        var offset = drop * SEG_H;
        for (var i = 0; i < state.segs.length + 4; i++) {
          var y = gy - (i + 1) * SEG_H - offset;
          if (y < -SEG_H * 2) break;
          c.fillStyle = i % 2 === 0 ? "#a06a3f" : "#96623a";
          c.fillRect(cx - TRUNK_W / 2, y, TRUNK_W, SEG_H + 1);
          c.fillStyle = "rgba(0,0,0,.12)";
          c.fillRect(cx + TRUNK_W / 2 - 12, y, 12, SEG_H + 1);
          var seg = state.segs[i];
          if (!seg) continue;
          if (seg.b === 1) drawBranch(c, cx, y, -1);
          else if (seg.b === 2) drawBranch(c, cx, y, 1);
          if (seg.c === 1) drawClock(c, cx - TRUNK_W / 2 - 34, y + SEG_H / 2);
          else if (seg.c === 2) drawClock(c, cx + TRUNK_W / 2 + 34, y + SEG_H / 2);
        }

        // زمین
        c.fillStyle = "#1c3a2e";
        c.fillRect(0, gy, env.W, env.H - gy);
        c.fillStyle = "#2a5a44";
        c.fillRect(0, gy, env.W, 8);
        c.fillStyle = "#7a4f2e";
        env.roundRect(c, cx - TRUNK_W / 2 - 8, gy - 10, TRUNK_W + 16, 18, 6);
        c.fill();

        // تکه‌چوب‌های در حال پرتاب
        for (var k = chips.length - 1; k >= 0; k--) {
          var chip = chips[k];
          chip.x += chip.vx;
          chip.y += chip.vy;
          chip.vy += 0.9;
          chip.rot += chip.vx * 0.03;
          c.save();
          c.translate(chip.x, chip.y + SEG_H / 2);
          c.rotate(chip.rot);
          c.fillStyle = "#a06a3f";
          c.fillRect(-TRUNK_W / 2, -SEG_H / 2, TRUNK_W, SEG_H);
          c.restore();
          if (chip.y > env.H + 80 || chip.x < -120 || chip.x > env.W + 120) chips.splice(k, 1);
        }

        // شخصیت هیزم‌شکن
        var dir = state.side === 0 ? -1 : 1;
        var px = cx + dir * (TRUNK_W / 2 + 40);
        c.save();
        c.translate(px, gy);
        if (fallen > 0) {
          c.translate(dir * fallen * 20, 0);
          c.rotate(dir * fallen * 1.45);
        }
        c.fillStyle = env.colors.danger;
        env.roundRect(c, -17, -50, 34, 40, 10);
        c.fill();
        c.fillStyle = "#1a2238";
        c.fillRect(-15, -12, 12, 12);
        c.fillRect(3, -12, 12, 12);
        c.fillStyle = "#f3c9a0";
        c.beginPath();
        c.arc(0, -64, 16, 0, 6.2832);
        c.fill();
        c.fillStyle = env.colors.gold;
        env.roundRect(c, -18, -84, 36, 12, 6);
        c.fill();
        // تبر
        c.save();
        c.translate(-dir * 6, -40);
        c.rotate(-dir * (0.9 - swing * 1.5));
        c.fillStyle = "#c9a27a";
        c.fillRect(-2, -40, 5, 44);
        c.fillStyle = "#dfe6f5";
        c.beginPath();
        c.moveTo(0, -42);
        c.lineTo(-dir * 20, -36);
        c.lineTo(-dir * 20, -22);
        c.lineTo(0, -26);
        c.closePath();
        c.fill();
        c.restore();
        c.restore();

        // نوار زمان
        var bw = env.W - 80, bx = 40, byy = env.safeTop + 6;
        c.fillStyle = "rgba(0,0,0,.35)";
        env.roundRect(c, bx, byy, bw, 16, 8);
        c.fill();
        var ratio = state.time / core.MAX_TIME;
        c.fillStyle = ratio < 0.25 ? env.colors.danger : ratio < 0.5 ? env.colors.gold : env.colors.good;
        env.roundRect(c, bx + 2, byy + 2, Math.max(0, (bw - 4) * ratio), 12, 6);
        c.fill();
      },
    };
  });
})();
