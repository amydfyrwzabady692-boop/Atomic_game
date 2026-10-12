/* «هیزم‌شکن» — رندر و افکت‌ها: جنگل کاج در روز با مه دوردست و ابر و پرنده، تنه‌ی درخت با پوست
   بافت‌دار، شاخه‌های پربرگ و هیزم‌شکنی که نفس می‌کشد، پلک می‌زند و تبرش واقعاً تاب می‌خورد.
   با هر ضربه برگ می‌ریزد. همه‌ی اجزا اسپرایت کش‌شده‌اند. */
(function () {
  "use strict";
  Arcade.registerRenderer("timber", function (env) {
    var core = Arcade.cores.timber, art = env.art;
    var TAU = Math.PI * 2;
    var SEG_H = 62, TRUNK_W = 80, BRANCH_W = 96;
    var swing = 0, drop = 0, fallen = 0;
    var chips = [];
    var leaves = [];

    function groundY() { return env.H - 104; }

    // ---------------------------------------------------------------- اسپرایت‌ها
    function pine(c, x, base, h, color) {
      c.fillStyle = "#3b2a1a";
      c.fillRect(x - h * 0.03, base - h * 0.12, h * 0.06, h * 0.12);
      c.fillStyle = color;
      for (var i = 0; i < 3; i++) {
        var top = base - h + i * h * 0.24, bottom = base - h * 0.1 - (2 - i) * h * 0.22, half = h * (0.16 + i * 0.07);
        c.beginPath();
        c.moveTo(x, top);
        c.lineTo(x + half, bottom);
        c.lineTo(x - half, bottom);
        c.closePath();
        c.fill();
      }
    }

    function paintScene(c, w, h, b) {
      var gy = groundY();
      var sky = c.createLinearGradient(0, -b, 0, gy);
      sky.addColorStop(0, "#5fb1ee");
      sky.addColorStop(0.6, "#bfe4fb");
      sky.addColorStop(1, "#fff3d6");
      c.fillStyle = sky;
      c.fillRect(-b, -b, w + b * 2, gy + b);
      // خورشید و پرتوها
      var sun = c.createRadialGradient(w * 0.82, env.safeTop + 40, 4, w * 0.82, env.safeTop + 40, 190);
      sun.addColorStop(0, "rgba(255,252,225,1)");
      sun.addColorStop(0.1, "rgba(255,244,190,.85)");
      sun.addColorStop(0.3, "rgba(255,240,190,.25)");
      sun.addColorStop(1, "rgba(255,240,190,0)");
      c.fillStyle = sun;
      c.fillRect(-b, -b, w + b * 2, gy + b);
      // کوه دوردست
      c.fillStyle = "#a9c7de";
      c.beginPath();
      c.moveTo(-b, gy);
      c.lineTo(-b, gy - 150);
      c.quadraticCurveTo(w * 0.18, gy - 250, w * 0.42, gy - 160);
      c.quadraticCurveTo(w * 0.7, gy - 270, w + b, gy - 170);
      c.lineTo(w + b, gy);
      c.closePath();
      c.fill();
      // سه ردیف کاج؛ هرچه دورتر، کم‌رنگ‌تر (مه)
      var rnd = art.rand(27);
      var rows = [
        { color: "#8fb8a6", size: 70, lift: 96, step: 26 },
        { color: "#4f8f6a", size: 104, lift: 52, step: 38 },
        { color: "#2c6a48", size: 140, lift: 8, step: 54 },
      ];
      for (var r = 0; r < rows.length; r++) {
        var row = rows[r];
        for (var x = -b - 10; x < w + b + 20; x += row.step * (0.7 + rnd() * 0.6)) {
          // جای تنه‌ی اصلی در ردیف جلو خالی می‌ماند
          if (r === 2 && Math.abs(x - w / 2) < 74) continue;
          pine(c, x, gy - row.lift, row.size * (0.75 + rnd() * 0.5), row.color);
        }
        var haze = c.createLinearGradient(0, gy - row.lift - 60, 0, gy - row.lift + 10);
        haze.addColorStop(0, "rgba(255,250,235,0)");
        haze.addColorStop(1, "rgba(255,250,235," + (0.5 - r * 0.16) + ")");
        c.fillStyle = haze;
        c.fillRect(-b, gy - row.lift - 60, w + b * 2, 70);
      }
      // زمین
      art.grass(c, -b, gy, w + b * 2, h - gy + b, { base: "#4b9a3f", seed: 14, density: 26 });
      var shade = c.createLinearGradient(0, gy, 0, h);
      shade.addColorStop(0, "rgba(255,255,220,.25)");
      shade.addColorStop(0.12, "rgba(0,0,0,0)");
      shade.addColorStop(1, "rgba(0,30,10,.45)");
      c.fillStyle = shade;
      c.fillRect(-b, gy, w + b * 2, h - gy + b);
      art.shadow(c, w / 2, gy + 8, 84, 13, 0.5);
      // سنگ، قارچ و گل روی زمین
      var deco = art.rand(71);
      for (var d = 0; d < 9; d++) {
        var dx = deco() * w, dy = gy + 16 + deco() * (h - gy - 26);
        if (Math.abs(dx - w / 2) < 96 && dy < gy + 40) continue; // جای هیزم‌شکن خالی بماند
        var kind = d % 3;
        if (kind === 0) {
          art.shadow(c, dx + 1, dy + 3, 9, 3, 0.35);
          art.sphere(c, dx, dy, 6 + deco() * 3, "#8d95a3", false);
        } else if (kind === 1) {
          c.fillStyle = "#f3ead8";
          c.fillRect(dx - 1.6, dy - 2, 3.2, 7);
          c.fillStyle = "#d8343f";
          c.beginPath();
          c.arc(dx, dy - 2, 6, Math.PI, 0);
          c.closePath();
          c.fill();
          c.fillStyle = "#ffffff";
          c.fillRect(dx - 3, dy - 5.4, 1.6, 1.6);
          c.fillRect(dx + 1.4, dy - 4.4, 1.4, 1.4);
        } else {
          c.fillStyle = ["#ffe066", "#ff9ecb", "#ffffff"][d % 3];
          for (var petal = 0; petal < 5; petal++) {
            var pa = (petal / 5) * TAU;
            c.beginPath();
            c.arc(dx + Math.cos(pa) * 2.4, dy + Math.sin(pa) * 2.4, 1.8, 0, TAU);
            c.fill();
          }
          c.fillStyle = "#f59e0b";
          c.beginPath();
          c.arc(dx, dy, 1.5, 0, TAU);
          c.fill();
        }
      }
    }

    function paintCloud(seed) {
      return function (c, w) {
        art.cloud(c, 0, 0, w, "#ffffff", "#b4c8e6", seed);
      };
    }

    function paintSegment(variant) {
      return function (c, w, h) {
        art.wood(c, 0, 0, w, h + 1, { base: "#8b5a33", seed: 60 + variant, round: true, knots: variant % 2 });
        // شیارهای پوست
        var rnd = art.rand(100 + variant);
        c.lineCap = "round";
        for (var i = 0; i < 7; i++) {
          var x = 6 + rnd() * (w - 12), y = rnd() * h * 0.7, len = 10 + rnd() * 22;
          c.strokeStyle = "rgba(35,18,8," + (0.35 + rnd() * 0.3) + ")";
          c.lineWidth = 1 + rnd() * 1.6;
          c.beginPath();
          c.moveTo(x, y);
          c.lineTo(x + (rnd() - 0.5) * 3, y + len);
          c.stroke();
          c.strokeStyle = "rgba(255,225,180,.16)";
          c.lineWidth = 0.8;
          c.beginPath();
          c.moveTo(x + 1.6, y + 1);
          c.lineTo(x + 1.6, y + len - 1);
          c.stroke();
        }
      };
    }

    /* شاخه به سمت راست؛ مبدأ در لبه‌ی تنه و وسط ارتفاع */
    function paintBranch(c, w, h) {
      var my = h / 2;
      env.dropShadow(c, 3, 3, 0.35);
      var wood = c.createLinearGradient(0, my - 9, 0, my + 9);
      wood.addColorStop(0, "#a8713f");
      wood.addColorStop(1, "#5a3519");
      c.fillStyle = wood;
      c.beginPath();
      c.moveTo(0, my - 9);
      c.lineTo(BRANCH_W - 20, my - 3);
      c.lineTo(BRANCH_W - 20, my + 4);
      c.lineTo(0, my + 10);
      c.closePath();
      c.fill();
      env.dropShadow(c);
      var leaves = [[62, 6, 17, "#2f8f46"], [84, 0, 19, "#3aa655"], [98, 10, 15, "#2c7f40"], [74, -12, 16, "#49b862"], [92, -14, 13, "#3aa655"], [52, -6, 12, "#2c7f40"]];
      for (var i = 0; i < leaves.length; i++) art.leaves(c, leaves[i][0], my + leaves[i][1], leaves[i][2], leaves[i][3]);
      c.fillStyle = "rgba(255,255,200,.3)";
      c.beginPath();
      c.ellipse(80, my - 14, 12, 5, -0.3, 0, TAU);
      c.fill();
    }

    function paintClock(c) {
      env.dropShadow(c, 3, 2, 0.4);
      art.sphere(c, 16, 18, 14, "#f5b82e", false);
      env.dropShadow(c);
      c.fillStyle = "#b9770e";
      c.fillRect(13.5, 1, 5, 5);
      c.fillStyle = "#fffaf0";
      c.beginPath();
      c.arc(16, 18, 10.5, 0, TAU);
      c.fill();
      c.strokeStyle = "#1b1f3a";
      c.lineWidth = 2;
      c.lineCap = "round";
      c.beginPath();
      c.moveTo(16, 11.5);
      c.lineTo(16, 18);
      c.lineTo(20.5, 21);
      c.stroke();
    }

    function paintStump(c, w) {
      art.wood(c, 6, 6, w - 12, 18, { base: "#6b4023", seed: 77, round: true, knots: 0 });
      var top = c.createLinearGradient(0, 0, w, 0);
      top.addColorStop(0, "#e0b07a");
      top.addColorStop(1, "#b98248");
      c.fillStyle = top;
      c.beginPath();
      c.ellipse(w / 2, 7, w / 2 - 5, 6.5, 0, 0, TAU);
      c.fill();
      c.strokeStyle = "rgba(90,50,20,.5)";
      c.lineWidth = 0.8;
      for (var r = 0.3; r < 1; r += 0.25) {
        c.beginPath();
        c.ellipse(w / 2, 7, (w / 2 - 5) * r, 6.5 * r, 0, 0, TAU);
        c.stroke();
      }
    }

    /* هیزم‌شکن رو به چپ (به سمت تنه)، بدون تبر؛ پاها روی y=0 */
    function paintJack(blink) {
      return function (c) {
        drawJack(c, blink);
      };
    }
    function drawJack(c, blink) {
      c.translate(30, 104);
      // پاها و چکمه
      c.fillStyle = "#2c3a63";
      art.rr(c, -14, -22, 11, 22, 4);
      c.fill();
      art.rr(c, 3, -22, 11, 22, 4);
      c.fill();
      c.fillStyle = "#5a3519";
      art.rr(c, -19, -7, 17, 8, 3);
      c.fill();
      art.rr(c, 0, -7, 17, 8, 3);
      c.fill();
      // پیراهن چهارخانه
      var shirt = c.createLinearGradient(-19, 0, 19, 0);
      shirt.addColorStop(0, "#ff7b7b");
      shirt.addColorStop(0.5, "#e5383b");
      shirt.addColorStop(1, "#9d1f2c");
      c.fillStyle = shirt;
      art.rr(c, -19, -58, 38, 40, 11);
      c.fill();
      c.save();
      art.rr(c, -19, -58, 38, 40, 11);
      c.clip();
      c.fillStyle = "rgba(0,0,0,.22)";
      for (var x = -19; x < 19; x += 12) c.fillRect(x + 5, -58, 4, 40);
      for (var y = -58; y < -18; y += 12) c.fillRect(-19, y + 5, 38, 4);
      c.restore();
      // بند شلوار
      c.fillStyle = "#2c3a63";
      c.fillRect(-12, -58, 4, 26);
      c.fillRect(8, -58, 4, 26);
      // سر، ریش و کلاه بافتنی
      art.sphere(c, 0, -72, 16, "#f0c49a", false);
      c.fillStyle = "#7a4520";
      c.beginPath();
      c.arc(0, -68, 16.5, 0.05 * Math.PI, 0.95 * Math.PI);
      c.quadraticCurveTo(0, -60, 16, -67);
      c.fill();
      if (blink) {
        c.strokeStyle = "#1b1f3a";
        c.lineWidth = 1.6;
        c.lineCap = "round";
        c.beginPath();
        c.moveTo(-11.4, -75);
        c.lineTo(-6.8, -75);
        c.moveTo(-1.4, -75);
        c.lineTo(3.2, -75);
        c.stroke();
      } else {
        c.fillStyle = "#ffffff";
        c.beginPath();
        c.arc(-9, -75, 3.2, 0, TAU);
        c.arc(1, -75, 3.2, 0, TAU);
        c.fill();
        c.fillStyle = "#1b1f3a";
        c.beginPath();
        c.arc(-9.8, -75, 1.9, 0, TAU);
        c.arc(0.2, -75, 1.9, 0, TAU);
        c.fill();
      }
      // ابرو و بینی
      c.strokeStyle = "#5a3212";
      c.lineWidth = 1.8;
      c.lineCap = "round";
      c.beginPath();
      c.moveTo(-12.4, -79.6);
      c.lineTo(-6.4, -78.6);
      c.moveTo(-2, -78.6);
      c.lineTo(4, -79.6);
      c.stroke();
      art.sphere(c, -5.2, -70.6, 2.6, "#e5a57a", false);
      var hat = c.createLinearGradient(0, -98, 0, -78);
      hat.addColorStop(0, "#ffd257");
      hat.addColorStop(1, "#e09a12");
      c.fillStyle = hat;
      c.beginPath();
      c.arc(0, -80, 17, Math.PI, 0);
      c.closePath();
      c.fill();
      c.fillStyle = "#c2410c";
      c.fillRect(-17, -83, 34, 5);
      art.sphere(c, 0, -98, 5, "#fff3c4", false);
    }

    /* تبر: دسته عمودی، لبه رو به چپ؛ مبدأ چرخش (دست) در پایین دسته */
    function paintAxe(c) {
      c.translate(30, 56);
      art.wood(c, -3, -50, 6, 56, { base: "#c79a63", seed: 5, knots: 0 });
      var blade = c.createLinearGradient(-26, 0, 4, 0);
      blade.addColorStop(0, "#f8fafc");
      blade.addColorStop(0.35, "#cbd5e1");
      blade.addColorStop(1, "#64748b");
      c.fillStyle = blade;
      c.beginPath();
      c.moveTo(4, -52);
      c.quadraticCurveTo(-26, -52, -25, -28);
      c.quadraticCurveTo(-12, -34, 4, -32);
      c.closePath();
      c.fill();
      c.strokeStyle = "rgba(30,40,60,.6)";
      c.lineWidth = 1;
      c.stroke();
      c.strokeStyle = "rgba(255,255,255,.9)";
      c.lineWidth = 1.4;
      c.beginPath();
      c.moveTo(-23, -47);
      c.quadraticCurveTo(-26, -40, -24, -30);
      c.stroke();
    }

    return {
      controls: "sides",
      ownBackground: true,
      reset: function () {
        chips = [];
        leaves = [];
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
          if (chips.length < 6) {
            chips.push({ x: cx, y: groundY() - SEG_H / 2, vx: state.side === 0 ? 8 : -8, vy: -6, rot: 0, life: 1, variant: state.chops % 4 });
          }
          env.fx.debris(cx + (state.side === 0 ? -1 : 1) * TRUNK_W / 2, groundY() - SEG_H / 2, "#e2b57e", 6, 3.2, 3);
          // برگ‌هایی که از شاخه‌ها می‌ریزند
          for (var leaf = 0; leaf < state.segs.length; leaf++) {
            if (state.segs[leaf].b && leaves.length < 14) {
              var side = state.segs[leaf].b === 1 ? -1 : 1;
              leaves.push({
                x: cx + side * (TRUNK_W / 2 + 40 + Math.random() * 40), y: groundY() - (leaf + 1) * SEG_H + 20,
                vx: (Math.random() - 0.5) * 0.8, vy: 0.6 + Math.random() * 0.8, phase: Math.random() * 6, life: 1,
              });
            }
          }
          env.fx.shake(2.5);
          env.haptic("light");
          env.sound("tap");
        } else if (name === "clock") {
          env.fx.text(cx, groundY() - SEG_H * 2, "+ زمان ⏱", env.colors.gold);
          env.fx.burst(cx, groundY() - SEG_H, env.colors.gold, 14, 4);
          env.haptic("medium");
          env.sound("bonus");
        } else if (name === "combo") {
          env.fx.text(cx, groundY() - SEG_H * 3, "سرعتی! +۵", "#ffffff");
          env.sound("good");
        } else if (name === "fail") {
          fallen = 0.01;
          env.fx.flash(env.colors.danger, 0.5);
          env.fx.shake(10);
          env.haptic("error");
          env.sound("bad");
        }
      },
      draw: function (c, state) {
        var cx = env.W / 2, gy = groundY();
        swing *= 0.78;
        drop *= 0.7;
        if (fallen > 0) fallen = Math.min(1, fallen + 0.06);
        env.scene(c, "timber", paintScene);
        var now = env.now();

        // ابرهای آرام و پرنده‌ها در آسمان
        for (var cl = 0; cl < 3; cl++) {
          var cw = 110 + cl * 36;
          var cloud = env.sprite("timber:cloud:" + cl, cw, cw * 0.5, paintCloud(5 + cl * 6));
          c.globalAlpha = 0.9;
          env.blit(c, cloud, ((now * (0.004 + cl * 0.002) + cl * 150) % (env.W + cw)) - cw, env.safeTop + 30 + cl * 62);
        }
        c.globalAlpha = 1;
        for (var bird = 0; bird < 2; bird++) {
          art.bird(c, ((now * (0.024 + bird * 0.008) + bird * 190) % (env.W + 60)) - 30, env.safeTop + 150 + bird * 44 + Math.sin(now / 600 + bird) * 8, 5 - bird, now / 120 + bird * 2, "rgba(40,60,80,.6)");
        }

        // تنه و شاخه‌ها (از پایین به بالا)، با انیمیشن پایین آمدن بعد از هر ضربه
        var offset = drop * SEG_H;
        var base = state.chops || 0;
        var i, y, seg;
        for (i = 0; i < state.segs.length + 6; i++) {
          y = gy - (i + 1) * SEG_H - offset;
          if (y < -SEG_H * 2) break;
          var variant = (base + i) % 4;
          env.blit(c, env.sprite("timber:seg:" + variant, TRUNK_W, SEG_H, paintSegment(variant)), cx - TRUNK_W / 2, y);
        }
        var branch = env.sprite("timber:branch", BRANCH_W + 24, 70, paintBranch, 6);
        for (i = 0; i < state.segs.length; i++) {
          seg = state.segs[i];
          y = gy - (i + 1) * SEG_H - offset;
          if (seg.b) {
            var dir = seg.b === 1 ? -1 : 1;
            c.save();
            c.translate(cx + dir * (TRUNK_W / 2 - 4), y + SEG_H / 2);
            c.scale(dir, 1);
            c.drawImage(branch.canvas, -branch.pad, -35 - branch.pad, branch.fw, branch.fh);
            c.restore();
          }
          if (seg.c) {
            var side = seg.c === 1 ? -1 : 1;
            var clockX = cx + side * (TRUNK_W / 2 + 36), clockY = y + SEG_H / 2 + Math.sin(env.now() / 260 + i) * 3;
            art.glow(c, clockX, clockY, 26, "#ffd257", 0.45);
            env.blitC(c, env.sprite("timber:clock", 32, 34, paintClock, 5), clockX, clockY);
          }
        }
        env.blit(c, env.sprite("timber:stump", TRUNK_W + 22, 26, paintStump), cx - TRUNK_W / 2 - 11, gy - 14);

        // تکه‌چوب‌های پرتاب‌شده
        for (var k = chips.length - 1; k >= 0; k--) {
          var chip = chips[k];
          chip.x += chip.vx;
          chip.y += chip.vy;
          chip.vy += 0.9;
          chip.rot += chip.vx * 0.035;
          chip.life -= 0.03;
          if (chip.life <= 0 || chip.y > env.H + 60) { chips.splice(k, 1); continue; }
          c.globalAlpha = Math.min(1, chip.life * 2);
          env.blitC(c, env.sprite("timber:seg:" + chip.variant, TRUNK_W, SEG_H, paintSegment(chip.variant)), chip.x, chip.y, chip.rot, 1, 0.6);
        }
        c.globalAlpha = 1;

        // هیزم‌شکن و تبرش
        var facing = state.side === 0 ? -1 : 1;
        // برگ‌های در حال افتادن (تاب‌خوران)
        for (var lf = leaves.length - 1; lf >= 0; lf--) {
          var leafItem = leaves[lf];
          leafItem.phase += 0.12;
          leafItem.x += leafItem.vx + Math.sin(leafItem.phase) * 0.9;
          leafItem.y += leafItem.vy;
          if (leafItem.y > gy + 6) leafItem.life -= 0.05;
          if (leafItem.life <= 0) { leaves.splice(lf, 1); continue; }
          c.save();
          c.globalAlpha = leafItem.life;
          c.translate(leafItem.x, Math.min(leafItem.y, gy + 6));
          c.rotate(Math.sin(leafItem.phase) * 0.9);
          c.fillStyle = lf % 2 ? "#3aa655" : "#6cc04a";
          c.beginPath();
          c.ellipse(0, 0, 5, 2.4, 0, 0, TAU);
          c.fill();
          c.restore();
        }
        c.globalAlpha = 1;
        var blink = fallen === 0 && now % 3100 < 140;
        var jack = env.sprite(blink ? "timber:jackBlink" : "timber:jack", 60, 106, paintJack(blink), 2);
        var breath = fallen > 0 ? 0 : Math.sin(now / 520) * 0.012;
        var axe = env.sprite("timber:axe", 60, 64, paintAxe, 2);
        c.save();
        c.translate(cx + facing * (TRUNK_W / 2 + 42), gy);
        if (fallen > 0) {
          c.translate(facing * fallen * 22, 0);
          c.rotate(facing * fallen * 1.45);
        }
        c.scale(facing, 1); // اسپرایت رو به چپ است؛ در سمت چپ تنه آینه می‌شود
        art.shadow(c, 0, 2, 26, 6, 0.4);
        c.rotate(-swing * 0.1); // هنگام ضربه کمی به سمت تنه خم می‌شود
        c.scale(1 - breath, 1 + breath);
        c.drawImage(jack.canvas, -30 - jack.pad, -104 - jack.pad, jack.fw, jack.fh);
        c.translate(-12, -44);
        c.rotate(0.85 - swing * 1.75);
        c.drawImage(axe.canvas, -30 - axe.pad, -56 - axe.pad, axe.fw, axe.fh);
        c.restore();

        // نوار زمان
        var bw = env.W - 96, bx = 48, by = env.safeTop + 8;
        c.fillStyle = "rgba(30,20,10,.65)";
        art.rr(c, bx - 3, by - 3, bw + 6, 20, 10);
        c.fill();
        var ratio = state.time / core.MAX_TIME;
        c.fillStyle = ratio < 0.25 ? "#ff5c7a" : ratio < 0.5 ? "#ffc233" : "#5ee6a8";
        art.rr(c, bx, by, Math.max(10, bw * ratio), 14, 7);
        c.fill();
        c.fillStyle = "rgba(255,255,255,.45)";
        c.fillRect(bx + 5, by + 2, Math.max(2, bw * ratio - 10), 2);
      },
    };
  });
})();
