/* «دونده‌ی سه‌خطی» — رندر سه‌بعدی و افکت‌ها: جاده‌ی آسفالت در غروب، مانع راه‌بندان و جعبه‌های چوبی،
   سکه‌های چرخان، تیرهای چراغ کنار جاده و دونده‌ای با چرخه‌ی دویدن. */
(function () {
  "use strict";
  Arcade.registerRenderer("runner", function (env) {
    var core = Arcade.cores.runner, art = env.art;
    var ACTIONS = { left: 0, right: 1, up: 2 };
    var TAU = Math.PI * 2;
    var FAR = 9000, NEAR = -700, FIRST_Z = 4200;
    var VANISH = 30000; // جاده و خط‌چین‌ها تا نزدیک افق ادامه دارند؛ موانع از FAR پیدا می‌شوند
    var LANE = 96, FRAMES = 8;
    var laneX = 1; // موقعیت نمایشی (نرم) بین خط‌ها
    var lean = 0, crashAt = 0;

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
      // آسمان غروب
      var sky = c.createLinearGradient(0, -b, 0, hy + 6);
      sky.addColorStop(0, "#162454");
      sky.addColorStop(0.5, "#6a3f86");
      sky.addColorStop(0.82, "#e0647a");
      sky.addColorStop(1, "#ffbf78");
      c.fillStyle = sky;
      c.fillRect(-b, -b, w + b * 2, hy + b + 8);
      // خورشید
      var sun = c.createRadialGradient(w * 0.5, hy + 4, 4, w * 0.5, hy + 4, 120);
      sun.addColorStop(0, "rgba(255,244,200,1)");
      sun.addColorStop(0.16, "rgba(255,214,130,.95)");
      sun.addColorStop(0.2, "rgba(255,190,110,.5)");
      sun.addColorStop(1, "rgba(255,160,110,0)");
      c.fillStyle = sun;
      c.fillRect(-b, hy - 130, w + b * 2, 140);
      // کوه‌های دور
      var rnd = art.rand(4);
      for (var layer = 0; layer < 2; layer++) {
        c.fillStyle = layer ? "#3b2c5e" : "#6a4a82";
        c.beginPath();
        c.moveTo(-b, hy + 4);
        for (var x = -b; x <= w + b + 30; x += 30) c.lineTo(x, hy - (layer ? 8 : 20) - rnd() * (layer ? 26 : 34));
        c.lineTo(w + b, hy + 4);
        c.closePath();
        c.fill();
      }
      // زمین دو طرف جاده
      var land = c.createLinearGradient(0, hy, 0, h + b);
      land.addColorStop(0, "#4a4460");
      land.addColorStop(0.12, "#2f3a35");
      land.addColorStop(1, "#16211b");
      c.fillStyle = land;
      c.fillRect(-b, hy, w + b * 2, h + b - hy);
      art.speckle(c, -b, hy, w + b * 2, h + b - hy, "#000000", 500, 2);
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
      road.addColorStop(0, "#5a5766");
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
      c.restore();
      // مه افق
      var haze = c.createLinearGradient(0, hy - 6, 0, hy + 60);
      haze.addColorStop(0, "rgba(255,190,130,.55)");
      haze.addColorStop(1, "rgba(255,190,130,0)");
      c.fillStyle = haze;
      c.fillRect(-b, hy - 6, w + b * 2, 66);
      art.vignette(c, w, h, 0.4);
    }

    function paintBarrier(c, w, h) {
      // پایه‌ها
      c.fillStyle = "#5f6676";
      c.fillRect(8, 6, 5, h - 6);
      c.fillRect(w - 13, 6, 5, h - 6);
      c.fillStyle = "#3b404c";
      c.fillRect(3, h - 4, 15, 4);
      c.fillRect(w - 18, h - 4, 15, 4);
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
      g.addColorStop(0, "rgba(255,255,255,.4)");
      g.addColorStop(0.4, "rgba(255,255,255,0)");
      g.addColorStop(1, "rgba(0,0,0,.3)");
      c.fillStyle = g;
      c.fillRect(0, 2, w, 15);
      c.restore();
    }

    function paintCrates(c, w, h) {
      var half = h / 2;
      for (var i = 0; i < 2; i++) {
        var y = i * half, inset = i === 0 ? 5 : 0, cw = w - inset * 2;
        art.wood(c, inset, y, cw, half, { base: i ? "#a8743f" : "#b98248", seed: 40 + i, horizontal: true, knots: 1 });
        c.strokeStyle = "#4e2f14";
        c.lineWidth = 2;
        c.strokeRect(inset + 1, y + 1, cw - 2, half - 2);
        // قاب و تخته‌ی مورب
        c.fillStyle = "rgba(78,47,20,.85)";
        c.fillRect(inset, y, cw, 5);
        c.fillRect(inset, y + half - 5, cw, 5);
        c.fillRect(inset, y, 5, half);
        c.fillRect(inset + cw - 5, y, 5, half);
        c.strokeStyle = "rgba(78,47,20,.8)";
        c.lineWidth = 5;
        c.beginPath();
        c.moveTo(inset + 5, y + 5);
        c.lineTo(inset + cw - 5, y + half - 5);
        c.stroke();
        c.fillStyle = "rgba(255,230,190,.22)";
        c.fillRect(inset + 5, y + 5, cw - 10, 1.5);
      }
      // سایه‌روشن حجم
      var g = c.createLinearGradient(0, 0, w, 0);
      g.addColorStop(0, "rgba(255,255,255,.12)");
      g.addColorStop(0.5, "rgba(0,0,0,0)");
      g.addColorStop(1, "rgba(0,0,0,.32)");
      c.fillStyle = g;
      c.fillRect(0, 0, w, h);
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

    function paintCoin(c) {
      art.coin(c, 16, 16, 15);
    }

    /* دونده از پشت سر؛ phase فاز چرخه‌ی دویدن و air حالت پرش */
    function paintRunner(phase, air) {
      return function (c) {
        c.translate(34, 108);
        var s = Math.sin(phase), bob = air ? -2 : -Math.abs(Math.cos(phase)) * 2.5;
        c.lineCap = "round";
        c.lineJoin = "round";
        function leg(x, lift) {
          var footY = -lift * 20 - (air ? 16 : 0);
          c.strokeStyle = "#1c2742";
          c.lineWidth = 10;
          c.beginPath();
          c.moveTo(x, -44 + bob);
          c.lineTo(x * 1.25, -25 + bob - lift * 9);
          c.lineTo(x, footY - 6);
          c.stroke();
          // کفش
          c.fillStyle = "#f4f6fa";
          c.beginPath();
          c.ellipse(x, footY - 3.5, 6.5, 4.6, 0, 0, TAU);
          c.fill();
          c.fillStyle = "#e5383b";
          c.fillRect(x - 6.5, footY - 2.2, 13, 2.2);
        }
        function arm(x, swing) {
          var side = x < 0 ? -1 : 1;
          c.strokeStyle = "#e9b98e";
          c.lineWidth = 6.5;
          c.beginPath();
          c.moveTo(x, -76 + bob);
          c.lineTo(x + side * 5, -62 + bob + swing * 4);
          c.lineTo(x + side * 2, (air ? -84 : -50) + bob + swing * 9);
          c.stroke();
          c.strokeStyle = "#c81e3a";
          c.lineWidth = 8;
          c.beginPath();
          c.moveTo(x, -76 + bob);
          c.lineTo(x + side * 3.5, -67 + bob + swing * 2.5);
          c.stroke();
        }
        leg(-7, air ? 0.7 : Math.max(0, s));
        leg(7, air ? 0.7 : Math.max(0, -s));
        arm(-16, -s);
        arm(16, s);
        // پیراهن
        var jersey = c.createLinearGradient(-15, 0, 15, 0);
        jersey.addColorStop(0, "#ff6b6b");
        jersey.addColorStop(0.55, "#e5383b");
        jersey.addColorStop(1, "#a51a2c");
        c.fillStyle = jersey;
        art.rr(c, -15, -84 + bob, 30, 44, 10);
        c.fill();
        c.fillStyle = "rgba(255,255,255,.9)";
        c.font = env.font(15, 900);
        c.textAlign = "center";
        c.fillText("7", 0, -56 + bob);
        c.fillStyle = "#1c2742";
        art.rr(c, -14, -46 + bob, 28, 10, 4);
        c.fill();
        // سر و مو
        art.sphere(c, 0, -96 + bob, 11, "#e9b98e", false);
        c.fillStyle = "#3a2a1c";
        c.beginPath();
        c.arc(0, -97 + bob, 11.4, Math.PI * 0.95, Math.PI * 2.05);
        c.quadraticCurveTo(0, -90 + bob, -11, -94 + bob);
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
        } else if (cell === 2) {
          art.shadow(c, x + 4 * sc, p.y, 46 * sc, 9 * sc, 0.5);
          c.drawImage(env.sprite("runner:crates", 76, 96, paintCrates).canvas, x - 38 * sc, p.y - 96 * sc, 76 * sc, 96 * sc);
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
          env.fx.burst(px, py, "#d8d2c4", 6, 2);
          env.sound("tick");
        } else if (name === "move") {
          env.sound("tap");
        } else if (name === "fail") {
          crashAt = env.now();
          env.fx.flash(env.colors.danger, 0.5);
          env.fx.shake(10);
          env.fx.debris(px, py - 40, "#b98248", 14, 5.5, 5);
          env.fx.burst(px, py - 30, "#ffffff", 14, 4);
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

        // تیرهای چراغ کنار جاده (از دور به نزدیک)
        var lamp = env.sprite("runner:lamp", 32, 150, paintLamp);
        for (z = FAR * 1.4 - ((FAR * 1.4 + dist) % core.ROW_GAP); z > NEAR; z -= core.ROW_GAP) {
          p = project(z, P0);
          var lw = 32 * p.scale, lh = 150 * p.scale;
          c.drawImage(lamp.canvas, xFor(-1.05, p.scale) - lw / 2, p.y - lh, lw, lh);
          c.drawImage(lamp.canvas, xFor(3.05, p.scale) - lw / 2, p.y - lh, lw, lh);
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
        art.shadow(c, px, gy + 2, 24 - lift * 0.14, 7 - lift * 0.05, 0.5 - lift * 0.003);
        var frame = state.over ? 2 : Math.floor(dist / 85) % FRAMES;
        var air = lift > 0;
        var sprite = env.sprite(air ? "runner:air" : "runner:run:" + frame, 68, 112, paintRunner((frame / FRAMES) * TAU, air), 2);
        if (state.over) {
          // زمین خوردن بعد از برخورد
          var t = crashAt ? Math.min(1, (env.now() - crashAt) / 350) : 1;
          c.save();
          c.translate(px, gy);
          c.rotate(-t * 1.35);
          c.drawImage(sprite.canvas, -34 - sprite.pad, -108 - sprite.pad + t * 10, sprite.fw, sprite.fh);
          c.restore();
        } else {
          c.save();
          c.translate(px, gy - lift);
          c.rotate(lean * 0.12);
          c.drawImage(sprite.canvas, -34 - sprite.pad, -108 - sprite.pad, sprite.fw, sprite.fh);
          c.restore();
        }

        // ردیفی که همین حالا از آن رد شده و از کنار دوربین بیرون می‌رود
        for (k = state.passed - 1; k >= Math.max(0, state.passed - 2); k--) {
          z = FIRST_Z + k * core.ROW_GAP - dist;
          if (z < 0 && z > NEAR) drawRow(c, state, k, z);
        }
      },
    };
  });
})();
