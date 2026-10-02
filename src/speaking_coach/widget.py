BODY = (
    '<div id="root" class="grid"><div class="empty">…</div></div>'
    '<div class="muted footer">Practice tool. Not affiliated with or endorsed by IELTS, the British Council, '
    "IDP or Cambridge University Press &amp; Assessment. Scores are practice estimates, not official results.</div>"
)

EXTRA_CSS = """
.footer { margin-top: 12px; border-top: 1px solid var(--line); padding-top: 8px; }
ol { margin: 6px 0 0; padding-left: 20px; } ol li { margin: 3px 0; }
ul { margin: 6px 0 0; padding-left: 20px; }
.cue { border-left: 4px solid var(--accent); }
.timer { font-size: 28px; font-variant-numeric: tabular-nums; font-weight: 600; min-width: 80px; }
.bar { height: 10px; border-radius: 999px; background: var(--line); overflow: hidden; flex: 1; min-width: 120px; }
.bar > div { height: 100%; background: var(--accent); }
.crit { display: grid; grid-template-columns: minmax(140px, 1fr) 2fr 28px; gap: 8px; align-items: center; margin: 6px 0; }
.band { font-size: 32px; font-weight: 700; }
"""

SCRIPT = r"""
(function () {
  var el = plugkit.el;
  var tick = null;

  function stopTimer() { if (tick !== null) { clearInterval(tick); tick = null; } }
  function fmt(s) { var m = Math.floor(s / 60), r = s % 60; return m + ":" + (r < 10 ? "0" : "") + r; }

  function list(items) {
    return el("ol", {}, (items || []).map(function (q) { return el("li", { text: q }); }));
  }

  function timerBlock(c) {
    var display = el("div", { class: "timer", text: fmt(c.prep_seconds) });
    var status = el("div", { class: "muted", text: "No recording: answer in voice mode or type your talk." });
    function run(seconds, label, done) {
      stopTimer();
      var left = seconds;
      display.textContent = fmt(left);
      status.textContent = label;
      tick = setInterval(function () {
        left -= 1;
        display.textContent = fmt(Math.max(left, 0));
        if (left <= 0) { stopTimer(); status.textContent = done; }
      }, 1000);
    }
    var prep = el("button", { text: "Start 1-min preparation", onclick: function () {
      run(c.prep_seconds, "Preparing: make notes on the points above.", "Preparation time is over. Start speaking.");
    }});
    var speak = el("button", { class: "primary", text: "Start speaking", onclick: function () {
      run(c.speaking_seconds, "Speaking: keep talking until the timer ends.", "Time is up.");
    }});
    var reset = el("button", { text: "Stop", onclick: function () {
      stopTimer(); display.textContent = fmt(c.prep_seconds); status.textContent = "Timer stopped.";
    }});
    return el("div", { class: "row", style: "margin-top:10px" }, [display, prep, speak, reset, status]);
  }

  function test(d) {
    var out = [el("div", { class: "row" }, [el("h2", { text: "Speaking practice test" }), el("span", { class: "pill", text: d.test_id })])];
    if (d.part1) out.push(el("div", { class: "card" }, [
      el("strong", { text: "Part 1 · " + d.part1.topic }), list(d.part1.questions)]));
    if (d.part2) {
      var c = d.part2;
      out.push(el("div", { class: "card cue" }, [
        el("strong", { text: "Part 2 · cue card" }),
        el("div", { style: "margin-top:6px;font-size:15px", text: c.prompt }),
        el("div", { class: "muted", style: "margin-top:6px", text: "You should say:" }),
        el("ul", {}, c.bullets.map(function (b) { return el("li", { text: b }); })),
        el("div", { style: "margin-top:4px", text: c.final }),
        timerBlock(c)
      ]));
    }
    if (d.part3) out.push(el("div", { class: "card" }, [
      el("strong", { text: "Part 3 · discussion: " + d.part3.topic }), list(d.part3.questions)]));
    return out;
  }

  function counts(items, key) {
    if (!items || !items.length) return "none";
    return items.map(function (x) { return x[key] + " ×" + x.count; }).join(", ");
  }

  function analysis(d) {
    var rows = [
      ["Words", String(d.word_count)],
      ["Sentences", String(d.sentence_count)],
      ["Average sentence length", d.avg_sentence_length + " words"],
      ["Unique words", String(d.unique_words)],
      ["Type-token ratio", String(d.type_token_ratio)],
      ["Fillers (" + d.filler_total + ")", counts(d.fillers, "item")],
      ["Linking devices (" + d.linking_total + ")", counts(d.linking_devices, "item")],
      ["Most repeated words", counts(d.repeated_words, "word")]
    ];
    if (d.words_per_minute !== null && d.words_per_minute !== undefined)
      rows.push(["Words per minute", d.words_per_minute + " (" + d.duration_seconds + " s)"]);
    var out = [
      el("h2", { text: "Transcript analysis · Part " + d.part }),
      el("table", {}, [el("tbody", {}, rows.map(function (r) {
        return el("tr", {}, [el("th", { text: r[0] }), el("td", { text: r[1] })]);
      }))])
    ];
    if (d.part2_length_note) out.push(el("div", { class: "card", text: d.part2_length_note }));
    out.push(el("ul", { class: "muted" }, (d.notes || []).map(function (n) { return el("li", { text: n }); })));
    out.push(el("div", { class: "muted", text: "Counts only — no band judgement." }));
    return out;
  }

  function scores(d) {
    var bars = d.criteria.map(function (c) {
      var v = c.assessed ? Math.max(0, Math.min(9, Number(c.score))) : 0;
      return el("div", { class: "crit" }, [
        el("span", { text: c.name }),
        el("div", { class: "bar" }, [el("div", { style: "width:" + (v / 9 * 100).toFixed(1) + "%" })]),
        el("strong", { text: c.assessed ? String(v) : "–" })
      ]);
    });
    var band = d.estimated_band === null || d.estimated_band === undefined
      ? el("div", {}, [el("div", { class: "band", text: "not assessed" }),
          el("div", { class: "muted", text: "Pronunciation was not assessed, so no band is estimated." })])
      : el("div", {}, [el("div", { class: "band", text: Number(d.estimated_band).toFixed(1) }),
          el("div", { class: "muted", text: "Estimated practice band" })]);
    var out = [
      el("h2", { text: "Speaking feedback" }),
      el("div", { class: "card" }, bars.concat([
        el("div", { class: "row", style: "justify-content:space-between;margin-top:8px" }, [
          el("div", { text: "Average of " + d.criteria_assessed + " criteria: " + d.average }), band
        ])
      ]))
    ];
    if (d.strengths && d.strengths.length) out.push(el("div", { class: "card" }, [
      el("strong", { class: "ok", text: "Strengths" }),
      el("ul", {}, d.strengths.map(function (s) { return el("li", { text: s }); }))]));
    if (d.improvements && d.improvements.length) out.push(el("div", { class: "card" }, [
      el("strong", { class: "warn", text: "To improve" }),
      el("ul", {}, d.improvements.map(function (s) { return el("li", { text: s }); }))]));
    if (d.better_answer_example) out.push(el("div", { class: "card" }, [
      el("strong", { text: "A stronger answer" }),
      el("div", { style: "white-space:pre-wrap;margin-top:6px", text: d.better_answer_example })]));
    out.push(el("div", { class: "muted", text: d.rounding_note }));
    // The page footer already carries the not-affiliated disclaimer; the score's
    // own disclaimer is in the tool text for the model, so it is not repeated here.
    return out;
  }

  var VIEWS = { test: test, analysis: analysis, scores: scores };

  plugkit.onData(function (d) {
    stopTimer();
    var root = document.getElementById("root");
    var view = VIEWS[d && d.kind];
    root.replaceChildren.apply(root, view ? view(d) : [el("div", { class: "empty", text: "Nothing to show." })]);
  });
  window.addEventListener("pagehide", stopTimer);
})();
"""
