BODY = '<div id="root" class="grid"><div class="empty">…</div></div>'

EXTRA_CSS = """
.sev { font-weight: 600; white-space: nowrap; }
.code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; white-space: nowrap; }
.pill.err { border-color: var(--err); } .pill.warn { border-color: var(--warn); }
.ident { display: grid; gap: 2px; }
"""

SCRIPT = r"""
(function () {
  var el = plugkit.el;
  var SEV = { error: "err", warning: "warn", info: "muted" };
  var TYPES = { proforma: "Proforma invoice", quotation: "Quotation", invoice: "Invoice" };

  function table(headers, rows) {
    return el("table", {}, [
      el("thead", {}, [el("tr", {}, headers.map(function (h) { return el("th", { text: h }); }))]),
      el("tbody", {}, rows)
    ]);
  }

  function ident(doc, label) {
    var kind = TYPES[doc.type] || "Document";
    var title = [kind, doc.number].filter(Boolean).join(" ");
    var facts = [doc.supplier, doc.issue_date, doc.currency,
      [doc.incoterm, doc.incoterm_place].filter(Boolean).join(" ")].filter(Boolean).join(" · ");
    return el("div", { class: "ident" }, [
      label ? el("div", { class: "muted", text: label }) : null,
      el("strong", { text: title }),
      facts ? el("div", { class: "muted", text: facts }) : null,
      doc.file_name ? el("div", { class: "muted", text: doc.file_name }) : null
    ]);
  }

  function findingRows(list) {
    return list.map(function (f) {
      return el("tr", {}, [
        el("td", { class: "sev " + (SEV[f.severity] || ""), text: f.severity }),
        el("td", { class: "code", text: f.rule }),
        el("td", {}, [
          f.location && f.location !== "document" ? el("div", { class: "muted", text: f.location }) : null,
          el("div", { text: f.message })
        ])
      ]);
    });
  }

  function pill(n, word, cls) {
    return el("span", { class: "pill " + cls, text: n + " " + word + (n === 1 || word === "info" ? "" : "s") });
  }

  function check(d) {
    var c = d.counts;
    var out = [
      el("div", { class: "card" }, [ident(d.document)]),
      el("div", { class: "row" }, [pill(c.error, "error", "err"), pill(c.warning, "warning", "warn"), pill(c.info, "info", "muted")])
    ];
    if (d.findings.length) out.push(table(["Severity", "Rule", "Finding"], findingRows(d.findings)));
    else out.push(el("div", { class: "card ok", text: "No inconsistencies found in what was checked." }));
    (d.document.notes || []).forEach(function (n) { out.push(el("div", { class: "muted", text: n })); });
    out.push(el("div", { class: "muted", text: d.note + " Validity checked as of " + d.as_of + "; rounding tolerance " + d.tolerance + "." }));
    return out;
  }

  function compare(d) {
    var out = [el("div", { class: "card grid" }, [ident(d.old, "Old version"), ident(d.new, "New version")])];
    if (d.changes.length) {
      out.push(el("h2", { text: d.changes.length + (d.changes.length === 1 ? " change" : " changes") }));
      out.push(table(["Severity", "Rule", "Change"], findingRows(d.changes)));
    } else {
      out.push(el("div", { class: "card", text: "No differences in lines, totals or terms." }));
    }
    out.push(el("div", { class: "muted", text: d.note }));
    return out;
  }

  function rules(d) {
    var rows = d.rules.map(function (r) {
      return el("tr", {}, [
        el("td", { class: "code", text: r.id }),
        el("td", { class: "sev " + (SEV[r.severity] || ""), text: r.severity }),
        el("td", { text: r.summary + (r.heuristic ? " (heuristic)" : "") })
      ]);
    });
    return [el("h2", { text: "Checks" }), table(["Rule", "Severity", "What it checks"], rows)];
  }

  var VIEWS = { check: check, compare: compare, rules: rules };

  plugkit.onData(function (d) {
    var root = document.getElementById("root");
    var view = VIEWS[d && d.kind];
    root.replaceChildren.apply(root, view ? view(d) : [el("div", { class: "empty", text: "Nothing to show." })]);
  });
})();
"""
