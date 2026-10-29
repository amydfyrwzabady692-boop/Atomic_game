/* «پرش ابرها» — رندر و افکت‌ها: آسمانی که با بالا رفتن از آبی روز به شب پرستاره می‌رسد، ابرهای حجیم
   سه‌نوع (سفید عادی، آبی متحرک، خاکستری طوفانیِ شکننده)، بالن و پرنده در ارتفاع کم، ماه در ارتفاع زیاد
   و شخصیتی که پلک می‌زند، پاهایش را جمع می‌کند و شال‌گردنش در باد تکان می‌خورد. */
(function () {
  "use strict";
  Arcade.registerRenderer("jumper", function (env) {
    var core = Arcade.cores.jumper, art = env.art;
    var TAU = Math.PI * 2;
    var S = 0.1;
    var PW = core.PLAT_W * S;
    var CLOUD_W = PW + 14, CLOUD_H = CLOUD_W * 0.5;
    var camera = -core.VIEW_BELOW;
    var squash = 0;
    var trail = [];

    function screenY(worldY) {
      return env.H - 70 - (worldY - camera) * S * (env.H / 640);
    }

    // ---------------------------------------------------------------- اسپرایت‌ها
    function sky(top, bottom) {
      return function (c, w, h) {
        var g = c.createLinearGradient(0, 0, 0, h);
        g.addColorStop(0, top);
        g.addColorStop(1, bottom);
        c.fillStyle = g;
        c.fillRect(-1, -1, w + 2, h + 2);
      };
    }
    function paintStars(c, w, h) {
      var rnd = art.rand(61);
      for (var i = 0; i < 120; i++) {
        c.globalAlpha = 0.35 + rnd() * 0.65;
        c.fillStyle = rnd() < 0.15 ? "#ffe9b0" : rnd() < 0.3 ? "#bcd7ff" : "#ffffff";
        var s = 0.5 + rnd() * 1.4;
        c.fillRect(rnd() * w, rnd() * h, s, s);
      }
      c.globalAlpha = 1;
    }
    function paintSun(c, w) {
      var m = w / 2;
      var g = c.createRadialGradient(m, m, 2, m, m, m);
      g.addColorStop(0, "rgba(255,253,235,1)");
      g.addColorStop(0.16, "rgba(255,244,190,.95)");
      g.addColorStop(0.3, "rgba(255,240,180,.3)");
      g.addColorStop(1, "rgba(255,240,180,0)");
      c.fillStyle = g;
      c.fillRect(0, 0, w, w);
    }
    function paintMoon(c, w) {
      var m = w / 2, r = w * 0.3;
      var halo = c.createRadialGradient(m, m, r * 0.8, m, m, m);
      halo.addColorStop(0, "rgba(210,225,255,.35)");
      halo.addColorStop(1, "rgba(210,225,255,0)");
      c.fillStyle = halo;
      c.fillRect(0, 0, w, w);
      art.sphere(c, m, m, r, "#e6ebf7", false);
      c.fillStyle = "rgba(120,135,170,.4)";
      var craters = [[-0.3, -0.2, 0.2], [0.25, 0.1, 0.26], [-0.1, 0.4, 0.14], [0.3, -0.42, 0.12]];
      for (var i = 0; i < craters.length; i++) {
        c.beginPath();
        c.arc(m + craters[i][0] * r, m + craters[i][1] * r, craters[i][2] * r, 0, TAU);
        c.fill();
      }
    }
    function paintMountains(c, w, h) {
      var layers = [["#9db9d6", 0.3, 3], ["#6f93b8", 0.5, 2]];
      for (var l = 0; l < layers.length; l++) {
        c.fillStyle = layers[l][0];
        c.beginPath();
        c.moveTo(0, h);
        for (var x = 0; x <= w; x += 8) {
          var a = (x / w) * TAU * layers[l][2];
          c.lineTo(x, h * (layers[l][1] + 0.18 * Math.sin(a + l) + 0.08 * Math.sin(a * 2.7 + 1)));
        }
        c.lineTo(w, h);
        c.closePath();
        c.fill();
      }
      // مه پای کوه
      var haze = c.createLinearGradient(0, h * 0.5, 0, h);
      haze.addColorStop(0, "rgba(255,255,255,0)");
      haze.addColorStop(1, "rgba(255,255,255,.55)");
      c.fillStyle = haze;
      c.fillRect(0, h * 0.5, w, h * 0.5);
    }
    function paintGround(c, w, h) {
      art.grass(c, 0, 0, w, h, { base: "#52a644", seed: 19, density: 26 });
      var g = c.createLinearGradient(0, 0, 0, h);
      g.addColorStop(0, "rgba(255,255,210,.35)");
      g.addColorStop(0.1, "rgba(0,0,0,0)");
      g.addColorStop(1, "rgba(0,30,10,.5)");
      c.fillStyle = g;
      c.fillRect(0, 0, w, h);
      c.fillStyle = "rgba(255,255,255,.5)";
      c.fillRect(0, 0, w, 1.2);
    }

    /* سکو: ۰ ابر سفید، ۱ ابر آبی متحرک، ۲ ابر طوفانیِ شکننده */
    function paintPlatform(type) {
      return function (c, w, h) {
        art.shadow(c, w / 2, h - 2, w * 0.4, 4, 0.22);
        if (type === 2) art.cloud(c, 0, 0, w, "#c9ced9", "#4f566b", 6);
        else if (type === 1) art.cloud(c, 0, 0, w, "#f2fcff", "#4fb4ea", 2);
        else art.cloud(c, 0, 0, w, "#ffffff", "#9fb4e0", 4);
        if (type === 2) {
          // صاعقه‌ی کوچک: این ابر بعد از یک پرش از هم می‌پاشد
          c.fillStyle = "#ffd84a";
          c.strokeStyle = "rgba(90,60,0,.6)";
          c.lineWidth = 0.8;
          c.lineJoin = "round";
          c.beginPath();
          c.moveTo(w * 0.52, h * 0.34);
          c.lineTo(w * 0.42, h * 0.62);
          c.lineTo(w * 0.5, h * 0.62);
          c.lineTo(w * 0.44, h * 0.9);
          c.lineTo(w * 0.6, h * 0.54);
          c.lineTo(w * 0.52, h * 0.54);
          c.lineTo(w * 0.58, h * 0.34);
          c.closePath();
          c.fill();
          c.stroke();
        } else if (type === 1) {
          // خط‌های باد دو طرف ابر متحرک
          c.strokeStyle = "rgba(255,255,255,.9)";
          c.lineWidth = 1.6;
          c.lineCap = "round";
          c.beginPath();
          c.moveTo(1, h * 0.52);
          c.lineTo(7, h * 0.52);
          c.moveTo(3, h * 0.68);
          c.lineTo(8, h * 0.68);
          c.moveTo(w - 7, h * 0.52);
          c.lineTo(w - 1, h * 0.52);
          c.moveTo(w - 8, h * 0.68);
          c.lineTo(w - 3, h * 0.68);
          c.stroke();
        }
      };
    }
    function paintSpring(c) {
      c.strokeStyle = "#5d6676";
      c.lineWidth = 3.4;
      c.lineJoin = "round";
      c.beginPath();
      c.moveTo(6, 20);
      c.lineTo(20, 16);
      c.lineTo(6, 12);
      c.lineTo(20, 8);
      c.stroke();
      c.strokeStyle = "#d5dbe6";
      c.lineWidth = 1.6;
      c.stroke();
      art.bevel(c, 0, 0, 26, 8, 4, "#ff5d5d");
    }
    function paintFarCloud(seed) {
      return function (c, w) {
        art.cloud(c, 0, 0, w, "#ffffff", "#c5d6f2", seed);
      };
    }
    function paintBalloon(color) {
      return function (c, w, h) {
        var m = w / 2, r = w * 0.44;
        // طناب‌ها و سبد
        c.strokeStyle = "rgba(60,40,20,.7)";
        c.lineWidth = 0.8;
        c.beginPath();
        c.moveTo(m - r * 0.5, r * 1.7);
        c.lineTo(m - 4, h - 9);
        c.moveTo(m + r * 0.5, r * 1.7);
        c.lineTo(m + 4, h - 9);
        c.stroke();
        art.wood(c, m - 5, h - 9, 10, 8, { base: "#a8743f", seed: 3, horizontal: true, knots: 0 });
        // بادکنک راه‌راه
        c.save();
        c.beginPath();
        c.moveTo(m - r * 0.42, r * 1.86);
        c.quadraticCurveTo(m - r * 1.25, r * 1.1, m - r, r * 0.7);
        c.arc(m, r * 0.94, r, Math.PI * 1.08, Math.PI * 1.92);
        c.quadraticCurveTo(m + r * 1.25, r * 1.1, m + r * 0.42, r * 1.86);
        c.closePath();
        c.clip();
        var stripes = [color, "#ffffff", color, "#ffffff", color];
        for (var i = 0; i < 5; i++) {
          c.fillStyle = stripes[i];
          c.fillRect(m - r + (i * r * 2) / 5, 0, (r * 2) / 5 + 0.5, h);
        }
        var shade = c.createLinearGradient(m - r, 0, m + r, 0);
        shade.addColorStop(0, "rgba(255,255,255,.35)");
        shade.addColorStop(0.45, "rgba(255,255,255,0)");
        shade.addColorStop(1, "rgba(0,0,40,.4)");
        c.fillStyle = shade;
        c.fillRect(0, 0, w, h);
        c.restore();
      };
    }

    /* شخصیت رو به راست؛ پاها روی y=0. pose: up (در حال بالا رفتن، پاها جمع) | down (در حال افتادن) */
    function paintHero(pose, blink) {
      return function (c) {
        c.translate(26, 64);
        var up = pose === "up";
        // پاها و کفش‌ها
        for (var side = -1; side <= 1; side += 2) {
          var fx = side * 8 + (up ? side * 2 : 0), fy = up ? -8 : -1;
          c.strokeStyle = "#4a2fa0";
          c.lineWidth = 5.4;
          c.lineCap = "round";
          c.beginPath();
          c.moveTo(side * 7, -10);
          c.lineTo(fx, fy - 3);
          c.stroke();
          c.fillStyle = "#ffb703";
          c.beginPath();
          c.ellipse(fx + 1.5, fy - 1.6, 6, 3.4, 0, 0, TAU);
          c.fill();
          c.fillStyle = "rgba(120,70,0,.5)";
          c.fillRect(fx - 4.5, fy + 0.4, 12, 1.2);
        }
        // بدن ژله‌ای با نور از چپ-بالا
        var body = c.createRadialGradient(-6, -36, 3, 0, -26, 26);
        body.addColorStop(0, "#e6dcff");
        body.addColorStop(0.45, "#a98bf7");
        body.addColorStop(1, "#5a2dc4");
        c.fillStyle = body;
        art.rr(c, -17, -46, 34, 40, 15);
        c.fill();
        c.strokeStyle = "rgba(50,20,120,.55)";
        c.lineWidth = 1;
        c.stroke();
        // برق و شکم
        c.fillStyle = "rgba(255,255,255,.45)";
        c.beginPath();
        c.ellipse(-8, -37, 4.6, 8, -0.4, 0, TAU);
        c.fill();
        c.fillStyle = "rgba(255,255,255,.16)";
        c.beginPath();
        c.ellipse(1, -15, 10, 7, 0, 0, TAU);
        c.fill();
        // دست‌ها
        c.strokeStyle = "#7b55e6";
        c.lineWidth = 5;
        c.beginPath();
        c.moveTo(-16, -26);
        c.lineTo(-22, up ? -38 : -18);
        c.moveTo(16, -26);
        c.lineTo(22, up ? -38 : -18);
        c.stroke();
        // چشم‌ها
        for (var e = 0; e < 2; e++) {
          var ex = e ? 10 : -3;
          if (blink) {
            c.strokeStyle = "#2a1560";
            c.lineWidth = 1.8;
            c.beginPath();
            c.arc(ex, -29, 5, 0.15 * Math.PI, 0.85 * Math.PI);
            c.stroke();
          } else {
            c.fillStyle = "#ffffff";
            c.beginPath();
            c.arc(ex, -28, 6.2, 0, TAU);
            c.fill();
            c.fillStyle = "#1b1f3a";
            c.beginPath();
            c.arc(ex + 2, up ? -29.4 : -26.6, 3, 0, TAU);
            c.fill();
            c.fillStyle = "#ffffff";
            c.beginPath();
            c.arc(ex + 1, up ? -30.6 : -27.8, 1.1, 0, TAU);
            c.fill();
          }
        }
        // دهان: لبخند هنگام بالا رفتن، «او» هنگام افتادن
        c.strokeStyle = "#2a1560";
        c.fillStyle = "#2a1560";
        c.lineWidth = 1.6;
        c.beginPath();
        if (up) {
          c.arc(4, -19, 4.5, 0.15 * Math.PI, 0.85 * Math.PI);
          c.stroke();
        } else {
          c.ellipse(4.5, -17, 2.4, 3, 0, 0, TAU);
          c.fill();
        }
        // آنتن با حباب نورانی
        c.strokeStyle = "#c4b5fd";
        c.lineWidth = 2.5;
        c.beginPath();
        c.moveTo(0, -46);
        c.quadraticCurveTo(-6, -56, -3, -60);
        c.stroke();
        art.sphere(c, -3, -61.5, 3.8, "#ffc233");
      };
    }

    function platform(c, p, x, y) {
      env.blit(c, env.sprite("jumper:plat:" + p.type, CLOUD_W, CLOUD_H, paintPlatform(p.type), 3), x - 7, y - CLOUD_H * 0.4);
      if (p.spring) env.blit(c, env.sprite("jumper:spring", 26, 20, paintSpring, 2), x + PW / 2 - 13, y - 22);
    }

    return {
      controls: "sides",
      hudBump: false, // امتیاز همان ارتفاع است و پیوسته بالا می‌رود
      ownBackground: true,
      reset: function (state) {
        camera = state.camY;
        trail = [];
      },
      input: function (kind, data) {
        if (kind !== "tap") return null;
        return [data.x < env.W / 2 ? 0 : 1];
      },
      hud: function (state) {
        if (!state) return "";
        return state.started ? "ارتفاع" : "چپ یا راست را بزن";
      },
      event: function (name, state) {
        var x = state.x * S, y = screenY(state.y);
        if (name === "bounce") {
          squash = 1;
          env.fx.burst(x, y, "#ffffff", 6, 2);
          env.sound("tick");
        } else if (name === "spring") {
          squash = 1.6;
          env.fx.burst(x, y, env.colors.gold, 18, 5);
          env.fx.ring(x, y, "#ffe9b0", 8, 50);
          env.fx.text(x, y - 40, "فنر!", env.colors.gold);
          env.haptic("medium");
          env.sound("bonus");
        } else if (name === "break") {
          squash = 1;
          env.fx.debris(x, y + 8, "#8f96a8", 10, 3.2, 4);
          env.fx.burst(x, y + 8, "#ffe36b", 8, 3);
          env.haptic("light");
          env.sound("tap");
        } else if (name === "fail") {
          env.fx.flash(env.colors.danger, 0.45);
          env.fx.shake(9);
          env.haptic("error");
          env.sound("bad");
        }
      },
      draw: function (c, state, alpha) {
        var W = env.W, H = env.H, i, now = env.now();
        camera += (state.camY - camera) * 0.18;
        var moving = state.started && !state.over;
        var depth = env.clamp(state.maxY / 60000, 0, 1);
        var rise = (camera + core.VIEW_BELOW) * S * (H / 640); // مقدار بالا رفتن دوربین روی صفحه

        // آسمان: هر چه بالاتر، تیره‌تر و پرستاره‌تر
        c.drawImage(env.sprite("jumper:day", 4, H, sky("#3a8fe4", "#cdeeff")).canvas, -12, -12, W + 24, H + 24);
        if (depth < 0.7) {
          c.globalAlpha = 1 - depth / 0.7;
          env.blit(c, env.sprite("jumper:sun", 220, 220, paintSun), W * 0.78 - 110, env.safeTop - 60);
          c.globalAlpha = 1;
        }
        if (depth > 0.02) {
          c.globalAlpha = depth;
          c.drawImage(env.sprite("jumper:night", 4, H, sky("#050720", "#27306e")).canvas, -12, -12, W + 24, H + 24);
          env.blit(c, env.sprite("jumper:stars", W, H, paintStars), 0, 0);
          if (depth > 0.35) {
            c.globalAlpha = env.clamp((depth - 0.35) / 0.3, 0, 1);
            env.blit(c, env.sprite("jumper:moon", 110, 110, paintMoon), 26, env.safeTop + 10 + rise * 0.004);
          }
          c.globalAlpha = 1;
        }

        // کوه‌های دور (آهسته‌تر از زمین پایین می‌روند)
        var mountainY = H - 70 - 150 + rise * 0.35;
        if (mountainY < H + 12) env.blit(c, env.sprite("jumper:mountains", W + 24, 170, paintMountains), -12, mountainY);

        // ابرهای دوردست در دو لایه (پارالاکس)
        var fade = 1 - depth * 0.85;
        for (i = 0; i < 6; i++) {
          var near = i % 2 === 1;
          var cw = near ? 132 : 190;
          var far = env.sprite("jumper:far:" + (i % 3), cw, cw * 0.5, paintFarCloud(11 + (i % 3) * 7));
          var speed = near ? 0.14 : 0.06;
          var fy = ((i * 173 + rise * speed) % (H + 200)) - 110;
          var fx = ((i * 131 + now * (near ? 0.006 : 0.003)) % (W + cw)) - cw;
          c.globalAlpha = (near ? 0.5 : 0.3) * fade;
          env.blit(c, far, fx, fy);
        }
        c.globalAlpha = 1;

        // بالن‌ها در ارتفاع کم و میانه
        for (i = 0; i < 3; i++) {
          var by = H - 260 - (3200 + i * 7600) * S * (H / 640) + rise * 0.55 + Math.sin(now / 900 + i) * 4;
          if (by < -90 || by > H + 20) continue;
          var balloon = env.sprite("jumper:balloon:" + i, 44, 70, paintBalloon(["#ff5d5d", "#ffb703", "#3fdc94"][i]));
          env.blit(c, balloon, ((i * 139 + 40 + now * 0.004) % (W + 60)) - 50, by);
        }
        // پرنده‌ها نزدیک زمین
        if (depth < 0.25) {
          for (i = 0; i < 3; i++) {
            var birdX = ((now * (0.02 + i * 0.006) + i * 140) % (W + 80)) - 40;
            var birdY = H - 330 - i * 46 + rise * 0.7 + Math.sin(now / 500 + i * 2) * 6;
            if (birdY > -10 && birdY < H) art.bird(c, birdX, birdY, 6 - i, now / 130 + i, "rgba(40,50,80,.55)");
          }
        }

        var tick = state.tick + (moving ? alpha : 0);
        for (i = 0; i < state.plats.length; i++) {
          var p = state.plats[i];
          if (!p.alive) continue;
          var y = screenY(p.y);
          if (y < -50 || y > H + 50) continue;
          if (p.w >= core.WIDTH) {
            env.blit(c, env.sprite("jumper:ground", W + 24, 130, paintGround), -12, y);
            continue;
          }
          var x = core.platformX(p, Math.floor(tick)) * S;
          platform(c, p, x, y);
          if (x + PW > W) platform(c, p, x - W, y); // ادامه از لبه‌ی دیگر
        }

        // رد حرکت و شخصیت
        squash *= 0.82;
        var px = (state.x + (moving ? state.dir * core.H_SPEED * alpha : 0)) * S;
        var py = screenY(state.y + (moving ? state.vy * alpha : 0));
        if (moving && state.vy > 60) trail.push({ x: px, y: py - 20, life: 1 });
        c.fillStyle = "#d6c9ff";
        for (var t = trail.length - 1; t >= 0; t--) {
          trail[t].life -= 0.09;
          if (trail[t].life <= 0) { trail.splice(t, 1); continue; }
          c.globalAlpha = trail[t].life * 0.3;
          c.beginPath();
          c.arc(trail[t].x, trail[t].y, 12 * trail[t].life, 0, TAU);
          c.fill();
        }
        c.globalAlpha = 1;
        var pose = state.vy > 0 || !state.started ? "up" : "down";
        var blink = now % 2600 < 130;
        var hero = env.sprite("jumper:hero:" + pose + (blink ? ":b" : ""), 52, 70, paintHero(pose, blink), 2);
        var stretch = env.clamp(state.vy / 700, -0.18, 0.22);
        var facing = state.dir < 0 ? -1 : 1;
        var sx = (1 + squash * 0.2 - stretch * 0.5) * facing, sy = 1 - squash * 0.22 + stretch;
        for (var copy = -1; copy <= 1; copy++) {
          var hx = px + copy * W;
          if (hx < -34 || hx > W + 34) continue;
          // شال‌گردن که پشت سر در باد موج می‌زند
          c.strokeStyle = "#ff5d5d";
          c.lineWidth = 5;
          c.lineCap = "round";
          c.beginPath();
          c.moveTo(hx - facing * 6, py - 40 * sy);
          for (var seg = 1; seg <= 4; seg++) {
            c.lineTo(
              hx - facing * (6 + seg * 6),
              py - 40 * sy + Math.sin(now / 90 + seg * 1.1) * 2.6 * seg * 0.5 + env.clamp(state.vy, -160, 160) * 0.02 * seg
            );
          }
          c.stroke();
          c.save();
          c.translate(hx, py);
          c.scale(sx, sy);
          c.drawImage(hero.canvas, -26 - hero.pad, -64 - hero.pad, hero.fw, hero.fh);
          c.restore();
        }

        if (!state.started) {
          var nudge = Math.sin(now / 300) * 6;
          art.label(c, "‹", W * 0.16 - nudge, H * 0.55, 46, "#ffffff", 900);
          art.label(c, "›", W * 0.84 + nudge, H * 0.55, 46, "#ffffff", 900);
        }
      },
    };
  });
})();
