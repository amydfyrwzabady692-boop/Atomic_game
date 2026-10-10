/* «سیخ‌زن» — رندر و افکت‌ها. هیچ منطق بازی این‌جا نیست؛ فقط وضعیت core نمایش داده می‌شود. */
(function () {
  "use strict";
  Arcade.registerRenderer("pins", function (env) {
    var core = Arcade.cores.pins;
    var RAD = Math.PI / 180000; // واحد زاویه‌ی core → رادیان
    var R = 58, PIN = 74, HEAD = 7;
    var bump = 0;

    function center() {
      return { x: env.W / 2, y: env.safeTop + R + PIN + 18 };
    }

    function drawPin(c, cx, cy, angle, color, length) {
      var cos = Math.cos(angle), sin = Math.sin(angle);
      c.strokeStyle = color;
      c.fillStyle = color;
      c.lineWidth = 3;
      c.lineCap = "round";
      c.beginPath();
      c.moveTo(cx + cos * (R - 4), cy + sin * (R - 4));
      c.lineTo(cx + cos * (R + length), cy + sin * (R + length));
      c.stroke();
      c.beginPath();
      c.arc(cx + cos * (R + length), cy + sin * (R + length), HEAD, 0, 6.2832);
      c.fill();
    }

    return {
      controls: "tap",

      input: function (kind) {
        return kind === "tap" ? [] : null;
      },

      hud: function (state) {
        if (!state) return "";
        return "مرحله " + env.fa(state.level + 1) + (state.lv && state.lv.boss ? " · باس 👹" : "");
      },

      event: function (name, state) {
        var c = center();
        if (name === "throw") env.sound("tick");
        else if (name === "stick") {
          bump = 1;
          env.fx.shake(3);
          env.haptic("light");
          env.sound("tap");
        } else if (name === "clear") {
          env.fx.burst(c.x, c.y, env.colors.good, 34, 6);
          env.fx.burst(c.x, c.y, env.colors.gold, 22, 4);
          env.fx.flash(env.colors.good, 0.25);
          env.fx.text(c.x, c.y - R - PIN - 6, "مرحله " + env.fa(state.level) + " ✓", env.colors.good);
          env.haptic("success");
          env.sound("clear");
        } else if (name === "fail") {
          env.fx.flash(env.colors.danger, 0.55);
          env.fx.shake(16);
          env.fx.burst(c.x, c.y + R + PIN, env.colors.danger, 18, 4);
          env.haptic("error");
          env.sound("bad");
        }
      },

      draw: function (c, state, alpha) {
        var p = center();
        var lv = state.lv;
        var boss = lv && lv.boss;
        var main = boss ? env.colors.gold : env.colors.accent;
        var angle = state.angle;
        if (!state.over && state.pause === 0) angle += core.speedAt(lv, state.ltick) * alpha;
        var rot = angle * RAD;
        bump *= 0.82;

        // هنگام تمام شدن مرحله، دایره باز می‌شود و محو می‌شود
        var breaking = state.pause > 0 ? 1 - state.pause / core.PAUSE_TICKS : 0;
        c.save();
        c.globalAlpha = 1 - breaking;
        var spread = breaking * 46;

        for (var i = 0; i < state.pins.length; i++) {
          drawPin(c, p.x, p.y, state.pins[i] * RAD + rot, env.colors.ink, PIN + spread);
        }
        if (state.over && state.hitAngle !== undefined) {
          drawPin(c, p.x, p.y, core.BOTTOM * RAD, env.colors.danger, PIN + 10);
        }

        var r = R + bump * 4 + breaking * 20;
        // هاله‌ی دور دایره
        c.strokeStyle = "rgba(255,255,255,.07)";
        c.lineWidth = 1.5;
        c.beginPath();
        c.arc(p.x, p.y, R + PIN + HEAD + 6, 0, 6.2832);
        c.stroke();
        env.glow(c, main, 26);
        var gradient = c.createRadialGradient(p.x - 16, p.y - 18, 6, p.x, p.y, r);
        gradient.addColorStop(0, main);
        gradient.addColorStop(1, boss ? env.colors.danger : env.colors.violet);
        c.fillStyle = gradient;
        c.beginPath();
        c.arc(p.x, p.y, r, 0, 6.2832);
        c.fill();
        env.glow(c);
        // نشانه‌ی چرخش روی دایره
        c.strokeStyle = "rgba(255,255,255,.28)";
        c.lineWidth = 3;
        c.beginPath();
        c.arc(p.x, p.y, r - 12, rot, rot + 1.1);
        c.stroke();
        c.restore();

        c.fillStyle = "#0d1324";
        c.textAlign = "center";
        c.textBaseline = "middle";
        c.font = env.font(34, 900);
        c.fillText(env.fa(Math.max(state.remaining, 0)), p.x, p.y + 2);
        c.textBaseline = "alphabetic";

        // سیخ‌های در حال پرواز
        var bottomY = p.y + R + PIN;
        var queueY = Math.min(env.H - 150, bottomY + 150);
        for (var f = 0; f < state.flights.length; f++) {
          var left = state.flights[f] - (state.tick + alpha);
          var t = 1 - Math.max(0, Math.min(1, left / core.FLIGHT_TICKS));
          var y = queueY + (bottomY - queueY) * t;
          c.strokeStyle = env.colors.ink;
          c.fillStyle = env.colors.ink;
          c.lineWidth = 3;
          c.beginPath();
          c.moveTo(p.x, y - PIN);
          c.lineTo(p.x, y);
          c.stroke();
          c.beginPath();
          c.arc(p.x, y, HEAD, 0, 6.2832);
          c.fill();
        }

        // صف سیخ‌های آماده پایین صفحه
        var waiting = Math.max(0, state.remaining - state.flights.length);
        var shown = Math.min(waiting, 6);
        for (var q = 0; q < shown; q++) {
          var qy = queueY + q * 26;
          if (qy > env.H - 24) break;
          c.globalAlpha = 1 - q * 0.14;
          c.fillStyle = q === 0 ? main : env.colors.muted;
          env.glow(c, q === 0 ? main : null, 12);
          c.beginPath();
          c.arc(p.x, qy, HEAD + (q === 0 ? 2 : 0), 0, 6.2832);
          c.fill();
        }
        env.glow(c);
        c.globalAlpha = 1;
      },
    };
  });
})();
