/* «پرنده‌ی پرشی» — رندر و افکت‌ها: آسمان عصرگاهی با کوه و تپه‌های پارالاکس، لوله‌های فلزی حجم‌دار،
   زمین چمنی متحرک و پرنده‌ای با سه حالت بال. همه‌ی لایه‌ها اسپرایت کش‌شده‌اند. */
(function () {
  "use strict";
  Arcade.registerRenderer("flappy", function (env) {
    var core = Arcade.cores.flappy, art = env.art;
    var TAU = Math.PI * 2;
    var wing = 0;
    var scroll = 0, lastTick = 0;
    var feathers = [];
    var failAt = 0, failY = 0;

    function groundH() {
      return env.clamp(env.H - 640 + 14, 14, 46);
    }
    function layout() {
      var scale = Math.min(env.W / core.FIELD_W, env.H / core.FIELD_H);
      // کف منطقی زمین (پایین FIELD_H) دقیقاً روی لبه‌ی بالایی چمن می‌افتد
      return { s: scale, ox: (env.W - core.FIELD_W * scale) / 2, oy: env.H - groundH() - core.FIELD_H * scale };
    }

    // ---------------------------------------------------------------- اسپرایت‌ها
    function paintSky(c, w, h) {
      var g = c.createLinearGradient(0, 0, 0, h);
      g.addColorStop(0, "#2f6fc4");
      g.addColorStop(0.55, "#7fc0ea");
      g.addColorStop(0.85, "#ffd9a8");
      g.addColorStop(1, "#ffb98a");
      c.fillStyle = g;
      c.fillRect(-1, -1, w + 2, h + 2);
    }
    /* نوار کوه با دوره‌ی تکرار برابر عرض صفحه (بی‌درز) */
    function paintMountains(c, w, h) {
      for (var layer = 0; layer < 2; layer++) {
        var base = layer ? "#5f7fa8" : "#8fa9c9";
        var g = c.createLinearGradient(0, 0, 0, h);
        g.addColorStop(0, art.shade(base, 0.25));
        g.addColorStop(1, base);
        c.fillStyle = g;
        c.beginPath();
        c.moveTo(0, h);
        for (var x = 0; x <= w; x += 6) {
          var a = (x / env.W) * TAU;
          var y = layer
            ? 0.55 + 0.2 * Math.sin(a * 2 + 1) + 0.12 * Math.sin(a * 5 + 2) + 0.05 * Math.sin(a * 11)
            : 0.3 + 0.18 * Math.sin(a * 3) + 0.1 * Math.sin(a * 7 + 1) + 0.04 * Math.sin(a * 13 + 2);
          c.lineTo(x, h * env.clamp(y, 0.05, 0.95));
        }
        c.lineTo(w, h);
        c.closePath();
        c.fill();
      }
    }
    /* تپه‌های سبز با درخت؛ بی‌درز */
    function paintHills(c, w, h) {
      var g = c.createLinearGradient(0, 0, 0, h);
      g.addColorStop(0, "#5aa85a");
      g.addColorStop(1, "#2f7a45");
      c.fillStyle = g;
      c.beginPath();
      c.moveTo(0, h);
      for (var x = 0; x <= w; x += 6) {
        var a = (x / env.W) * TAU;
        c.lineTo(x, h * (0.5 + 0.16 * Math.sin(a * 2 + 0.5) + 0.07 * Math.sin(a * 5 + 1.3)));
      }
      c.lineTo(w, h);
      c.closePath();
      c.fill();
      var rnd = art.rand(15);
      for (var i = 0; i < 9; i++) {
        var tx = rnd() * env.W, ta = (tx / env.W) * TAU;
        var ty = h * (0.5 + 0.16 * Math.sin(ta * 2 + 0.5) + 0.07 * Math.sin(ta * 5 + 1.3)) + 3;
        var size = 9 + rnd() * 8;
        for (var copy = -1; copy <= 1; copy++) {
          var px = tx + copy * env.W;
          c.fillStyle = "#5a3a1c";
          c.fillRect(px - 1.2, ty - size * 0.5, 2.4, size * 0.5);
          art.sphere(c, px, ty - size * 0.9, size * 0.62, "#3f9a4c", false);
          art.sphere(c, px - size * 0.4, ty - size * 0.55, size * 0.45, "#358a45", false);
          art.sphere(c, px + size * 0.4, ty - size * 0.6, size * 0.42, "#44a352", false);
        }
      }
    }
    function paintGround(c, w, h) {
      var dirt = c.createLinearGradient(0, 0, 0, h);
      dirt.addColorStop(0, "#c68d4f");
      dirt.addColorStop(1, "#7d5228");
      c.fillStyle = dirt;
      c.fillRect(0, 0, w, h + 1);
      c.fillStyle = "rgba(60,30,8,.22)";
      for (var x = -h; x < w + h; x += 24) {
        c.beginPath();
        c.moveTo(x, h);
        c.lineTo(x + 10, h);
        c.lineTo(x + 10 + h * 0.6, 8);
        c.lineTo(x + h * 0.6, 8);
        c.closePath();
        c.fill();
      }
      var grass = c.createLinearGradient(0, 0, 0, 10);
      grass.addColorStop(0, "#8fe06a");
      grass.addColorStop(1, "#3f9a3a");
      c.fillStyle = grass;
      c.fillRect(0, 0, w, 9);
      c.fillStyle = "#2f7a2f";
      for (var gx = 0; gx < w; gx += 12) {
        c.beginPath();
        c.moveTo(gx, 9);
        c.lineTo(gx + 6, 13.5);
        c.lineTo(gx + 12, 9);
        c.closePath();
        c.fill();
      }
      c.fillStyle = "rgba(255,255,255,.45)";
      c.fillRect(0, 0, w, 1.2);
    }
    function paintPipeBody(c, w, h) {
      var g = c.createLinearGradient(0, 0, w, 0);
      g.addColorStop(0, "#1f6b33");
      g.addColorStop(0.12, "#3fae55");
      g.addColorStop(0.3, "#a6efaa");
      g.addColorStop(0.45, "#55c468");
      g.addColorStop(0.8, "#2c8a42");
      g.addColorStop(1, "#145226");
      c.fillStyle = g;
      c.fillRect(0, -1, w, h + 2);
    }
    function paintPipeCap(c, w, h) {
      env.dropShadow(c, 3, 2, 0.4);
      var g = c.createLinearGradient(0, 0, w, 0);
      g.addColorStop(0, "#1f6b33");
      g.addColorStop(0.12, "#45b75b");
      g.addColorStop(0.3, "#c2f7c4");
      g.addColorStop(0.45, "#5fcf72");
      g.addColorStop(0.8, "#2c8a42");
      g.addColorStop(1, "#124a22");
      c.fillStyle = g;
      art.rr(c, 0, 0, w, h, 5);
      c.fill();
      env.dropShadow(c);
      c.strokeStyle = "rgba(10,50,20,.7)";
      c.lineWidth = 1.2;
      c.stroke();
      c.fillStyle = "rgba(255,255,255,.4)";
      c.fillRect(4, 2, w - 8, 1.6);
      c.fillStyle = "rgba(0,0,0,.25)";
      c.fillRect(2, h - 4, w - 4, 2.4);
    }

    /* پرنده رو به راست؛ pose: ۰ بال بالا، ۱ وسط، ۲ پایین */
    function paintBird(r, pose) {
      return function (c) {
        c.translate(r * 2, r * 1.7);
        // دم
        c.fillStyle = "#e07b1a";
        for (var i = -1; i <= 1; i++) {
          c.beginPath();
          c.ellipse(-r * 1.15, i * r * 0.26, r * 0.5, r * 0.16, i * 0.35, 0, TAU);
          c.fill();
        }
        // بدن
        var body = c.createRadialGradient(-r * 0.3, -r * 0.45, r * 0.1, 0, 0, r * 1.1);
        body.addColorStop(0, "#fff6c9");
        body.addColorStop(0.45, "#ffd23f");
        body.addColorStop(1, "#f08a1c");
        c.fillStyle = body;
        c.beginPath();
        c.ellipse(0, 0, r * 1.05, r * 0.92, 0, 0, TAU);
        c.fill();
        c.strokeStyle = "rgba(150,70,0,.5)";
        c.lineWidth = 1;
        c.stroke();
        // شکم
        c.fillStyle = "rgba(255,250,225,.75)";
        c.beginPath();
        c.ellipse(r * 0.15, r * 0.4, r * 0.6, r * 0.4, 0, 0, TAU);
        c.fill();
        // بال
        var wy = [-r * 0.45, r * 0.05, r * 0.5][pose];
        var wingGrad = c.createLinearGradient(0, wy - r * 0.4, 0, wy + r * 0.4);
        wingGrad.addColorStop(0, "#ffe38a");
        wingGrad.addColorStop(1, "#e88a1a");
        c.fillStyle = wingGrad;
        c.beginPath();
        c.ellipse(-r * 0.3, wy, r * 0.55, r * (pose === 1 ? 0.24 : 0.4), pose === 0 ? 0.5 : pose === 2 ? -0.5 : 0, 0, TAU);
        c.fill();
        c.strokeStyle = "rgba(150,70,0,.45)";
        c.stroke();
        // چشم
        c.fillStyle = "#ffffff";
        c.beginPath();
        c.arc(r * 0.45, -r * 0.3, r * 0.32, 0, TAU);
        c.fill();
        c.fillStyle = "#1b1f3a";
        c.beginPath();
        c.arc(r * 0.55, -r * 0.28, r * 0.15, 0, TAU);
        c.fill();
        c.fillStyle = "#ffffff";
        c.beginPath();
        c.arc(r * 0.5, -r * 0.34, r * 0.06, 0, TAU);
        c.fill();
        // نوک
        c.fillStyle = "#ff6a3d";
        c.beginPath();
        c.moveTo(r * 0.8, -r * 0.12);
        c.quadraticCurveTo(r * 1.5, -r * 0.05, r * 1.55, r * 0.12);
        c.lineTo(r * 0.8, r * 0.14);
        c.closePath();
        c.fill();
        c.fillStyle = "#d94a22";
        c.beginPath();
        c.moveTo(r * 0.8, r * 0.14);
        c.lineTo(r * 1.45, r * 0.16);
        c.lineTo(r * 0.85, r * 0.36);
        c.closePath();
        c.fill();
      };
    }

    function strip(c, sp, offset, y) {
      var x = -(((offset % env.W) + env.W) % env.W);
      c.drawImage(sp.canvas, x, y, sp.w, sp.h);
      c.drawImage(sp.canvas, x + env.W, y, sp.w, sp.h);
    }

    function pipe(c, body, cap, x, y, w, h, capAtBottom) {
      if (h <= 0) return;
      c.drawImage(body.canvas, x, y, w, h);
      env.blit(c, cap, x - 5, capAtBottom ? y + h - 24 : y);
    }

    return {
      controls: "tap",
      ownBackground: true,
      reset: function (state) {
        feathers = [];
        scroll = 0;
        lastTick = state.tick;
        failAt = 0;
      },
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
          env.fx.text(bx + 34, by - 28, "+۱", env.colors.gold);
          env.haptic("light");
          env.sound("good");
        } else if (name === "fail") {
          failAt = env.now();
          failY = by;
          for (var i = 0; i < 9; i++) {
            feathers.push({ x: bx, y: by, vx: (Math.random() - 0.5) * 7, vy: -Math.random() * 6, rot: Math.random() * 6, life: 1 });
          }
          env.fx.burst(bx, by, "#fff2b8", 18, 4.5);
          env.fx.flash("#ffffff", 0.45);
          env.fx.shake(9);
          env.haptic("error");
          env.sound("bad");
        }
      },
      draw: function (c, state, alpha) {
        var l = layout(), s = l.s, W = env.W, H = env.H;
        var moving = state.started && !state.over;
        var speed = moving ? core.speedFor(state.score) : 0;
        // اسکرول پس‌زمینه بر اساس زمان بازی (مستقل از نرخ فریم)
        var tickNow = state.tick + (moving ? alpha : 0);
        if (moving) scroll += Math.max(0, tickNow - lastTick) * speed * s;
        lastTick = tickNow;
        var gh = groundH(), groundY = H - gh;

        c.drawImage(env.sprite("flappy:sky", 4, H, paintSky).canvas, -12, -12, W + 24, H + 24);
        // نوارها ۶ پیکسل پهن‌تر از دوره‌ی تکرارند تا محل اتصال دو نسخه درز نیندازد
        strip(c, env.sprite("flappy:mountains", W + 6, 170, paintMountains), scroll * 0.08, groundY - 215);
        strip(c, env.sprite("flappy:hills", W + 6, 110, paintHills), scroll * 0.3, groundY - 108);

        // لوله‌ها
        var body = env.sprite("flappy:pipe", core.PIPE_W * s, 8, paintPipeBody);
        var cap = env.sprite("flappy:cap", core.PIPE_W * s + 10, 24, paintPipeCap, 6);
        for (var i = 0; i < state.pipes.length; i++) {
          var p = state.pipes[i];
          var x = l.ox + (p.x - speed * alpha) * s, w = core.PIPE_W * s;
          var top = l.oy + p.gapY * s, bottom = l.oy + (p.gapY + p.gapH) * s;
          pipe(c, body, cap, x, -12, w, top + 12, true);
          pipe(c, body, cap, x, bottom, w, groundY - bottom + 2, false);
        }

        // زمین متحرک (هم‌سرعت با لوله‌ها)
        var ground = env.sprite("flappy:ground", W + 48, 46, paintGround);
        c.drawImage(ground.canvas, -(((scroll % 24) + 24) % 24) - 12, groundY, ground.w, ground.h);

        // پرنده
        var vy = state.vy;
        var by = l.oy + (state.y + (moving ? vy * alpha : 0)) * s;
        if (!state.started) by += Math.sin(env.now() / 220) * 5;
        var bx = l.ox + core.BIRD_X * s, r = core.RADIUS * s;
        wing *= 0.9;
        var pose = state.started ? (wing > 0.6 ? 2 : wing > 0.25 ? 1 : 0) : Math.floor(env.now() / 120) % 3;
        var tilt = Math.max(-0.45, Math.min(1.1, vy / 170));
        if (state.over && failAt) {
          // سقوط چرخان بعد از برخورد
          var t = Math.min(1.2, (env.now() - failAt) / 700);
          by = Math.min(groundY - r, failY + t * t * 380);
          tilt = 1.1 + t * 5;
          pose = 1;
        }
        art.shadow(c, bx, groundY + 3, r * (1.2 - Math.min(0.7, (groundY - by) / 700)), 3.5, 0.3);
        env.blitC(c, env.sprite("flappy:bird:" + pose, r * 4, r * 3.4, paintBird(r, pose), 2), bx, by, tilt);

        // پرهای ریخته بعد از برخورد
        for (var f = feathers.length - 1; f >= 0; f--) {
          var fe = feathers[f];
          fe.x += fe.vx;
          fe.y += fe.vy;
          fe.vy += 0.25;
          fe.rot += 0.12;
          fe.life -= 0.018;
          if (fe.life <= 0) { feathers.splice(f, 1); continue; }
          c.save();
          c.globalAlpha = fe.life;
          c.translate(fe.x, fe.y);
          c.rotate(fe.rot);
          c.fillStyle = "#ffd23f";
          c.beginPath();
          c.ellipse(0, 0, 9, 3.5, 0, 0, TAU);
          c.fill();
          c.restore();
        }
        c.globalAlpha = 1;
      },
    };
  });
})();
