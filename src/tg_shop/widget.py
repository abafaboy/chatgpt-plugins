BODY = '<div id="root"><div class="empty">…</div></div>'

CSS = r"""
.products { display: grid; gap: 10px; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); }
.product { display: flex; flex-direction: column; gap: 6px; padding: 8px; }
.thumb { width: 100%; aspect-ratio: 1 / 1; object-fit: cover; border-radius: 8px; background: var(--line); display: block; }
.nophoto { width: 100%; aspect-ratio: 1 / 1; border-radius: 8px; background: var(--line); color: var(--muted);
  display: flex; align-items: center; justify-content: center; font-size: 12px; text-align: center; }
.title { font-weight: 600; overflow-wrap: anywhere; }
.price { font-size: 15px; }
.spacer { flex: 1; }
.sold { color: var(--err); border-color: var(--err); }
.sample { color: var(--warn); border-color: var(--warn); }
.strip { display: flex; gap: 8px; overflow-x: auto; scroll-snap-type: x mandatory; padding-bottom: 4px; }
.strip img, .strip .nophoto { flex: 0 0 auto; width: min(320px, 80%); aspect-ratio: 1 / 1; object-fit: cover;
  border-radius: 8px; scroll-snap-align: start; }
.desc { white-space: pre-wrap; overflow-wrap: anywhere; }
.shops { display: grid; gap: 8px; }
.head { margin-bottom: 10px; }
"""

SCRIPT = r"""
(function () {
  var el = plugkit.el;
  var root = document.getElementById("root");

  function show(nodes) { root.replaceChildren.apply(root, nodes); }

  function photo(url, alt, cls) {
    if (!url) return el("div", { class: "nophoto " + (cls || ""), text: "No photo" });
    var img = el("img", { src: url, alt: alt, loading: "lazy", class: cls || "" });
    img.addEventListener("error", function () {
      img.replaceWith(el("div", { class: "nophoto " + (cls || ""), text: "Photo unavailable" }));
    });
    return img;
  }

  function priceText(p) {
    if (p.price && p.price.display) return p.price.display;
    if (p.price && p.price.amount !== null) return p.price.amount + " " + (p.price.currency || "");
    return "Price not listed";
  }

  function shopLine(p) {
    return el("div", { class: "row muted" }, [
      el("span", { text: p.shop_name }),
      p.demo ? el("span", { class: "pill sample", text: "sample data" }) : null
    ]);
  }

  function openButton(p) {
    return el("button", { class: "primary", text: "Open in shop", onclick: function () { plugkit.openLink(p.product_page); } });
  }

  function loading(text) { show([el("div", { class: "empty", text: text })]); }

  function openProduct(p) {
    loading("Opening…");
    plugkit.callTool("get_product", { shop: p.shop, product_id: p.id }).then(render, function () { render(last); });
  }

  function card(p) {
    return el("div", { class: "card product" }, [
      photo(p.images[0], p.title, "thumb"),
      el("div", { class: "title", text: p.title }),
      el("div", { class: "row" }, [
        el("span", { class: "price", text: priceText(p) }),
        p.sold ? el("span", { class: "pill sold", text: "Sold" }) : null
      ]),
      shopLine(p),
      el("div", { class: "spacer" }),
      el("div", { class: "row" }, [
        openButton(p),
        el("button", { text: "Details", onclick: function () { openProduct(p); } })
      ])
    ]);
  }

  function search(d) {
    var head = d.products.length
      ? (d.total > d.products.length ? d.products.length + " of " + d.total + " products" : d.total + " products")
      : "No matching products";
    var out = [el("div", { class: "muted head", text: head + (d.query ? " for “" + d.query + "”" : "") })];
    if (d.products.length) out.push(el("div", { class: "products" }, d.products.map(card)));
    if (d.unavailable_shops.length) out.push(el("div", { class: "muted", text: "Not searched right now: " + d.unavailable_shops.join(", ") }));
    return out;
  }

  function product(d) {
    var p = d.product;
    var imgs = p.images.length ? p.images.map(function (u) { return photo(u, p.title); }) : [photo(null, p.title)];
    var buttons = [openButton(p)];
    if (p.telegram_post) buttons.push(el("button", { text: "Post on Telegram", onclick: function () { plugkit.openLink(p.telegram_post); } }));
    if (last && last.kind === "search") buttons.push(el("button", { text: "Back", onclick: function () { render(last); } }));
    return [el("div", { class: "card grid" }, [
      el("div", { class: "strip" }, imgs),
      el("h2", { text: p.title }),
      el("div", { class: "row" }, [
        el("span", { class: "price", text: priceText(p) }),
        p.sold ? el("span", { class: "pill sold", text: "Sold" }) : null
      ]),
      shopLine(p),
      p.description ? el("div", { class: "desc", text: p.description }) : null,
      p.categories.length ? el("div", { class: "row" }, p.categories.map(function (c) { return el("span", { class: "pill", text: c }); })) : null,
      el("div", { class: "row" }, buttons)
    ])];
  }

  function shops(d) {
    return [el("div", { class: "shops" }, d.shops.map(function (s) {
      var status = s.error ? el("span", { class: "err", text: "Catalogue unavailable right now" })
        : el("span", { class: "muted", text: s.product_count + " products · " + s.available_count + " available" });
      return el("div", { class: "card grid" }, [
        el("div", { class: "row" }, [
          el("strong", { text: s.name }),
          s.demo ? el("span", { class: "pill sample", text: "sample data" }) : null
        ]),
        el("div", { class: "muted", text: s.city + " · " + s.language }),
        status,
        el("div", { class: "row" }, [
          s.error ? null : el("button", { class: "primary", text: "Browse", onclick: function () {
            loading("Loading…");
            plugkit.callTool("search_products", { shop: s.slug }).then(render, function () { render(d); });
          }}),
          el("button", { text: "Open site", onclick: function () { plugkit.openLink(s.base_url); } })
        ])
      ]);
    }))];
  }

  var VIEWS = { search: search, product: product, shops: shops };
  var last = null;

  function render(d) {
    var view = VIEWS[d && d.kind];
    if (!view) { show([el("div", { class: "empty", text: "Nothing to show." })]); return; }
    show(view(d));
    if (d.kind !== "product") last = d;
  }

  plugkit.onData(render);
})();
"""
