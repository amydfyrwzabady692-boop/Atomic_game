/* «برج‌ساز» — رندر و افکت‌ها: هر بلوک یک طبقه‌ی برج است با نمای بتنی و پنجره‌های شیشه‌ای که جرثقیل
   پایین می‌آورد؛ آسمان با بالا رفتن برج از روز به شب می‌رسد و پنجره‌ها روشن می‌شوند. ابرها، پرنده‌ها و
   شهر دوردست با پارالاکس حرکت می‌کنند. */
(function () {
  "use strict";
  Arcade.registerRenderer("stack", function (env) {
    var art = env.art;
    var BLOCK_H = 30, DEPTH = 10;
    var PITCH = 20; // فاصله‌ی افقی پنجره‌ها
    var FACADE_W = 560; // عرض نوار نما (بیشتر از پهن‌ترین طبقه + جابه‌جایی الگو)
    var nightAmount = 0;
    var camera = 0; // تعداد بلوک‌هایی که دوربین بالا رفته (نرم)
    var falling = []; // تکه‌های بریده‌شده‌ی در حال سقوط
    var pulses = []; // قاب نورانی بعد از ضربه‌ی دقیق
    var settle = 0; // فرو نشستن کوتاه بلوک تازه
    var palette = [];

    function colors(index) {
      var hit = palette[index];
      if (hit) return hit;
      var hue = (index * 9 + 196) % 360;
      hit = palette[index] = {
        top: "hsl(" + hue + ",34%,84%)",
        tint: "hsla(" + hue + ",85%,58%,.24)",
        side: "hsl(" + hue + ",26%,42%)",
        glow: "hsl(" + hue + ",90%,70%)",
      };
      return hit;
    }
    function baseY() {
      return env.H - 150;
    }

    // ---------------------------------------------------------------- اسپرایت‌ها
    /* سایه‌روشن وجه جلوی بلوک (روی رنگ تخت کشیده و در عرض کشیده می‌شود) */
    function paintShade(c, w, h) {
      var g = c.createLinearGradient(0, 0, 0, h);
      g.addColorStop(0, "rgba(255,255,255,.34)");
      g.addColorStop(0.1, "rgba(255,255,255,.1)");
      g.addColorStop(0.5, "rgba(255,255,255,0)");
      g.addColorStop(1, "rgba(0,0,20,.34)");
      c.fillStyle = g;
      c.fillRect(0, 0, w + 1, h);
      c.fillStyle = "rgba(255,255,255,.5)";
      c.fillRect(0, 0, w, 1);
      c.fillStyle = "rgba(0,0,20,.35)";
      c.fillRect(0, h - 1, w, 1);
    }
    /* نمای یک طبقه: بتن روشن با یک ردیف پنجره‌ی شیشه‌ای */
    function paintFacade(c, w, h) {
      var wall = c.createLinearGradient(0, 0, 0, h);
      wall.addColorStop(0, "#dfe4ec");
      wall.addColorStop(1, "#b3bcc9");
      c.fillStyle = wall;
      c.fillRect(0, 0, w + 1, h);
      c.fillStyle = "#eef1f6";
      c.fillRect(0, 0, w + 1, 4);
      c.fillStyle = "rgba(60,70,90,.45)";
      c.fillRect(0, 4, w + 1, 1);
      c.fillStyle = "#8a94a3";
      c.fillRect(0, h - 3, w + 1, 3);
      for (var x = 4; x < w; x += PITCH) {
        var glass = c.createLinearGradient(0, 7, 0, 24);
        glass.addColorStop(0, "#a9dcfa");
        glass.addColorStop(0.5, "#4f97cc");
        glass.addColorStop(1, "#28587f");
        c.fillStyle = glass;
        c.fillRect(x, 7, 12, 17);
        // بازتاب مورب آسمان روی شیشه
        c.fillStyle = "rgba(255,255,255,.4)";
        c.beginPath();
        c.moveTo(x + 1, 8);
        c.lineTo(x + 6, 8);
        c.lineTo(x + 1, 17);
        c.closePath();
        c.fill();
        c.strokeStyle = "#3b4656";
        c.lineWidth = 1;
        c.strokeRect(x + 0.5, 7.5, 11, 16);
        c.fillStyle = "#3b4656";
        c.fillRect(x + 5.6, 7, 0.9, 17);
      }
    }
    /* پنجره‌های روشن شب (روی نما کشیده می‌شود)؛ بعضی خاموش‌اند */
    function paintLitWindows(c, w) {
      var rnd = art.rand(77);
      for (var x = 4; x < w; x += PITCH) {
        if (rnd() < 0.38) continue;
        var warm = c.createLinearGradient(0, 7, 0, 24);
        warm.addColorStop(0, "#fff3c2");
        warm.addColorStop(1, rnd() < 0.5 ? "#ffb347" : "#ffd27a");
        c.fillStyle = warm;
        c.fillRect(x + 1, 8, 10, 15);
        c.fillStyle = "rgba(90,50,10,.55)";
        c.fillRect(x + 5.6, 8, 0.9, 15);
      }
    }
    function sky(top, mid, bottom) {
      return function (c, w, h) {
        var g = c.createLinearGradient(0, 0, 0, h);
        g.addColorStop(0, top);
        g.addColorStop(0.6, mid);
        g.addColorStop(1, bottom);
        c.fillStyle = g;
        c.fillRect(-1, -1, w + 2, h + 2); // تا آخرین پیکسل اسپرایت هم پر شود
      };
    }
    function paintStars(c, w, h) {
      var rnd = art.rand(42);
      for (var i = 0; i < 90; i++) {
        c.globalAlpha = 0.3 + rnd() * 0.7;
        c.fillStyle = rnd() < 0.2 ? "#ffe9b0" : "#ffffff";
        var s = 0.5 + rnd() * 1.3;
        c.fillRect(rnd() * w, rnd() * h, s, s);
      }
      c.globalAlpha = 1;
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
        c.arc(m + craters[i][0] * r, m + craters[i][1] * r, craters[i][2] * r, 0, Math.PI * 2);
        c.fill();
      }
    }
    function paintSkyline(c, w, h) {
      var rnd = art.rand(8);
      for (var layer = 0; layer < 2; layer++) {
        var x = -10;
        while (x < w + 10) {
          var bw = 22 + rnd() * 30, bh = h * (layer ? 0.35 + rnd() * 0.4 : 0.55 + rnd() * 0.45);
          c.fillStyle = layer ? "rgba(46,64,110,.92)" : "rgba(88,116,170,.6)";
          c.fillRect(x, h - bh, bw, bh);
          if (layer) {
            c.fillStyle = "rgba(255,226,150,.5)";
            for (var wy = h - bh + 6; wy < h - 8; wy += 9) {
              for (var wx = x + 4; wx < x + bw - 5; wx += 7) if (rnd() < 0.4) c.fillRect(wx, wy, 3, 4);
            }
          }
          x += bw + rnd() * 6;
        }
      }
    }
    function paintGround(c, w, h) {
      // سکوی بتنی
      var g = c.createLinearGradient(0, 0, 0, h);
      g.addColorStop(0, "#8c95a6");
      g.addColorStop(0.06, "#5d6676");
      g.addColorStop(1, "#262b38");
      c.fillStyle = g;
      c.fillRect(0, 0, w, h);
      art.speckle(c, 0, 0, w, h, "#ffffff", 240, 4);
      art.speckle(c, 0, 0, w, h, "#000000", 300, 6);
      c.fillStyle = "rgba(255,255,255,.4)";
      c.fillRect(0, 0, w, 1.5);
      c.fillStyle = "rgba(0,0,0,.28)";
      for (var x = 40; x < w; x += 90) c.fillRect(x, 0, 1.2, h);
    }

    function slab(c, x, w, y, index, a) {
      var col = colors(index);
      if (a !== undefined) c.globalAlpha = a;
      c.fillStyle = col.top;
      c.beginPath();
      c.moveTo(x, y);
      c.lineTo(x + DEPTH, y - DEPTH);
      c.lineTo(x + w + DEPTH, y - DEPTH);
      c.lineTo(x + w, y);
      c.closePath();
      c.fill();
      c.fillStyle = col.side;
      c.beginPath();
      c.moveTo(x + w, y);
      c.lineTo(x + w + DEPTH, y - DEPTH);
      c.lineTo(x + w + DEPTH, y - DEPTH + BLOCK_H);
      c.lineTo(x + w, y + BLOCK_H);
      c.closePath();
      c.fill();
      // نمای طبقه: تکه‌ای از نوار پنجره‌ها که با شبکه‌ی پنجره‌های کل برج هم‌تراز است
      var facade = env.sprite("stack:facade", FACADE_W, BLOCK_H, paintFacade);
      var px = facade.canvas.width / FACADE_W;
      var sx = ((x % PITCH) + PITCH) % PITCH;
      c.drawImage(facade.canvas, sx * px, 0, w * px, facade.canvas.height, x, y, w, BLOCK_H);
      c.fillStyle = col.tint;
      c.fillRect(x, y, w, BLOCK_H);
      if (nightAmount > 0.02) {
        c.fillStyle = "rgba(8,12,40," + nightAmount * 0.42 + ")";
        c.fillRect(x, y, w, BLOCK_H);
        var lit = env.sprite("stack:lit", FACADE_W, BLOCK_H, paintLitWindows);
        var before = c.globalAlpha;
        c.globalAlpha = before * nightAmount;
        // هر طبقه الگوی روشنایی خودش را دارد
        c.drawImage(lit.canvas, (sx + ((index * 7) % 8) * PITCH) * px, 0, w * px, lit.canvas.height, x, y, w, BLOCK_H);
        c.globalAlpha = before;
      }
      var shade = env.sprite("stack:shade", 8, BLOCK_H, paintShade);
      c.drawImage(shade.canvas, x, y, w, BLOCK_H);
      if (a !== undefined) c.globalAlpha = 1;
    }

    return {
      controls: "tap",
      ownBackground: true,
      reset: function () {
        camera = 0;
        falling = [];
        pulses = [];
        settle = 0;
      },
      input: function (kind) {
        return kind === "tap" ? [] : null;
      },
      hud: function (state) {
        return state && state.combo > 1 ? "کمبو ×" + env.fa(state.combo) : "";
      },
      event: function (name, state) {
        var top = state.blocks[state.blocks.length - 1];
        var y = baseY() - (state.blocks.length - 1 - camera) * BLOCK_H;
        if (name === "perfect") {
          settle = 1;
          pulses.push({ x: top.x / 10, w: top.w / 10, y: y, life: 1 });
          env.fx.burst((top.x + top.w / 2) / 10, y, "#fff6cf", 12, 3);
          env.fx.text(env.W / 2, y - 30, state.combo > 1 ? "عالی! ×" + env.fa(state.combo) : "عالی!", env.colors.gold);
          env.haptic("medium");
          env.sound("bonus");
        } else if (name === "cut") {
          settle = 1;
          env.fx.burst((top.x + top.w / 2) / 10, y + BLOCK_H, "#ffffff", 5, 1.8);
          if (state.lastCut) {
            var right = state.lastCut.x > top.x;
            falling.push({ x: state.lastCut.x / 10, w: state.lastCut.w / 10, y: y, vy: 0, vx: right ? 1.1 : -1.1, rot: 0, spin: right ? 0.03 : -0.03, index: state.blocks.length - 1 });
          }
          env.haptic("light");
          env.sound("tap");
        } else if (name === "fail") {
          if (state.lastCut) {
            falling.push({ x: state.lastCut.x / 10, w: state.lastCut.w / 10, y: y - BLOCK_H, vy: 0, vx: 0, rot: 0, spin: 0.02, index: state.blocks.length });
          }
          env.fx.flash(env.colors.danger, 0.45);
          env.fx.shake(9);
          env.haptic("error");
          env.sound("bad");
        }
      },
      draw: function (c, state, alpha) {
        var count = state.blocks.length;
        var target = Math.max(0, count - 7);
        camera += (target - camera) * 0.12;
        settle *= 0.72;
        var by = baseY();
        var W = env.W, H = env.H, i;

        // آسمان: روز ← غروب ← شب
        var dusk = env.clamp((camera - 8) / 14, 0, 1), night = env.clamp((camera - 30) / 18, 0, 1);
        nightAmount = Math.max(night, dusk * 0.45); // پنجره‌ها از غروب کم‌کم روشن می‌شوند
        var day = env.sprite("stack:day", 4, H, sky("#3f97ea", "#8ecbf7", "#d7efff"));
        c.drawImage(day.canvas, -12, -12, W + 24, H + 24);
        if (dusk > 0) {
          c.globalAlpha = dusk;
          c.drawImage(env.sprite("stack:dusk", 4, H, sky("#2a2d78", "#b9508f", "#ffb56e")).canvas, -12, -12, W + 24, H + 24);
        }
        if (night > 0) {
          c.globalAlpha = night;
          c.drawImage(env.sprite("stack:night", 4, H, sky("#04061a", "#10143a", "#272c66")).canvas, -12, -12, W + 24, H + 24);
          env.blit(c, env.sprite("stack:stars", W, H, paintStars), 0, 0);
        }
        c.globalAlpha = 1;

        // ابرها (پارالاکس آهسته) و شهر دوردست
        var drift = env.now() / 1000;
        c.globalAlpha = 1 - night;
        for (i = 0; i < 5 && night < 1; i++) {
          var big = i % 2 === 0;
          var cw = big ? 120 : 84;
          var cloud = env.sprite(big ? "stack:cloudA" : "stack:cloudB", cw, cw * 0.5, function (s, w) { art.cloud(s, 0, 0, w, "#ffffff", "#a9bde0", big ? 4 : 9); });
          var span = H + 160;
          var cy = ((i * 173 + camera * BLOCK_H * (0.25 + i * 0.04)) % span) - 80;
          var cx = ((i * 131 + drift * (4 + i * 2)) % (W + cw)) - cw;
          env.blit(c, cloud, cx, cy);
        }
        c.globalAlpha = 1;
        var nowMs = env.now();
        // پرنده‌ها در روز، ماه و شهاب در شب
        if (dusk < 1) {
          for (i = 0; i < 3; i++) {
            art.bird(c, ((nowMs * (0.02 + i * 0.007) + i * 150) % (W + 60)) - 30, env.safeTop + 70 + i * 52 + Math.sin(nowMs / 600 + i) * 7, 5.5 - i, nowMs / 120 + i * 2, "rgba(30,50,90," + 0.55 * (1 - dusk) + ")");
          }
        }
        if (night > 0) {
          c.globalAlpha = night;
          env.blit(c, env.sprite("stack:moon", 96, 96, paintMoon), W - 118, env.safeTop + 18);
          var shoot = (nowMs % 5200) / 620;
          if (shoot < 1) {
            var sx0 = 40 + ((Math.floor(nowMs / 5200) * 97) % 180), sy0 = env.safeTop + 40 + ((Math.floor(nowMs / 5200) * 53) % 120);
            c.globalAlpha = night * Math.sin(shoot * Math.PI);
            c.strokeStyle = "#ffffff";
            c.lineWidth = 1.6;
            c.lineCap = "round";
            c.beginPath();
            c.moveTo(sx0 + shoot * 120, sy0 + shoot * 60);
            c.lineTo(sx0 + shoot * 120 - 34, sy0 + shoot * 60 - 17);
            c.stroke();
          }
          c.globalAlpha = 1;
        }
        var groundTop = by + BLOCK_H + camera * BLOCK_H;
        var cityY = by + BLOCK_H - 132 + camera * BLOCK_H * 0.55;
        if (cityY < H + 12) env.blit(c, env.sprite("stack:city", W + 24, 132, paintSkyline), -12, cityY);
        if (groundTop < H + 12) {
          env.blit(c, env.sprite("stack:ground", W + 24, 190, paintGround), -12, groundTop);
          art.shadow(c, W / 2 + 8, groundTop + 3, 118, 9, 0.5);
        }

        // برج
        var first = Math.max(0, Math.floor(camera) - 6);
        for (i = first; i < count; i++) {
          var b = state.blocks[i];
          var y = by - (i - camera) * BLOCK_H;
          if (i === count - 1) y += settle * 4;
          if (y > H + 20) continue;
          slab(c, b.x / 10, b.w / 10, y, i);
        }

        var topBlock = state.blocks[count - 1];
        var topY = by - (count - 1 - camera) * BLOCK_H;

        // قاب نورانی ضربه‌ی دقیق
        for (i = pulses.length - 1; i >= 0; i--) {
          var pulse = pulses[i];
          pulse.life -= 0.045;
          if (pulse.life <= 0) { pulses.splice(i, 1); continue; }
          var grow = (1 - pulse.life) * 16;
          c.globalAlpha = pulse.life;
          c.strokeStyle = "#fff6cf";
          c.lineWidth = 3 * pulse.life + 0.5;
          c.strokeRect(pulse.x - grow, pulse.y - grow * 0.5, pulse.w + grow * 2, BLOCK_H + grow);
          c.globalAlpha = 1;
        }

        // بلوک متحرک و سایه‌اش روی سر برج
        if (!state.over && state.cur) {
          var cur = state.cur;
          var x = (cur.x + cur.dir * cur.speed * alpha) / 10, w = cur.w / 10;
          var sl = Math.max(x, topBlock.x / 10), sr = Math.min(x + w, (topBlock.x + topBlock.w) / 10);
          if (sr > sl) {
            c.fillStyle = "rgba(0,0,30,.22)";
            c.beginPath();
            c.moveTo(sl, topY);
            c.lineTo(sl + DEPTH, topY - DEPTH);
            c.lineTo(sr + DEPTH, topY - DEPTH);
            c.lineTo(sr, topY);
            c.closePath();
            c.fill();
          }
          var hover = topY - BLOCK_H - 6;
          // کابل‌ها و قلاب جرثقیل که طبقه را نگه داشته
          var hookX = x + w / 2 + DEPTH / 2, hookY = hover - 46;
          c.strokeStyle = "rgba(30,36,48,.85)";
          c.lineWidth = 1.4;
          c.beginPath();
          c.moveTo(x + 6, hover - DEPTH / 2);
          c.lineTo(hookX, hookY);
          c.lineTo(x + w + DEPTH - 6, hover - DEPTH / 2);
          c.moveTo(hookX, hookY);
          c.lineTo(hookX, -20);
          c.stroke();
          c.fillStyle = "#f4b400";
          c.fillRect(hookX - 5, hookY - 7, 10, 9);
          c.fillStyle = "rgba(0,0,0,.3)";
          c.fillRect(hookX - 5, hookY, 10, 2);
          art.glow(c, x + w / 2, hover + BLOCK_H / 2, Math.max(w * 0.75, 40), colors(count).glow, 0.22);
          slab(c, x, w, hover, count);
        }

        // تکه‌های بریده‌شده
        for (i = falling.length - 1; i >= 0; i--) {
          var piece = falling[i];
          piece.vy += 0.55;
          piece.y += piece.vy;
          piece.x += piece.vx;
          piece.rot += piece.spin;
          if (piece.y > H + 80) { falling.splice(i, 1); continue; }
          c.save();
          c.translate(piece.x + piece.w / 2, piece.y + BLOCK_H / 2);
          c.rotate(piece.rot);
          slab(c, -piece.w / 2, piece.w, -BLOCK_H / 2, piece.index, 0.92);
          c.restore();
        }
      },
    };
  });
})();
