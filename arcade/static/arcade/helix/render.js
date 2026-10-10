/* «مارپیچ سقوط» — رندر شبه‌سه‌بعدی و افکت‌ها */
(function () {
  "use strict";
  Arcade.registerRenderer("helix", function (env) {
    var core = Arcade.cores.helix;
    var RAD = Math.PI / 180000;
    var TWO_PI = Math.PI * 2;
    var R_OUT = 128, R_IN = 40, TILT = 0.34, SY = 0.085;
    var camera = 0, pendingDx = 0, squash = 0;

    function floorScreenY(index) {
      return env.safeTop + 120 + (index * core.FLOOR_H - camera) * SY;
    }

    /* بخشی از حلقه بین دو زاویه (رادیان، در بازه‌ی [lo, hi]) */
    function ringPiece(c, cx, cy, a0, a1, color) {
      c.fillStyle = color;
      c.beginPath();
      c.ellipse(cx, cy, R_OUT, R_OUT * TILT, 0, a0, a1);
      c.ellipse(cx, cy, R_IN, R_IN * TILT, 0, a1, a0, true);
      c.closePath();
      c.fill();
    }
    /* سکتور [start, start+size) را فقط در نیمه‌ی [lo, hi] می‌کشد */
    function sectorInHalf(c, cx, cy, start, size, lo, hi, color) {
      start = ((start % TWO_PI) + TWO_PI) % TWO_PI;
      var spans = start + size > TWO_PI ? [[start, TWO_PI], [0, start + size - TWO_PI]] : [[start, start + size]];
      for (var i = 0; i < spans.length; i++) {
        var a = Math.max(spans[i][0], lo), b = Math.min(spans[i][1], hi);
        if (b - a > 0.002) ringPiece(c, cx, cy, a, b, color);
      }
    }
    function drawFloorHalf(c, cx, cy, floor, rot, lo, hi, palette) {
      var rotRad = rot * RAD;
      if (!floor) {
        sectorInHalf(c, cx, cy, 0, TWO_PI - 0.0001, lo, hi, palette.base);
        return;
      }
      // کل حلقه به‌جز شکاف، سپس بخش‌های قرمز روی آن
      var gapEnd = (floor.gapStart + floor.gapSize) * RAD + rotRad;
      sectorInHalf(c, cx, cy, gapEnd, TWO_PI - floor.gapSize * RAD, lo, hi, lo === 0 ? palette.front : palette.back);
      for (var i = 0; i < floor.reds.length; i++) {
        var red = floor.reds[i];
        // بخش قرمزی که روی شکاف افتاده دیده نمی‌شود (شکاف اولویت دارد)
        var start = red[0], size = red[1];
        var intoGap = ((start - floor.gapStart) % core.CIRCLE + core.CIRCLE) % core.CIRCLE;
        if (intoGap < floor.gapSize) {
          var cut = floor.gapSize - intoGap;
          start += cut;
          size -= cut;
        }
        var toGap = ((floor.gapStart - start) % core.CIRCLE + core.CIRCLE) % core.CIRCLE;
        if (toGap < size) size = toGap;
        if (size > 0) sectorInHalf(c, cx, cy, start * RAD + rotRad, size * RAD, lo, hi, lo === 0 ? palette.red : palette.redBack);
      }
    }

    return {
      controls: "drag",
      reset: function (state) {
        camera = state.y - 1400;
        pendingDx = 0;
      },
      input: function (kind, data) {
        if (kind === "drag") pendingDx += data.dx;
        return null; // ورودی در sample و یک بار در هر تیک ثبت می‌شود
      },
      sample: function (state) {
        if (state.pause > 0) { pendingDx = 0; return null; }
        // کشیدن به راست، سطح جلوی برج را به راست می‌برد
        var turn = Math.round(-pendingDx * 600);
        pendingDx = 0;
        if (!turn) return null;
        return [Math.max(-core.MAX_TURN, Math.min(core.MAX_TURN, turn))];
      },
      hud: function (state) {
        if (!state) return "";
        var fire = state.streak >= core.FIRE_STREAK ? " · 🔥 آتشین" : "";
        return "مرحله " + env.fa(state.level + 1) + fire;
      },
      event: function (name, state) {
        var cx = env.W / 2, y = floorScreenY(state.floorIdx) - 20;
        if (name === "bounce") {
          squash = 1;
          env.sound("tick");
        } else if (name === "pass") {
          env.fx.text(cx + 60, y - 60, "+" + env.fa(state.streak), env.colors.gold);
          env.haptic("light");
          env.sound("good");
        } else if (name === "smash") {
          env.fx.burst(cx, y - 120, env.colors.gold, 30, 6);
          env.fx.shake(8);
          env.haptic("heavy");
          env.sound("bonus");
        } else if (name === "clear") {
          env.fx.burst(cx, y, env.colors.good, 40, 7);
          env.fx.flash(env.colors.good, 0.3);
          env.haptic("success");
          env.sound("clear");
        } else if (name === "fail") {
          env.fx.burst(cx, y, env.colors.danger, 30, 6);
          env.fx.flash(env.colors.danger, 0.5);
          env.fx.shake(14);
          env.haptic("error");
          env.sound("bad");
        }
      },
      draw: function (c, state, alpha) {
        var cx = env.W / 2;
        var ballY = state.y + (state.over || state.pause > 0 ? 0 : state.vy * alpha);
        camera += (ballY - 1400 - camera) * 0.14;
        var hue = (200 + state.level * 47) % 360;
        var palette = {
          front: "hsl(" + hue + ", 65%, 58%)",
          back: "hsl(" + hue + ", 45%, 34%)",
          red: env.colors.danger,
          redBack: "#8a3346",
          base: env.colors.gold,
        };
        var total = state.count + 1; // آخرین حلقه کف برج است
        var first = Math.max(1, Math.floor(camera / core.FLOOR_H));
        var last = Math.min(total, first + Math.ceil(env.H / (core.FLOOR_H * SY)) + 2);
        var ballDrawn = false;

        function drawBall() {
          squash *= 0.8;
          var by = env.safeTop + 120 + (ballY - camera) * SY + (R_OUT + R_IN) * 0.5 * TILT - 11;
          var fire = state.streak >= core.FIRE_STREAK;
          if (fire) {
            c.fillStyle = "rgba(255,184,77,.35)";
            c.beginPath();
            c.arc(cx, by, 20 + Math.sin(env.now() / 50) * 3, 0, TWO_PI);
            c.fill();
          }
          c.fillStyle = fire ? env.colors.gold : "#ffffff";
          env.glow(c, fire ? env.colors.gold : "#6ee7ff", 18);
          c.beginPath();
          c.ellipse(cx, by + squash * 3, 11 * (1 + squash * 0.25), 11 * (1 - squash * 0.25), 0, 0, TWO_PI);
          c.fill();
          env.glow(c);
        }

        // ستون مرکزی
        var colGrad = c.createLinearGradient(cx - R_IN, 0, cx + R_IN, 0);
        colGrad.addColorStop(0, "#3a4480");
        colGrad.addColorStop(0.5, "#262d5c");
        colGrad.addColorStop(1, "#171b3d");
        c.fillStyle = colGrad;
        c.fillRect(cx - R_IN, 0, R_IN * 2, env.H);
        c.fillStyle = "rgba(255,255,255,.06)";
        c.fillRect(cx - R_IN, 0, 10, env.H);

        // از پایین به بالا: نیمه‌ی پشتی، تکه‌ی ستون بالای آن، نیمه‌ی جلویی
        for (var k = last; k >= first; k--) {
          var floor = k <= state.count ? state.floors[k - 1] : null;
          var y = floorScreenY(k);
          if (floor && floor.broken) continue;
          drawFloorHalf(c, cx, y, floor, state.rot, Math.PI, TWO_PI, palette);
          c.fillStyle = colGrad;
          c.fillRect(cx - R_IN, y - core.FLOOR_H * SY, R_IN * 2, core.FLOOR_H * SY);
          c.fillStyle = "rgba(255,255,255,.06)";
          c.fillRect(cx - R_IN, y - core.FLOOR_H * SY, 10, core.FLOOR_H * SY);
          if (k === state.floorIdx - 1 && !ballDrawn) {
            // توپ زیر طبقه‌هایی است که از آن‌ها رد شده
            drawBall();
            ballDrawn = true;
          }
          drawFloorHalf(c, cx, y, floor, state.rot, 0, Math.PI, palette);
          // ضخامت لبه‌ی جلویی
          c.strokeStyle = "rgba(0,0,0,.25)";
          c.lineWidth = 3;
          c.beginPath();
          c.ellipse(cx, y + 2, R_OUT, R_OUT * TILT, 0, 0.05, Math.PI - 0.05);
          c.stroke();
        }
        if (!ballDrawn) drawBall();
      },
    };
  });
})();
