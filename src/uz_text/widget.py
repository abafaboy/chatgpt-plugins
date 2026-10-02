BODY = '<div id="root" class="grid"><div class="empty">…</div></div>'

SCRIPT = r"""
(function () {
  var el = plugkit.el;
  var LABELS = { latin: "Latin (1995)", cyrillic: "Кирилл", new_latin: "New Latin (2026)" };

  function copyButton(text) {
    return el("button", { text: "Copy", onclick: function (e) {
      if (navigator.clipboard) navigator.clipboard.writeText(text);
      e.target.textContent = "Copied";
    }});
  }

  function scripts(d) {
    var cards = Object.keys(LABELS).map(function (k) {
      var v = d.versions[k];
      return el("div", { class: "card" }, [
        el("div", { class: "row" }, [
          el("strong", { text: LABELS[k] }),
          k === d.target ? el("span", { class: "pill", text: "requested" }) : null,
          copyButton(v)
        ]),
        el("div", { style: "white-space:pre-wrap;margin-top:6px", text: v })
      ]);
    });
    var out = [el("div", { class: "grid" }, cards)];
    if (d.note) out.push(el("div", { class: "muted", text: d.note }));
    return out;
  }

  function amount(d) {
    return [el("div", { class: "card" }, [
      el("div", { class: "muted", text: d.amount }),
      el("div", { style: "font-size:16px;margin:6px 0", text: d.words }),
      copyButton(d.words)
    ])];
  }

  function normalized(d) {
    return [el("div", { class: "card" }, [
      el("div", { class: "row" }, [el("strong", { text: d.changed ? "Fixed" : "Already correct" }), copyButton(d.normalized)]),
      el("div", { style: "white-space:pre-wrap;margin-top:6px", text: d.normalized }),
      el("div", { class: "muted", text: "Search key: " + d.search_key })
    ])];
  }

  function rates(d) {
    var rows = d.rates.map(function (r) {
      var ch = parseFloat(r.change);
      return el("tr", {}, [
        el("td", { text: r.nominal + " " + r.code }),
        el("td", { text: r.name_en || "" }),
        el("td", { text: r.rate_uzs + " soʻm" }),
        el("td", { class: ch > 0 ? "ok" : ch < 0 ? "err" : "", text: (ch > 0 ? "+" : "") + r.change })
      ]);
    });
    return [
      el("h2", { text: "Central Bank of Uzbekistan" }),
      el("table", {}, [el("thead", {}, [el("tr", {}, ["Unit", "Currency", "Rate", "Change"].map(function (h) { return el("th", { text: h }); }))]), el("tbody", {}, rows)]),
      el("div", { class: "muted", text: "Rates set for " + d.dates.join(", ") + " · source: cbu.uz" })
    ];
  }

  var VIEWS = { scripts: scripts, amount: amount, normalized: normalized, rates: rates };

  plugkit.onData(function (d) {
    var root = document.getElementById("root");
    var view = VIEWS[d && d.kind];
    root.replaceChildren.apply(root, view ? view(d) : [el("div", { class: "empty", text: "Nothing to show." })]);
  });
})();
"""
