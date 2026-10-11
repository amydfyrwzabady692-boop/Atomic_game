/* «دونده‌ی سه‌خطی» — رندر سه‌بعدی و افکت‌ها: جاده‌ی آسفالت در غروب با شهر دوردست، خودروهایی که جلوی راه
   را گرفته‌اند (از پشت سر، با چراغ عقب روشن)، مانع راه‌بندان، سکه‌های چرخان، درخت و تیر چراغ کنار جاده
   و دونده‌ای با چرخه‌ی دویدن. */
(function () {
  "use strict";
  Arcade.registerRenderer("runner", function (env) {
    var core = Arcade.cores.runner, art = env.art;
    var ACTIONS = { left: 0, right: 1, up: 2 };
    var TAU = Math.PI * 2;
    var FAR = 9000, NEAR = -700, FIRST_Z = 4200;
    var VANISH = 30000; // جاده و خط‌چین‌ها تا نزدیک افق ادامه دارند؛ موانع از FAR پیدا می‌شوند
    var LANE = 96, FRAMES = 8;
    // هر مانع بلند یکی از این‌هاست (بر اساس شماره‌ی ردیف و خط، همیشه یکسان)
    var VEHICLES = [
      { key: "red", color: "#d8343f", kind: "sedan", h: 84 },
      { key: "blue", color: "#2f6fd6", kind: "sedan", h: 84 },
      { key: "taxi", color: "#f4c21f", kind: "taxi", h: 86 },
      { key: "van", color: "#e9edf2", kind: "van", h: 104 },
      { key: "green", color: "#2f9e6b", kind: "sedan", h: 84 },
    ];
    var laneX = 1; // موقعیت نمایشی (نرم) بین خط‌ها
    var lean = 0, crashAt = 0, wasInAir = false;

    function horizon() { return env.safeTop + 50; }
    function ground() { return env.H - 120; }
    /* عمق z (۰ = بازیکن) → موقعیت و مقیاس روی صفحه */
    function project(z, out) {
      var t = Math.max(NEAR, Math.min(VANISH, z)) / FAR;
      var k = 1 / (1 + t * 3.2); // پرسپکتیو
      var hy = horizon();
      out.y = hy + (ground() - hy) * k;
      out.scale = k;
      return out;
    }
    function xFor(lane, scale) {
      return env.W / 2 + (lane - 1) * LANE * scale;
    }
    var P0 = { y: 0, scale: 1 }, P1 = { y: 0, scale: 1 };

    // ---------------------------------------------------------------- اسپرایت‌ها
    function paintScene(c, w, h, b) {
      var hy = horizon();
      var rnd = art.rand(4);
      // آسمان غروب و چند ستاره‌ی زودهنگام
      var sky = c.createLinearGradient(0, -b, 0, hy + 6);
      sky.addColorStop(0, "#131f4e");
      sky.addColorStop(0.45, "#5a3a86");
      sky.addColorStop(0.8, "#e0647a");
      sky.addColorStop(1, "#ffc37a");
      c.fillStyle = sky;
      c.fillRect(-b, -b, w + b * 2, hy + b + 8);
      c.fillStyle = "#ffffff";
      for (var s = 0; s < 26; s++) {
        c.globalAlpha = 0.25 + rnd() * 0.5;
        c.fillRect(rnd() * w, rnd() * hy * 0.5, 1.2, 1.2);
      }
      c.globalAlpha = 1;
      // خورشید در حال غروب
      var sun = c.createRadialGradient(w * 0.5, hy - 6, 4, w * 0.5, hy - 6, 130);
      sun.addColorStop(0, "rgba(255,248,214,1)");
      sun.addColorStop(0.17, "rgba(255,222,140,1)");
      sun.addColorStop(0.2, "rgba(255,196,120,.55)");
      sun.addColorStop(1, "rgba(255,160,110,0)");
      c.fillStyle = sun;
      c.fillRect(-b, hy - 140, w + b * 2, 150);
      // ابرهای غروب که از پایین نور گرفته‌اند
      art.cloud(c, 18, hy - 118, 120, "#ffd9c4", "#8a5a94", 3);
      art.cloud(c, 232, hy - 96, 96, "#ffcdb6", "#7d5290", 5);
      art.cloud(c, 150, hy - 134, 70, "#ffe3cf", "#9a6aa0", 8);
      // کوه‌های دور (وسط کوتاه‌تر تا خورشید دیده شود)
      for (var layer = 0; layer < 2; layer++) {
        c.fillStyle = layer ? "#3b2c5e" : "#6a4a82";
        c.beginPath();
        c.moveTo(-b, hy + 4);
        for (var x = -b; x <= w + b + 30; x += 24) {
          var side = Math.min(1, Math.abs(x - w / 2) / 150);
          c.lineTo(x, hy - (layer ? 4 : 10) - (rnd() * (layer ? 22 : 30) + 6) * side);
        }
        c.lineTo(w + b, hy + 4);
        c.closePath();
        c.fill();
      }
      // شهر دوردست با پنجره‌های روشن
      for (var bx = -b; bx < w + b; bx += 9 + rnd() * 10) {
        if (Math.abs(bx - w / 2) < 26) continue;
        var bh = 8 + rnd() * 24, bw = 7 + rnd() * 8;
        c.fillStyle = "#241a3d";
        c.fillRect(bx, hy - bh + 4, bw, bh);
        c.fillStyle = "rgba(255,214,130,.85)";
        for (var wy = hy - bh + 7; wy < hy; wy += 4) {
          for (var wx = bx + 1.5; wx < bx + bw - 2; wx += 3) if (rnd() < 0.42) c.fillRect(wx, wy, 1.4, 1.6);
        }
      }
      // زمین دو طرف جاده: چمن در نور غروب
      var land = c.createLinearGradient(0, hy, 0, h + b);
      land.addColorStop(0, "#5a4d63");
      land.addColorStop(0.1, "#3a4a3a");
      land.addColorStop(1, "#152318");
      c.fillStyle = land;
      c.fillRect(-b, hy, w + b * 2, h + b - hy);
      art.speckle(c, -b, hy, w + b * 2, h + b - hy, "#000000", 500, 2);
      art.speckle(c, -b, hy + 40, w + b * 2, h + b - hy, "#9ad07a", 260, 6);
      // جاده
      var far = { y: hy, scale: 0 }, near = project(NEAR, {});
      c.fillStyle = "#c9c2b4"; // شانه‌ی جاده
      c.beginPath();
      c.moveTo(xFor(-0.62, far.scale), far.y);
      c.lineTo(xFor(2.62, far.scale), far.y);
      c.lineTo(xFor(2.62, near.scale), near.y);
      c.lineTo(xFor(-0.62, near.scale), near.y);
      c.closePath();
      c.fill();
      var road = c.createLinearGradient(0, far.y, 0, h);
      road.addColorStop(0, "#6a6170");
      road.addColorStop(0.25, "#3d3f49");
      road.addColorStop(1, "#2a2c34");
      c.fillStyle = road;
      c.beginPath();
      c.moveTo(xFor(-0.5, far.scale), far.y);
      c.lineTo(xFor(2.5, far.scale), far.y);
      c.lineTo(xFor(2.5, near.scale), near.y);
      c.lineTo(xFor(-0.5, near.scale), near.y);
      c.closePath();
      c.fill();
      c.save();
      c.clip();
      art.speckle(c, 0, far.y, w, h - far.y, "#ffffff", 700, 9);
      art.speckle(c, 0, far.y, w, h - far.y, "#000000", 900, 10);
      // بازتاب گرم خورشید روی آسفالت
      var shine = c.createLinearGradient(0, hy, 0, hy + 170);
      shine.addColorStop(0, "rgba(255,190,120,.4)");
      shine.addColorStop(1, "rgba(255,190,120,0)");
      c.fillStyle = shine;
      c.fillRect(w / 2 - 60, hy, 120, 170);
      c.restore();
      // مه افق
      var haze = c.createLinearGradient(0, hy - 6, 0, hy + 56);
      haze.addColorStop(0, "rgba(255,190,130,.5)");
      haze.addColorStop(1, "rgba(255,190,130,0)");
      c.fillStyle = haze;
      c.fillRect(-b, hy - 6, w + b * 2, 62);
      art.vignette(c, w, h, 0.4);
    }

    function paintBarrier(c, w, h) {
      // پایه‌ها
      art.metal(c, 8, 6, 5, h - 6, { base: "#7b8494", vertical: true });
      art.metal(c, w - 13, 6, 5, h - 6, { base: "#7b8494", vertical: true });
      c.fillStyle = "#30343e";
      art.rr(c, 2, h - 5, 17, 5, 2);
      c.fill();
      art.rr(c, w - 19, h - 5, 17, 5, 2);
      c.fill();
      // تخته‌ی راه‌راه
      c.save();
      art.rr(c, 0, 2, w, 15, 3);
      c.clip();
      c.fillStyle = "#ffc933";
      c.fillRect(0, 2, w, 15);
      c.fillStyle = "#22252c";
      for (var x = -10; x < w + 10; x += 16) {
        c.beginPath();
        c.moveTo(x, 17);
        c.lineTo(x + 8, 17);
        c.lineTo(x + 16, 2);
        c.lineTo(x + 8, 2);
        c.closePath();
        c.fill();
      }
      var g = c.createLinearGradient(0, 2, 0, 17);
      g.addColorStop(0, "rgba(255,255,255,.45)");
      g.addColorStop(0.4, "rgba(255,255,255,0)");
      g.addColorStop(1, "rgba(0,0,0,.3)");
      c.fillStyle = g;
      c.fillRect(0, 2, w, 15);
      c.restore();
      // چراغ چشمک‌زن‌ها (خاموش؛ هاله‌ی روشن جدا کشیده می‌شود)
      art.sphere(c, 10.5, 4, 3.4, "#ff9f1c");
      art.sphere(c, w - 10.5, 4, 3.4, "#ff9f1c");
    }

    function paintVehicle(spec) {
      return function (c, w, h) {
        art.carRear(c, w, h, spec.color, spec.kind);
      };
    }

    function paintLamp(c, w, h) {
      var m = w / 2;
      art.metal(c, m - 1.6, 14, 3.2, h - 14, { base: "#6d7482", vertical: true });
      c.fillStyle = "#3b404c";
      c.fillRect(m - 5, h - 5, 10, 5);
      c.fillRect(m - 9, 10, 18, 5);
      var glow = c.createRadialGradient(m, 16, 1, m, 16, 16);
      glow.addColorStop(0, "rgba(255,240,190,1)");
      glow.addColorStop(0.3, "rgba(255,214,130,.6)");
      glow.addColorStop(1, "rgba(255,200,120,0)");
      c.fillStyle = glow;
      c.fillRect(m - 16, 0, 32, 32);
    }

    function paintTree(seed) {
      return function (c, w, h) {
        art.tree(c, w / 2, h, h * 0.98, seed % 2 ? "#3c8a4c" : "#2f7a4a", seed);
        // نور گرم غروب روی یک سمت تاج
        c.globalCompositeOperation = "source-atop";
        var warm = c.createLinearGradient(0, 0, w, 0);
        warm.addColorStop(0, "rgba(255,150,90,.22)");
        warm.addColorStop(0.5, "rgba(255,150,90,0)");
        c.fillStyle = warm;
        c.fillRect(0, 0, w, h);
        c.globalCompositeOperation = "source-over";
      };
    }

    function paintCoin(c) {
      art.coin(c, 16, 16, 15);
    }

    /* دونده از پشت سر؛ phase فاز چرخه‌ی دویدن و air حالت پرش */
    function paintRunner(phase, air) {
      return function (c) {
        c.translate(34, 108);
        var s = Math.sin(phase), bob = air ? -2 : -Math.abs(Math.cos(phase)) * 2.5;
        var skin = "#e9b98e", skinDark = "#c8935f";
        c.lineCap = "round";
        c.lineJoin = "round";
        function leg(x, lift) {
          var footY = -lift * 20 - (air ? 16 : 0);
          var kneeX = x * 1.25, kneeY = -25 + bob - lift * 9;
          // ساق و ران
          c.strokeStyle = skinDark;
          c.lineWidth = 8.6;
          c.beginPath();
          c.moveTo(x, -42 + bob);
          c.lineTo(kneeX, kneeY);
          c.lineTo(x, footY - 9);
          c.stroke();
          c.strokeStyle = skin;
          c.lineWidth = 6;
          c.beginPath();
          c.moveTo(x - 0.8, -42 + bob);
          c.lineTo(kneeX - 0.8, kneeY);
          c.lineTo(x - 0.8, footY - 9);
          c.stroke();
          // جوراب و کفش
          c.strokeStyle = "#f4f6fa";
          c.lineWidth = 7.4;
          c.beginPath();
          c.moveTo(x, footY - 12);
          c.lineTo(x, footY - 7);
          c.stroke();
          c.fillStyle = "#f4f6fa";
          c.beginPath();
          c.ellipse(x, footY - 3.6, 6.8, 4.8, 0, 0, TAU);
          c.fill();
          c.fillStyle = "#e5383b";
          art.rr(c, x - 6.8, footY - 2.4, 13.6, 2.6, 1.3);
          c.fill();
          c.fillStyle = "#1c2742";
          c.fillRect(x - 6.2, footY - 0.4, 12.4, 1.4);
        }
        function arm(x, swing) {
          var side = x < 0 ? -1 : 1;
          var handX = x + side * 2, handY = (air ? -86 : -50) + bob + swing * 9;
          c.strokeStyle = skinDark;
          c.lineWidth = 7;
          c.beginPath();
          c.moveTo(x, -76 + bob);
          c.lineTo(x + side * 5, -62 + bob + swing * 4);
          c.lineTo(handX, handY);
          c.stroke();
          c.strokeStyle = skin;
          c.lineWidth = 4.8;
          c.stroke();
          c.fillStyle = skin;
          c.beginPath();
          c.arc(handX, handY, 3.6, 0, TAU);
          c.fill();
          // آستین کوتاه
          c.strokeStyle = "#c81e3a";
          c.lineWidth = 9;
          c.beginPath();
          c.moveTo(x, -76 + bob);
          c.lineTo(x + side * 3.4, -67.5 + bob + swing * 2.4);
          c.stroke();
        }
        leg(-7, air ? 0.7 : Math.max(0, s));
        leg(7, air ? 0.7 : Math.max(0, -s));
        arm(-16, -s);
        arm(16, s);
        // شورت ورزشی
        var shorts = c.createLinearGradient(-15, 0, 15, 0);
        shorts.addColorStop(0, "#2f3d66");
        shorts.addColorStop(1, "#141c36");
        c.fillStyle = shorts;
        art.rr(c, -15, -50 + bob, 30, 17, 5);
        c.fill();
        c.fillStyle = "rgba(255,255,255,.5)";
        c.fillRect(-15, -44 + bob, 2, 10);
        c.fillRect(13, -44 + bob, 2, 10);
        // پیراهن با شماره
        var jersey = c.createLinearGradient(-16, 0, 16, 0);
        jersey.addColorStop(0, "#ff7676");
        jersey.addColorStop(0.5, "#e5383b");
        jersey.addColorStop(1, "#9d1a2c");
        c.fillStyle = jersey;
        art.rr(c, -16, -85 + bob, 32, 40, 10);
        c.fill();
        c.fillStyle = "rgba(255,255,255,.92)";
        c.font = env.font(15, 900);
        c.textAlign = "center";
        c.fillText("7", 0, -58 + bob);
        c.fillStyle = "rgba(255,255,255,.75)";
        c.fillRect(-9, -82 + bob, 18, 2);
        // گردن، گوش‌ها، سر و مو
        c.fillStyle = skinDark;
        art.rr(c, -4.5, -90 + bob, 9, 8, 3);
        c.fill();
        art.sphere(c, -11, -96 + bob, 2.6, skin, false);
        art.sphere(c, 11, -96 + bob, 2.6, skin, false);
        art.sphere(c, 0, -97 + bob, 11, skin, false);
        var hair = c.createLinearGradient(0, -110 + bob, 0, -90 + bob);
        hair.addColorStop(0, "#5a4028");
        hair.addColorStop(1, "#2c1c10");
        c.fillStyle = hair;
        c.beginPath();
        c.arc(0, -98 + bob, 11.6, Math.PI * 0.93, Math.PI * 2.07);
        c.quadraticCurveTo(6, -89 + bob, 0, -90 + bob);
        c.quadraticCurveTo(-6, -89 + bob, -11.2, -95.6 + bob);
        c.fill();
      };
    }

    /* یک چهارضلعی به مسیر فعلی اضافه می‌کند (همه با یک fill کشیده می‌شوند) */
    function quad(c, x1, y1, w1, x2, y2, w2) {
      c.moveTo(x1 - w1, y1);
      c.lineTo(x1 + w1, y1);
      c.lineTo(x2 + w2, y2);
      c.lineTo(x2 - w2, y2);
      c.closePath();
    }

    function drawRow(c, state, k, rz) {
      var p = project(rz, P0), row = state.rows[k];
      c.globalAlpha = env.clamp((FAR - rz) / 1300, 0, 1); // از دور کم‌کم پیدا می‌شوند
      for (var lane = 0; lane < 3; lane++) {
        var cell = row[lane];
        if (!cell) continue;
        var x = xFor(lane, p.scale), sc = p.scale;
        if (cell === 1) {
          art.shadow(c, x, p.y, 40 * sc, 7 * sc, 0.45);
          c.drawImage(env.sprite("runner:barrier", 74, 30, paintBarrier).canvas, x - 37 * sc, p.y - 30 * sc, 74 * sc, 30 * sc);
          // چراغ چشمک‌زن
          if (Math.sin(env.now() / 180 + k) > 0) {
            art.glow(c, x - 26.5 * sc, p.y - 26 * sc, 12 * sc, "#ffb347", 0.9);
            art.glow(c, x + 26.5 * sc, p.y - 26 * sc, 12 * sc, "#ffb347", 0.9);
          }
        } else if (cell === 2) {
          var spec = VEHICLES[(k * 3 + lane * 5) % VEHICLES.length];
          art.shadow(c, x, p.y + 1 * sc, 48 * sc, 9 * sc, 0.55);
          c.drawImage(env.sprite("runner:car:" + spec.key, 86, spec.h, paintVehicle(spec)).canvas, x - 43 * sc, p.y - spec.h * sc, 86 * sc, spec.h * sc);
        } else if (cell === 3) {
          var spin = Math.abs(Math.cos(env.now() / 230 + k));
          art.shadow(c, x, p.y, 12 * sc, 3.5 * sc, 0.35);
          art.glow(c, x, p.y - 34 * sc, 26 * sc, "#ffd257", 0.4);
          c.drawImage(env.sprite("runner:coin", 32, 32, paintCoin).canvas, x - 16 * sc * (0.15 + spin * 0.85), p.y - 50 * sc, 32 * sc * (0.15 + spin * 0.85), 32 * sc);
        }
      }
      c.globalAlpha = 1;
    }

    return {
      controls: "swipe",
      ownBackground: true,
      reset: function (state) {
        laneX = state.lane;
        lean = 0;
        crashAt = 0;
        wasInAir = false;
      },
      input: function (kind, data) {
        if (kind === "swipe" && ACTIONS[data.dir] !== undefined) return [ACTIONS[data.dir]];
        return null;
      },
      hud: function (state) {
        return state ? "سطح " + env.fa(state.level + 1) : "";
      },
      event: function (name, state) {
        var px = xFor(laneX, 1), py = ground();
        if (name === "coin") {
          env.fx.burst(px, py - 40, env.colors.gold, 10, 3);
          env.fx.ring(px, py - 40, "#ffe9b0", 8, 34);
          env.fx.text(px, py - 76, "+۵", env.colors.gold);
          env.haptic("light");
          env.sound("bonus");
        } else if (name === "jump") {
          env.fx.debris(px, py, "#b9b2a4", 5, 2, 2.4);
          env.sound("tick");
        } else if (name === "move") {
          env.sound("tap");
        } else if (name === "fail") {
          crashAt = env.now();
          env.fx.flash(env.colors.danger, 0.5);
          env.fx.shake(10);
          env.fx.debris(px, py - 40, "#d8dde6", 12, 5.5, 4);
          env.fx.burst(px, py - 30, "#ffffff", 14, 4);
          env.fx.ring(px, py - 40, "#ffffff", 10, 70);
          env.haptic("error");
          env.sound("bad");
        }
      },
      draw: function (c, state, alpha) {
        var gy = ground();
        var previous = laneX;
        laneX += (state.lane - laneX) * 0.35;
        lean += ((laneX - previous) * 3 - lean) * 0.4;
        var dist = state.dist + (state.over ? 0 : core.speedFor(state.passed) * alpha);
        var k, z, p, q;

        env.scene(c, "runner", paintScene);

        // خط‌چین‌های بین خط‌ها و خط‌های کناری که به سمت دوربین می‌آیند
        var stripe = core.ROW_GAP / 2;
        c.fillStyle = "rgba(255,255,255,.85)";
        c.beginPath();
        for (z = NEAR - (dist % stripe); z < VANISH * 0.5; z += stripe) {
          p = project(z, P0);
          q = project(z + stripe * 0.42, P1);
          for (var lane = 0.5; lane < 2; lane++) quad(c, xFor(lane, p.scale), p.y, 2 * p.scale, xFor(lane, q.scale), q.y, 2 * q.scale);
        }
        c.fill();
        c.fillStyle = "rgba(255,214,90,.9)";
        var far = project(VANISH, P0), near = project(NEAR, P1);
        c.beginPath();
        quad(c, xFor(-0.42, far.scale), far.y, 1.6 * far.scale, xFor(-0.42, near.scale), near.y, 1.6 * near.scale);
        quad(c, xFor(2.42, far.scale), far.y, 1.6 * far.scale, xFor(2.42, near.scale), near.y, 1.6 * near.scale);
        c.fill();

        // کنار جاده (از دور به نزدیک): یکی در میان تیر چراغ و درخت
        var lamp = env.sprite("runner:lamp", 32, 150, paintLamp);
        var span = FAR * 1.4;
        for (z = span - ((span + dist) % core.ROW_GAP); z > NEAR; z -= core.ROW_GAP) {
          p = project(z, P0);
          if (p.scale < 0.2) continue; // خیلی دور: دیده نمی‌شود
          var slot = Math.round((z + dist) / core.ROW_GAP);
          if (slot % 2 === 0) {
            var lw = 32 * p.scale, lh = 150 * p.scale;
            c.drawImage(lamp.canvas, xFor(-1.05, p.scale) - lw / 2, p.y - lh, lw, lh);
            c.drawImage(lamp.canvas, xFor(3.05, p.scale) - lw / 2, p.y - lh, lw, lh);
          } else {
            var seed = ((slot % 4) + 4) % 4;
            var tree = env.sprite("runner:tree:" + seed, 96, 132, paintTree(seed));
            var tw = 96 * p.scale * 1.25, th = 132 * p.scale * 1.25;
            c.drawImage(tree.canvas, xFor(-1.5, p.scale) - tw / 2, p.y - th, tw, th);
            c.drawImage(tree.canvas, xFor(3.5, p.scale) - tw / 2, p.y - th, tw, th);
          }
        }

        // موانع و سکه‌های جلوتر از دونده (از دور به نزدیک)
        var lastRow = Math.min(state.rows.length - 1, state.passed + 7);
        for (k = lastRow; k >= state.passed; k--) {
          z = FIRST_Z + k * core.ROW_GAP - dist;
          // بعد از برخورد، مانعی که دونده به آن خورده سر جایش می‌ماند
          if (z < FAR && (z >= 0 || state.over)) drawRow(c, state, k, Math.max(z, 0));
        }

        // دونده
        var px = xFor(laneX, 1);
        var lift = state.air > 0 ? Math.sin((1 - (state.air - alpha) / core.JUMP_TICKS) * Math.PI) * 64 : 0;
        var air = lift > 0;
        if (wasInAir && !air && !state.over) env.fx.debris(px, gy, "#b9b2a4", 6, 2.4, 2.4); // گرد و خاک فرود
        wasInAir = air;
        art.shadow(c, px, gy + 2, 24 - lift * 0.14, 7 - lift * 0.05, 0.5 - lift * 0.003);
        var frame = state.over ? 2 : Math.floor(dist / 85) % FRAMES;
        var sprite = env.sprite(air ? "runner:air" : "runner:run:" + frame, 68, 112, paintRunner((frame / FRAMES) * TAU, air), 2);
        c.save();
        if (state.over) {
          // زمین خوردن بعد از برخورد
          var t = crashAt ? Math.min(1, (env.now() - crashAt) / 350) : 1;
          c.translate(px, gy);
          c.rotate(-t * 1.35);
          c.drawImage(sprite.canvas, -34 - sprite.pad, -108 - sprite.pad + t * 10, sprite.fw, sprite.fh);
        } else {
          c.translate(px, gy - lift);
          c.rotate(lean * 0.12);
          c.drawImage(sprite.canvas, -34 - sprite.pad, -108 - sprite.pad, sprite.fw, sprite.fh);
        }
        c.restore();

        // ردیفی که همین حالا از آن رد شده و از کنار دوربین بیرون می‌رود
        for (k = state.passed - 1; k >= Math.max(0, state.passed - 2); k--) {
          z = FIRST_Z + k * core.ROW_GAP - dist;
          if (z < 0 && z > NEAR) drawRow(c, state, k, z);
        }

        // خط‌های سرعت در سطح‌های بالا
        var speed = core.speedFor(state.passed);
        if (speed > 50 && !state.over) {
          c.fillStyle = "rgba(255,255,255," + Math.min(0.22, (speed - 50) / 90) + ")";
          c.beginPath();
          for (var i = 0; i < 6; i++) {
            var phase = (env.now() / 260 + i * 0.37) % 1;
            var sx = i % 2 ? 14 + i * 5 : env.W - 14 - i * 5;
            var sy = horizon() + 60 + phase * (env.H - horizon() - 60);
            c.rect(sx, sy, 1.6, 26 + phase * 40);
          }
          c.fill();
        }
      },
    };
  });
})();
