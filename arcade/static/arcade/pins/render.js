/* «سیخ‌زن» — رندر و افکت‌ها: کنده‌ی چوبی چرخان روی دیوار تخته‌ای و چاقوهای فلزی که در آن فرو می‌روند.
   هیچ منطق بازی این‌جا نیست؛ فقط وضعیت core نمایش داده می‌شود. */
(function () {
  "use strict";
  Arcade.registerRenderer("pins", function (env) {
    var core = Arcade.cores.pins, art = env.art;
    var RAD = Math.PI / 180000; // واحد زاویه‌ی core → رادیان
    var TAU = Math.PI * 2;
    var R = 64, EMBED = 12, KNIFE_L = 70, KNIFE_W = 16;
    var bump = 0, failAt = 0, failSide = 1;
    var stuckAt = 0, stuckIndex = -1;

    function center() {
      return { x: env.W / 2, y: env.safeTop + R + KNIFE_L + 6 };
    }
    function readyTip(p) {
      return Math.min(env.H - 150, p.y + R + 170);
    }

    // ---------------------------------------------------------------- اسپرایت‌ها
    function paintScene(c, w, h, b) {
      // دیوار تخته‌ای
      var plank = 62, i = 0;
      for (var x = -b; x < w + b; x += plank, i++) {
        var tone = ["#3a2415", "#422a18", "#352012", "#3e2616"][i % 4];
        art.wood(c, x, -b, plank, h + b * 2, { base: tone, seed: 20 + i, knots: 2 });
        c.fillStyle = "rgba(0,0,0,.45)";
        c.fillRect(x, -b, 1.6, h + b * 2);
        c.fillStyle = "rgba(255,220,170,.05)";
        c.fillRect(x + 1.6, -b, 1, h + b * 2);
      }
      art.grain(c, -b, -b, w + b * 2, h + b * 2, 0.22);
      // نور گرم روی هدف
      var p = center();
      var light = c.createRadialGradient(p.x, p.y - 20, 20, p.x, p.y, 300);
      light.addColorStop(0, "rgba(255,206,140,.34)");
      light.addColorStop(0.5, "rgba(255,180,110,.1)");
      light.addColorStop(1, "rgba(255,180,110,0)");
      c.fillStyle = light;
      c.fillRect(-b, -b, w + b * 2, h + b * 2);
      // سایه‌ی کنده روی دیوار
      art.shadow(c, p.x + 6, p.y + 12, R * 1.5, R * 1.5, 0.5);
      art.vignette(c, w, h, 0.72);
    }

    function paintLog(boss) {
      return function (c) {
        env.dropShadow(c, 7, 5, 0.5);
        c.fillStyle = "#2b170b";
        c.beginPath();
        c.arc(R, R, R - 1, 0, TAU);
        c.fill();
        env.dropShadow(c);
        art.logSlice(c, R, R, R, boss ? { base: "#8a5a3a", bark: "#24140c", seed: 9 } : { base: "#cf9a60", bark: "#4d2e18", seed: 3 });
        if (boss) {
          // طوق آهنی و پرچ‌ها
          var band = c.createLinearGradient(0, 0, R * 2, R * 2);
          band.addColorStop(0, "#e2e8f2");
          band.addColorStop(0.5, "#5e6878");
          band.addColorStop(1, "#b9c2d0");
          c.strokeStyle = band;
          c.lineWidth = 7;
          c.beginPath();
          c.arc(R, R, R * 0.82, 0, TAU);
          c.stroke();
          c.strokeStyle = "rgba(0,0,0,.45)";
          c.lineWidth = 1;
          c.beginPath();
          c.arc(R, R, R * 0.82 + 3.5, 0, TAU);
          c.arc(R, R, R * 0.82 - 3.5, 0, TAU);
          c.stroke();
          for (var i = 0; i < 8; i++) {
            var a = (i / 8) * TAU;
            art.sphere(c, R + Math.cos(a) * R * 0.82, R + Math.sin(a) * R * 0.82, 2.6, "#aab4c4", false);
          }
        }
      };
    }

    /* نور ثابت صحنه روی کنده (نمی‌چرخد) */
    function paintLight(c) {
      c.beginPath();
      c.arc(R, R, R, 0, TAU);
      c.clip();
      var hi = c.createRadialGradient(R * 0.55, R * 0.45, 2, R * 0.55, R * 0.45, R * 1.1);
      hi.addColorStop(0, "rgba(255,244,220,.3)");
      hi.addColorStop(1, "rgba(255,244,220,0)");
      c.fillStyle = hi;
      c.fillRect(0, 0, R * 2, R * 2);
      var lo = c.createRadialGradient(R, R, R * 0.55, R * 1.1, R * 1.15, R * 1.25);
      lo.addColorStop(0, "rgba(0,0,0,0)");
      lo.addColorStop(1, "rgba(0,0,0,.42)");
      c.fillStyle = lo;
      c.fillRect(0, 0, R * 2, R * 2);
    }

    function paintHub(boss) {
      return function (c) {
        env.dropShadow(c, 3, 2, 0.55);
        var color = boss ? "#b9c2d0" : "#d9a441";
        art.sphere(c, 19, 19, 18, color, false);
        env.dropShadow(c);
        c.strokeStyle = art.shade(color, -0.5);
        c.lineWidth = 1.2;
        c.beginPath();
        c.arc(19, 19, 17.4, 0, TAU);
        c.stroke();
        c.strokeStyle = "rgba(255,255,255,.4)";
        c.beginPath();
        c.arc(19, 19, 13.5, 0, TAU);
        c.stroke();
      };
    }

    /* چاقو رو به بالا: نوک در y=0 */
    function paintKnife(danger) {
      return function (c) {
        var m = KNIFE_W / 2;
        env.dropShadow(c, 2.5, 2, 0.45);
        // تیغه
        var blade = c.createLinearGradient(m - 5, 0, m + 5, 0);
        blade.addColorStop(0, danger ? "#ffd0d6" : "#f4f7fb");
        blade.addColorStop(0.48, danger ? "#ff8795" : "#c2cad6");
        blade.addColorStop(0.52, danger ? "#e0495d" : "#8d97a6");
        blade.addColorStop(1, danger ? "#a8283a" : "#5b6472");
        c.fillStyle = blade;
        c.beginPath();
        c.moveTo(m, 0);
        c.quadraticCurveTo(m + 5.2, 9, m + 4.6, 18);
        c.lineTo(m + 4.6, 35);
        c.lineTo(m - 4.6, 35);
        c.lineTo(m - 4.6, 18);
        c.quadraticCurveTo(m - 5.2, 9, m, 0);
        c.closePath();
        c.fill();
        env.dropShadow(c);
        c.strokeStyle = "rgba(255,255,255,.75)";
        c.lineWidth = 0.8;
        c.beginPath();
        c.moveTo(m - 3.6, 33);
        c.lineTo(m - 3.6, 17);
        c.quadraticCurveTo(m - 4, 9, m - 0.4, 2);
        c.stroke();
        // محافظ برنجی
        art.bevel(c, m - 7.5, 34, 15, 4.5, 2, "#d9a441");
        // دسته با نوارپیچ
        var grip = c.createLinearGradient(m - 4.5, 0, m + 4.5, 0);
        grip.addColorStop(0, "#7a2c22");
        grip.addColorStop(0.4, "#b8483a");
        grip.addColorStop(1, "#4a1712");
        c.fillStyle = grip;
        art.rr(c, m - 4.5, 38, 9, 26, 3);
        c.fill();
        c.strokeStyle = "rgba(0,0,0,.35)";
        c.lineWidth = 1;
        for (var y = 42; y < 62; y += 4.5) {
          c.beginPath();
          c.moveTo(m - 4.5, y + 1.5);
          c.lineTo(m + 4.5, y - 1.5);
          c.stroke();
        }
        art.sphere(c, m, 66, 4.6, "#d9a441");
      };
    }

    function knife(c, x, y, rot, danger, scale) {
      var sp = env.sprite(danger ? "pins:knifeRed" : "pins:knife", KNIFE_W, KNIFE_L, paintKnife(danger), 6);
      env.blitC(c, sp, x, y, rot, scale);
    }
    /* چاقوی فرورفته در کنده در زاویه‌ی theta (رادیان) */
    function stuck(c, px, py, theta, out, spin, danger) {
      var d = R - EMBED + KNIFE_L / 2 + out;
      knife(c, px + Math.cos(theta) * d, py + Math.sin(theta) * d, theta - Math.PI / 2 + spin, danger);
    }

    return {
      controls: "tap",
      ownBackground: true,

      reset: function () {
        bump = 0;
        failAt = 0;
        stuckIndex = -1;
      },

      input: function (kind) {
        return kind === "tap" ? [] : null;
      },

      hud: function (state) {
        if (!state) return "";
        return "مرحله " + env.fa(state.level + 1) + (state.lv && state.lv.boss ? " · باس 👹" : "");
      },

      event: function (name, state) {
        var p = center();
        if (name === "throw") env.sound("tick");
        else if (name === "stick") {
          bump = 1;
          stuckAt = env.now();
          stuckIndex = state.pins.length - 1;
          env.fx.debris(p.x, p.y + R - 4, "#e2b57e", 5, 2.2, 2.6);
          env.fx.shake(2.5);
          env.haptic("light");
          env.sound("tap");
        } else if (name === "clear") {
          env.fx.debris(p.x, p.y, "#c8935a", 22, 6, 5);
          env.fx.debris(p.x, p.y, "#4d2e18", 10, 5, 4);
          env.fx.burst(p.x, p.y, env.colors.gold, 26, 5);
          env.fx.ring(p.x, p.y, "#ffe9b0", R * 0.6, R * 2.2);
          env.fx.flash("#ffe9b0", 0.22);
          env.fx.text(p.x, p.y + R + 46, "مرحله " + env.fa(state.level) + " ✓", env.colors.good);
          env.haptic("success");
          env.sound("clear");
        } else if (name === "fail") {
          failAt = env.now();
          failSide = Math.random() < 0.5 ? -1 : 1;
          env.fx.flash(env.colors.danger, 0.5);
          env.fx.shake(10);
          env.fx.burst(p.x, p.y + R, "#fff2c2", 16, 4.5);
          env.haptic("error");
          env.sound("bad");
        }
      },

      draw: function (c, state, alpha) {
        var p = center();
        var lv = state.lv;
        var boss = !!(lv && lv.boss);
        var angle = state.angle;
        if (!state.over && state.pause === 0) angle += core.speedAt(lv, state.ltick) * alpha;
        var rot = angle * RAD;
        bump *= 0.8;
        env.scene(c, "pins", paintScene);
        var now = env.now();
        // ذره‌های غبار معلق در نور
        c.fillStyle = "#ffe9c4";
        for (var mote = 0; mote < 14; mote++) {
          var mx = p.x + Math.sin(now / 2300 + mote * 2.1) * (60 + mote * 9);
          var my = p.y - 120 + ((now / (46 + mote * 3) + mote * 61) % 330);
          c.globalAlpha = 0.1 + 0.16 * (0.5 + 0.5 * Math.sin(now / 700 + mote));
          c.fillRect(mx, my, 1.6, 1.6);
        }
        c.globalAlpha = 1;
        // کنده‌ی مرحله‌ی تازه از بالا پایین می‌آید
        var intro = state.pause === 0 && !state.over ? env.clamp(state.ltick / 16, 0, 1) : 1;
        var drop = (1 - intro) * (1 - intro) * 46;

        // هنگام تمام شدن مرحله کنده چهار تکه می‌شود و چاقوها بیرون می‌پرند
        var breaking = state.pause > 0 ? env.clamp(1 - (state.pause - alpha) / core.PAUSE_TICKS, 0, 1) : 0;
        var fade = (1 - breaking * breaking) * intro;
        var cy = p.y - bump * 5 - drop;
        var i;

        c.globalAlpha = fade;
        for (i = 0; i < state.pins.length; i++) {
          // چاقوی تازه‌فرورفته چند لحظه می‌لرزد
          var wobble = i === stuckIndex ? Math.sin((now - stuckAt) / 22) * Math.exp(-(now - stuckAt) / 150) * 0.16 : 0;
          stuck(c, p.x, cy + breaking * breaking * 60, state.pins[i] * RAD + rot, breaking * 110, breaking * (i % 2 ? 4 : -4) + wobble, false);
        }
        c.globalAlpha = 1;

        var log = env.sprite(boss ? "pins:boss" : "pins:log", R * 2, R * 2, paintLog(boss), 16);
        if (breaking > 0) {
          for (i = 0; i < 4; i++) {
            var mid = rot + (i + 0.5) * (Math.PI / 2);
            c.save();
            c.globalAlpha = fade;
            c.translate(p.x + Math.cos(mid) * breaking * 70, cy + Math.sin(mid) * breaking * 70 + breaking * breaking * 90);
            c.rotate(rot + breaking * (i % 2 ? 0.9 : -0.9));
            c.beginPath();
            c.moveTo(0, 0);
            c.arc(0, 0, R + 4, i * (Math.PI / 2), (i + 1) * (Math.PI / 2));
            c.closePath();
            c.clip();
            c.drawImage(log.canvas, -log.fw / 2, -log.fh / 2, log.fw, log.fh);
            c.restore();
          }
        } else {
          c.globalAlpha = intro;
          env.blitC(c, log, p.x, cy, rot);
          env.blit(c, env.sprite("pins:light", R * 2, R * 2, paintLight), p.x - R, cy - R);
          env.blitC(c, env.sprite(boss ? "pins:hubBoss" : "pins:hub", 38, 38, paintHub(boss), 6), p.x, cy);
          c.fillStyle = boss ? "#1c2230" : "#4a2f0a";
          c.textAlign = "center";
          c.textBaseline = "middle";
          c.font = env.font(20, 900);
          c.fillText(env.fa(Math.max(state.remaining, 0)), p.x, cy + 1.5);
          c.textBaseline = "alphabetic";
          c.globalAlpha = 1;
        }

        // چاقویی که به چاقوی دیگر خورده و کمانه می‌کند
        if (state.over && state.hitAngle !== undefined) {
          var t = failAt ? Math.min(1.4, (env.now() - failAt) / 600) : 1.4;
          knife(c, p.x + failSide * t * 46, cy + R - EMBED + KNIFE_L / 2 + 8 + t * t * 240, failSide * t * 5.5, true);
        }

        // چاقوهای در حال پرواز
        var landTip = cy + R - EMBED;
        var ready = readyTip(p);
        for (i = 0; i < state.flights.length; i++) {
          var left = state.flights[i] - (state.tick + alpha);
          var f = 1 - env.clamp(left / core.FLIGHT_TICKS, 0, 1);
          var tip = ready + (landTip - ready) * f;
          c.globalAlpha = 0.25;
          knife(c, p.x, tip + KNIFE_L / 2 + 16, 0, false);
          c.globalAlpha = 1;
          knife(c, p.x, tip + KNIFE_L / 2, 0, false);
        }

        // چاقوی آماده و شمارنده‌ی چاقوهای مانده
        var waiting = Math.max(0, state.remaining - state.flights.length);
        if (waiting > 0 && !state.over && state.pause === 0) {
          art.shadow(c, p.x + 3, ready + KNIFE_L + 4, 16, 5, 0.5);
          knife(c, p.x, ready + KNIFE_L / 2 + Math.sin(env.now() / 260) * 1.5, 0, false);
        }
        var total = lv ? lv.pins : 0;
        var shown = Math.min(total, 14);
        var colY = env.H - 34;
        for (i = 0; i < shown; i++) {
          c.globalAlpha = i < waiting ? 1 : 0.22;
          knife(c, 26, colY - i * 17, Math.PI / 2, false, 0.42);
        }
        c.globalAlpha = 1;
      },
    };
  });
})();
