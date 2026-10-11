/* «پرش ابرها» — رندر و افکت‌ها: آسمانی که با بالا رفتن از آبی روز به شب پرستاره می‌رسد، ابرهای پف‌دار
   سه‌نوع (عادی، متحرک، شکننده)، فنر و شخصیت ژله‌ای. همه‌ی اجزا اسپرایت کش‌شده‌اند. */
(function () {
  "use strict";
  Arcade.registerRenderer("jumper", function (env) {
    var core = Arcade.cores.jumper, art = env.art;
    var TAU = Math.PI * 2;
    var S = 0.1;
    var PW = core.PLAT_W * S;
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
      for (var i = 0; i < 110; i++) {
        c.globalAlpha = 0.35 + rnd() * 0.65;
        c.fillStyle = rnd() < 0.15 ? "#ffe9b0" : rnd() < 0.3 ? "#bcd7ff" : "#ffffff";
        var s = 0.5 + rnd() * 1.4;
        c.fillRect(rnd() * w, rnd() * h, s, s);
      }
      c.globalAlpha = 1;
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
      // برف قله‌ها و مه پای کوه
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

    /* سکو: ۰ ابر سفید، ۱ ابر آبی متحرک، ۲ ابر خاکستری شکننده */
    function paintPlatform(type) {
      return function (c, w, h) {
        art.shadow(c, w / 2, h - 3, w * 0.42, 4, 0.3);
        var top = type === 2 ? "#e2e4ea" : type === 1 ? "#e9fbff" : "#ffffff";
        var bottom = type === 2 ? "#8a90a2" : type === 1 ? "#63c4f0" : "#aebfe6";
        art.cloud(c, 0, 0, w, top, bottom);
        // سطح صاف بالایی برای ایستادن
        c.fillStyle = "rgba(255,255,255,.5)";
        art.rr(c, w * 0.12, h * 0.36, w * 0.76, 3, 1.5);
        c.fill();
        if (type === 2) {
          c.strokeStyle = "rgba(50,55,70,.7)";
          c.lineWidth = 1.6;
          c.lineCap = "round";
          c.lineJoin = "round";
          c.beginPath();
          c.moveTo(w * 0.44, h * 0.2);
          c.lineTo(w * 0.5, h * 0.42);
          c.lineTo(w * 0.45, h * 0.55);
          c.lineTo(w * 0.56, h * 0.82);
          c.stroke();
        } else if (type === 1) {
          c.strokeStyle = "rgba(255,255,255,.85)";
          c.lineWidth = 1.6;
          c.lineCap = "round";
          c.beginPath();
          c.moveTo(2, h * 0.5);
          c.lineTo(8, h * 0.5);
          c.moveTo(w - 8, h * 0.5);
          c.lineTo(w - 2, h * 0.5);
          c.stroke();
        }
      };
    }
    function paintSpring(c) {
      c.strokeStyle = "#8f99aa";
      c.lineWidth = 2.6;
      c.lineJoin = "round";
      c.beginPath();
      c.moveTo(6, 20);
      c.lineTo(20, 16);
      c.lineTo(6, 12);
      c.lineTo(20, 8);
      c.stroke();
      art.bevel(c, 0, 0, 26, 8, 4, "#ff5d5d");
    }
    function paintFarCloud(c, w) {
      art.cloud(c, 0, 0, w, "#ffffff", "#dbe7fb");
    }

    /* شخصیت رو به راست؛ پاها روی y=0 */
    function paintHero(c) {
      c.translate(24, 62);
      // پاها
      c.fillStyle = "#3b2a7a";
      art.rr(c, -12, -6, 9, 8, 3);
      c.fill();
      art.rr(c, 3, -6, 9, 8, 3);
      c.fill();
      // بدن
      var body = c.createLinearGradient(-17, 0, 17, 0);
      body.addColorStop(0, "#d6c9ff");
      body.addColorStop(0.5, "#9b7bf5");
      body.addColorStop(1, "#5b2fc9");
      c.fillStyle = body;
      art.rr(c, -17, -44, 34, 40, 15);
      c.fill();
      c.strokeStyle = "rgba(50,20,120,.5)";
      c.lineWidth = 1;
      c.stroke();
      c.fillStyle = "rgba(255,255,255,.4)";
      c.beginPath();
      c.ellipse(-7, -35, 5.5, 8.5, -0.4, 0, TAU);
      c.fill();
      // چشم‌ها (رو به جلو)
      c.fillStyle = "#fff";
      c.beginPath();
      c.arc(-3, -27, 6, 0, TAU);
      c.arc(10, -27, 6, 0, TAU);
      c.fill();
      c.fillStyle = "#1b1f3a";
      c.beginPath();
      c.arc(-1, -26, 2.8, 0, TAU);
      c.arc(12, -26, 2.8, 0, TAU);
      c.fill();
      c.fillStyle = "#fff";
      c.beginPath();
      c.arc(-2, -27.4, 1, 0, TAU);
      c.arc(11, -27.4, 1, 0, TAU);
      c.fill();
      // لبخند
      c.strokeStyle = "#2a1560";
      c.lineWidth = 1.6;
      c.lineCap = "round";
      c.beginPath();
      c.arc(4, -18, 4.5, 0.15 * Math.PI, 0.85 * Math.PI);
      c.stroke();
      // آنتن
      c.strokeStyle = "#c4b5fd";
      c.lineWidth = 2.5;
      c.beginPath();
      c.moveTo(0, -44);
      c.quadraticCurveTo(-6, -54, -3, -58);
      c.stroke();
      art.sphere(c, -3, -59.5, 3.6, "#ffc233");
    }

    function platform(c, p, x, y) {
      env.blit(c, env.sprite("jumper:plat:" + p.type, PW, 26, paintPlatform(p.type), 4), x, y - 10);
      if (p.spring) env.blit(c, env.sprite("jumper:spring", 26, 20, paintSpring, 2), x + PW / 2 - 13, y - 24);
    }

    return {
      controls: "sides",
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
          env.fx.burst(x, y, "#ffffff", 5, 2);
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
          env.fx.debris(x, y + 8, "#b3b8c6", 10, 3.2, 4);
          env.fx.burst(x, y + 8, "#ffffff", 8, 2.5);
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
        var W = env.W, H = env.H, i;
        camera += (state.camY - camera) * 0.18;
        var moving = state.started && !state.over;
        var depth = env.clamp(state.maxY / 60000, 0, 1);
        var rise = (camera + core.VIEW_BELOW) * S * (H / 640); // مقدار بالا رفتن دوربین روی صفحه

        // آسمان: هر چه بالاتر، تیره‌تر و پرستاره‌تر
        c.drawImage(env.sprite("jumper:day", 4, H, sky("#3f93e6", "#c9ecff")).canvas, -12, -12, W + 24, H + 24);
        if (depth > 0.02) {
          c.globalAlpha = depth;
          c.drawImage(env.sprite("jumper:night", 4, H, sky("#050720", "#27306e")).canvas, -12, -12, W + 24, H + 24);
          env.blit(c, env.sprite("jumper:stars", W, H, paintStars), 0, 0);
          c.globalAlpha = 1;
        }
        // کوه‌های دور (آهسته‌تر از زمین پایین می‌روند) و ابرهای دوردست
        var mountainY = H - 70 - 150 + rise * 0.35;
        if (mountainY < H + 12) env.blit(c, env.sprite("jumper:mountains", W + 24, 170, paintMountains), -12, mountainY);
        c.globalAlpha = 0.5 * (1 - depth * 0.8);
        var far = env.sprite("jumper:far", 130, 50, paintFarCloud);
        for (i = 0; i < 5; i++) {
          var fy = ((i * 190 + rise * 0.12) % (H + 140)) - 70;
          env.blit(c, far, ((i * 137) % (W + 60)) - 60, fy);
        }
        c.globalAlpha = 1;

        var tick = state.tick + (moving ? alpha : 0);
        for (i = 0; i < state.plats.length; i++) {
          var p = state.plats[i];
          if (!p.alive) continue;
          var y = screenY(p.y);
          if (y < -40 || y > H + 40) continue;
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
        var hero = env.sprite("jumper:hero", 48, 66, paintHero, 2);
        var stretch = env.clamp(state.vy / 700, -0.18, 0.22);
        var sx = (1 + squash * 0.2 - stretch * 0.5) * (state.dir < 0 ? -1 : 1), sy = 1 - squash * 0.22 + stretch;
        for (var copy = -1; copy <= 1; copy++) {
          var hx = px + copy * W;
          if (hx < -30 || hx > W + 30) continue;
          c.save();
          c.translate(hx, py);
          c.scale(sx, sy);
          c.drawImage(hero.canvas, -24 - hero.pad, -62 - hero.pad, hero.fw, hero.fh);
          c.restore();
        }

        if (!state.started) {
          var nudge = Math.sin(env.now() / 300) * 6;
          art.label(c, "‹", W * 0.16 - nudge, H * 0.55, 46, "#ffffff", 900);
          art.label(c, "›", W * 0.84 + nudge, H * 0.55, 46, "#ffffff", 900);
        }
      },
    };
  });
})();
