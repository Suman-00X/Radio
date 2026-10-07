/* The recruiter tour's live test run, played as a short film: a title card and countdown, the run with every
 * result landing on screen as the server streams it, then a finale with the totals.
 * The stream is read with fetch rather than EventSource, which would quietly reconnect and start a second run. */

(() => {
  const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const PER_FRAME = 6;
  const LOG_LINES = 9;

  const el = (tag, cls, html) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (html != null) node.innerHTML = html;
    return node;
  };
  const esc = (text) => String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const fmt = (n) => n.toLocaleString("en-US");
  const clock = (ms) => {
    const s = Math.max(0, ms / 1000);
    return s < 60 ? `${s.toFixed(1)}s` : `${Math.floor(s / 60)}m ${String(Math.floor(s % 60)).padStart(2, "0")}s`;
  };
  const label = { passed: "PASS", failed: "FAIL", error: "ERROR", skipped: "SKIP" };

  function play(card, opener) {
    const url = card.dataset.testRun;
    const abort = new AbortController();
    const state = { total: 0, done: 0, passed: 0, failed: 0, skipped: 0, error: 0, failures: [], queue: [], summary: null, problem: null, started: 0, shown: 0 };
    let scene = "intro";
    let raf = 0;
    let closed = false;

    const root = el("div", "st");
    root.setAttribute("role", "dialog");
    root.setAttribute("aria-modal", "true");
    root.setAttribute("aria-label", "Live test run");
    root.innerHTML = `
      <div class="st-bar st-bar-top"></div><div class="st-bar st-bar-bottom"></div>
      <div class="st-grain"></div><div class="st-scan"></div><div class="st-vignette"></div><div class="st-flash"></div>
      <canvas class="st-sparks"></canvas>
      <button type="button" class="st-close" data-st-close>Close <kbd>Esc</kbd></button>
      <section class="st-scene st-intro on">
        <div>
          <div class="st-presents">radreport presents</div>
          <div class="st-title">The test suite</div>
          <div class="st-tagline">Every test · one take · no edits</div>
          <div class="st-leader"><span class="st-count">3</span></div>
        </div>
      </section>
      <section class="st-scene st-run" aria-live="off">
        <div class="st-hud">
          <div class="st-now"><b>Rolling</b><span class="st-file">collecting tests…</span></div>
          <div>
            <div class="st-big"><span class="st-pct">0</span><span class="st-pct-sign">%</span></div>
            <div class="st-meter"><i></i></div>
            <div class="st-tally">
              <div class="pass"><strong data-n="passed">0</strong><span>Passed</span></div>
              <div class="fail"><strong data-n="failed">0</strong><span>Failed</span></div>
              <div class="skip"><strong data-n="skipped">0</strong><span>Skipped</span></div>
              <div class="time"><strong data-n="clock">0.0s</strong><span>Elapsed</span></div>
            </div>
          </div>
          <div class="st-board"><div class="st-grid"></div><ol class="st-log"></ol></div>
        </div>
      </section>
      <section class="st-scene st-final" aria-live="polite"></section>`;
    document.body.append(root);
    const $ = (sel) => root.querySelector(sel);
    const scenes = { intro: $(".st-intro"), run: $(".st-run"), final: $(".st-final") };
    const grid = $(".st-grid");
    const log = $(".st-log");
    const previousOverflow = document.documentElement.style.overflow;
    document.documentElement.style.overflow = "hidden";
    $("[data-st-close]").focus();
    requestAnimationFrame(() => root.classList.add("st-letterbox"));

    const show = (name) => {
      scene = name;
      Object.entries(scenes).forEach(([key, node]) => node.classList.toggle("on", key === name));
    };

    function close() {
      if (closed) return;
      closed = true;
      abort.abort();
      cancelAnimationFrame(raf);
      document.removeEventListener("keydown", onKey);
      root.classList.add("st-out");
      setTimeout(() => {
        root.remove();
        document.documentElement.style.overflow = previousOverflow;
        opener?.focus();
      }, REDUCED ? 0 : 420);
    }
    const onKey = (e) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", onKey);
    root.addEventListener("click", (e) => {
      if (e.target.closest("[data-st-close]")) close();
      if (e.target.closest("[data-st-again]")) {
        close();
        setTimeout(() => play(card, opener), REDUCED ? 0 : 450);
      }
    });

    // The countdown runs while the server collects the tests, so the film never waits on the suite.
    const countdown = new Promise((resolve) => {
      if (REDUCED) return resolve();
      const leader = $(".st-leader");
      const count = $(".st-count");
      const begin = performance.now() + 1700;
      let last = 4;
      const step = (now) => {
        if (closed) return resolve();
        const t = Math.max(0, now - begin);
        const n = 3 - Math.floor(t / 800);
        leader.style.setProperty("--sweep", `${((t % 800) / 800) * 360}deg`);
        if (n !== last && n > 0) {
          last = n;
          count.textContent = n;
          count.classList.remove("tick");
          void count.offsetWidth;
          count.classList.add("tick");
        }
        if (n <= 0) return resolve();
        requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });

    function take(event) {
      if (event.type === "start") {
        state.total = event.total;
        state.started = performance.now();
        grid.replaceChildren(...Array.from({ length: event.total }, () => document.createElement("i")));
      } else if (event.type === "test") state.queue.push(event);
      else if (event.type === "done") state.summary = event;
      else if (event.type === "busy") state.problem = "Another visitor's run is still going. Give it half a minute, then try again.";
    }

    async function stream() {
      let response;
      try {
        response = await fetch(url, { signal: abort.signal, headers: { Accept: "text/event-stream" } });
      } catch (err) {
        if (!closed) state.problem = "The server could not be reached.";
        return;
      }
      if (!response.ok || !response.body) {
        state.problem = response.status === 429 ? "That is a lot of runs from one address. Try again in a few minutes." : response.status === 404 ? "This deployment does not offer the live test run." : `The server answered ${response.status}.`;
        return;
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      try {
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let cut;
          while ((cut = buffer.indexOf("\n\n")) >= 0) {
            const chunk = buffer.slice(0, cut);
            buffer = buffer.slice(cut + 2);
            const data = chunk.split("\n").filter((line) => line.startsWith("data: ")).map((line) => line.slice(6)).join("");
            if (data) take(JSON.parse(data));
          }
        }
      } catch (err) {
        if (!closed && !state.summary) state.problem = "The connection dropped before the run finished.";
      }
      if (!closed && !state.summary && !state.problem) state.problem = "The run ended without a summary.";
    }

    function land(event) {
      state.done += 1;
      state[event.outcome] = (state[event.outcome] || 0) + 1;
      if (event.outcome === "failed" || event.outcome === "error") state.failures.push(event.id);
      const cell = grid.children[state.done - 1];
      if (cell) cell.className = event.outcome;
      const [file, ...rest] = event.id.split("::");
      $(".st-file").textContent = file;
      const line = el("li", event.outcome, `<b>${label[event.outcome] || esc(event.outcome).toUpperCase()}</b>${esc(rest.join("::") || file)}`);
      log.prepend(line);
      while (log.children.length > LOG_LINES) log.lastElementChild.remove();
    }

    function paint() {
      const target = state.total ? state.done / state.total : 0;
      state.shown += (target - state.shown) * (REDUCED ? 1 : 0.18);
      if (Math.abs(target - state.shown) < 0.0005) state.shown = target;
      $(".st-pct").textContent = Math.floor(state.shown * 100);
      $(".st-meter i").style.width = `${state.shown * 100}%`;
      for (const key of ["passed", "failed", "skipped"]) $(`[data-n="${key}"]`).textContent = fmt(state[key] + (key === "failed" ? state.error : 0));
      if (state.started) $('[data-n="clock"]').textContent = clock((state.summary ? state.summary.seconds * 1000 : performance.now() - state.started));
    }

    function loop() {
      if (closed) return;
      if (state.problem && scene !== "final") return finale();
      if (scene === "run") {
        const burst = state.queue.length > 120 ? 40 : PER_FRAME;
        for (let i = 0; i < burst && state.queue.length; i += 1) land(state.queue.shift());
        paint();
        if (state.summary && !state.queue.length && state.shown >= 0.999) return finale();
      }
      raf = requestAnimationFrame(loop);
    }

    function finale() {
      const s = state.summary;
      const bad = state.failed + state.error;
      const final = scenes.final;
      if (state.problem) {
        final.innerHTML = `<div><div class="st-final-eyebrow">Cut</div><h2>Run stopped</h2><p class="st-final-sub">${esc(state.problem)}</p>
          <div class="st-final-actions"><button type="button" class="st-primary" data-st-close>Back to the tour</button></div></div>`;
      } else {
        const counts = `<b>${fmt(state.passed)} passed</b> · ${fmt(state.skipped)} skipped · ${bad ? `<em>${fmt(bad)} failed</em>` : "0 failed"} · ${clock(s.seconds * 1000)}`;
        const verdict = s.timeout ? '<div class="st-verdict bad">Stopped at the time limit</div>' : bad ? `<div class="st-verdict bad">✕ ${fmt(bad)} need${bad === 1 ? "s" : ""} attention</div>` : '<div class="st-verdict">✓ Every test that ran passed</div>';
        const failures = state.failures.length ? `<ol class="st-failures">${state.failures.map((id) => `<li>${esc(id)}</li>`).join("")}</ol>` : "";
        final.innerHTML = `<div>
          <div class="st-final-eyebrow st-reveal">${fmt(state.done)} of ${fmt(state.total)} · that's a wrap</div>
          <h2>All tests completed</h2>
          <p class="st-final-sub st-reveal" style="animation-delay:.9s">${counts}</p>
          <div class="st-reveal" style="animation-delay:1.3s">${verdict}</div>${failures}
          <div class="st-final-actions st-reveal" style="animation-delay:1.7s"><button type="button" class="st-primary" data-st-close>Back to the tour</button><button type="button" data-st-again>Run it again</button></div>
        </div>`;
        if (!REDUCED) {
          const flash = $(".st-flash");
          flash.classList.add("go");
          if (!bad) sparks($(".st-sparks"));
        }
      }
      show("final");
      final.querySelector("button")?.focus();
    }

    countdown.then(() => {
      if (closed) return;
      show("run");
      raf = requestAnimationFrame(loop);
    });
    stream();
  }

  // Gold and cyan sparks bursting from the title, falling under a little gravity, then gone.
  function sparks(canvas) {
    const ratio = window.devicePixelRatio || 1;
    const w = (canvas.width = canvas.clientWidth * ratio);
    const h = (canvas.height = canvas.clientHeight * ratio);
    const ctx = canvas.getContext("2d");
    const colors = ["#f6c86a", "#fff1c9", "#5ee7ff", "#3ef0a1", "#ffffff"];
    const bits = [];
    const burst = (x, y, n) => {
      for (let i = 0; i < n; i += 1) {
        const a = Math.random() * Math.PI * 2;
        const v = (2 + Math.random() * 9) * ratio;
        bits.push({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v - 3 * ratio, life: 1, decay: 0.008 + Math.random() * 0.014, size: (1 + Math.random() * 2.6) * ratio, color: colors[(Math.random() * colors.length) | 0] });
      }
    };
    burst(w / 2, h * 0.42, 220);
    setTimeout(() => burst(w * 0.22, h * 0.36, 120), 420);
    setTimeout(() => burst(w * 0.78, h * 0.36, 120), 760);
    const frame = () => {
      if (!canvas.isConnected) return;
      ctx.clearRect(0, 0, w, h);
      ctx.globalCompositeOperation = "lighter";
      for (let i = bits.length - 1; i >= 0; i -= 1) {
        const b = bits[i];
        b.x += b.vx;
        b.y += b.vy;
        b.vx *= 0.985;
        b.vy = b.vy * 0.985 + 0.12 * ratio;
        b.life -= b.decay;
        if (b.life <= 0) {
          bits.splice(i, 1);
          continue;
        }
        ctx.globalAlpha = Math.max(0, b.life);
        ctx.fillStyle = b.color;
        ctx.beginPath();
        ctx.arc(b.x, b.y, b.size, 0, Math.PI * 2);
        ctx.fill();
      }
      if (bits.length) requestAnimationFrame(frame);
      else ctx.clearRect(0, 0, w, h);
    };
    requestAnimationFrame(frame);
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-test-run]").forEach((card) => {
      const button = card.querySelector("[data-test-run-go]");
      button?.addEventListener("click", () => play(card, button));
    });
  });
})();
