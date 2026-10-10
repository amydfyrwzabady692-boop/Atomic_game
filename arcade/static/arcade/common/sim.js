/* اجرای قطعی یک لاگ ورودی روی core بازی — معادل ArcadeSimulator.simulate در پایتون.
   هم در مرورگر (صفحه‌ی تست تطابق) و هم در Node (CI) استفاده می‌شود. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.ArcadeSim = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var MAX_DURATION_MS = 10 * 60 * 1000;

  function simulate(core, seed, inputs, durationMs, config) {
    var state = core.newState(seed, config || {});
    var tickMs = core.TICK_MS;
    var maxMs = core.MAX_DURATION_MS || MAX_DURATION_MS;
    var endTick = Math.floor(Math.min(durationMs, maxMs) / tickMs);
    var index = 0;
    var tick = 0;
    for (;;) {
      while (index < inputs.length && Math.floor(inputs[index][0] / tickMs) <= tick) {
        if (!state.over) core.applyInput(state, inputs[index]);
        index++;
      }
      if (state.over || tick >= endTick) break;
      core.step(state);
      tick++;
    }
    return {
      score: state.score,
      level: state.level || 0,
      duration_ms: tick * tickMs,
      over: !!state.over,
      cause: state.cause || "",
    };
  }

  return { simulate: simulate };
});
