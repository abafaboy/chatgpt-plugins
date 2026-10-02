BODY = '<div id="root" class="grid"><div class="empty">…</div></div>'

EXTRA_CSS = """
details { border: 1px solid var(--line); border-radius: 10px; background: var(--card); }
summary { cursor: pointer; padding: 8px 12px; font-family: ui-monospace, Menlo, Consolas, monospace; }
details .row { padding: 0 12px; justify-content: flex-end; }
pre { margin: 8px 12px 12px; padding: 10px; white-space: pre-wrap; word-break: break-word; max-height: 360px;
      overflow: auto; font-size: 12px; background: var(--bg); border: 1px solid var(--line); border-radius: 8px; }
ul { margin: 0; padding-left: 20px; }
.sev { font-weight: 600; text-transform: uppercase; font-size: 11px; }
a.src { color: var(--accent); cursor: pointer; text-decoration: underline; }
"""

SCRIPT = r"""
(function () {
  var el = plugkit.el;

  function copyButton(text) {
    return el("button", { text: "Copy", onclick: function (e) {
      if (navigator.clipboard) navigator.clipboard.writeText(text);
      e.target.textContent = "Copied";
    }});
  }

  function header(d) {
    var ok = d.ok;
    var label = ok ? "Ready: no errors" : "Fix " + d.errors + " error" + (d.errors === 1 ? "" : "s");
    return el("div", { class: "row" }, [
      el("h2", { class: ok ? "ok" : "err", text: label }),
      el("span", { class: "pill", text: d.warnings + " warning" + (d.warnings === 1 ? "" : "s") }),
      el("span", { class: "muted", text: d.file_count + " files · " + d.skills.length + " skill(s)" })
    ]);
  }

  function sourceLink(url) {
    return el("a", { class: "src", text: "rule source", onclick: function () { plugkit.openLink(url); } });
  }

  function issuesTable(issues) {
    if (!issues.length) return el("div", { class: "muted", text: "No issues found." });
    var rows = issues.map(function (i) {
      return el("tr", {}, [
        el("td", {}, [el("span", { class: "sev " + (i.severity === "error" ? "err" : "warn"), text: i.severity })]),
        el("td", { text: i.rule_id }),
        el("td", { text: i.path }),
        el("td", {}, [i.message, " ", sourceLink(i.source_url)])
      ]);
    });
    return el("table", {}, [
      el("thead", {}, [el("tr", {}, ["Severity", "Rule", "File", "Issue"].map(function (h) { return el("th", { text: h }); }))]),
      el("tbody", {}, rows)
    ]);
  }

  function fileBlock(f) {
    return el("details", {}, [
      el("summary", { text: f.path }),
      el("div", { class: "row" }, [copyButton(f.content)]),
      el("pre", { text: f.content })
    ]);
  }

  function build(d) {
    return [
      el("div", { class: "card grid" }, [
        el("div", { class: "row" }, [el("strong", { text: "Package " + d.slug }), el("span", { class: "pill", text: d.files.length + " files" })]),
        el("div", { class: "muted", text: "Converted automatically" }),
        el("ul", {}, d.converted.map(function (c) { return el("li", { text: c }); })),
        el("div", { class: "muted", text: "Still to do by hand" }),
        el("ul", {}, d.manual_steps.map(function (m) { return el("li", { text: m }); }))
      ]),
      el("div", { class: "grid" }, d.files.map(fileBlock)),
      header(d),
      issuesTable(d.issues)
    ];
  }

  function validate(d) {
    return [header(d), issuesTable(d.issues)];
  }

  function rules(d) {
    var rows = d.rules.map(function (r) {
      return el("tr", {}, [
        el("td", { text: r.rule_id }),
        el("td", {}, [el("span", { class: "sev " + (r.severity === "error" ? "err" : "warn"), text: r.severity })]),
        el("td", { text: r.checks }),
        el("td", {}, [sourceLink(r.source_url)])
      ]);
    });
    return [
      el("h2", { text: "Plugin package rules" }),
      el("table", {}, [
        el("thead", {}, [el("tr", {}, ["Rule", "Severity", "Checks", "Source"].map(function (h) { return el("th", { text: h }); }))]),
        el("tbody", {}, rows)
      ])
    ];
  }

  var VIEWS = { build: build, validate: validate, rules: rules };

  plugkit.onData(function (d) {
    var root = document.getElementById("root");
    var view = VIEWS[d && d.kind];
    root.replaceChildren.apply(root, view ? view(d) : [el("div", { class: "empty", text: "Nothing to show." })]);
  });
})();
"""
