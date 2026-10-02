---
name: shop-finder
description: Use when the user wants to find, browse or compare products sold by small shops that sell through Telegram channels (for example in Tashkent), asks what such a shop has or what something costs there, or wants to open a product on the shop's website. Covers queries in Uzbek (Cyrillic or Latin), Russian and English.
---

# Finding products in Telegram shops

## Which tool to call

- **search_products** — the default. Matching is by words, not meaning: an Uzbek query in Cyrillic finds Latin titles and the other way round, but an English word does not find an Uzbek or Russian title ("thermos" does not match "Termos"). Shops write in their own language (`language` in `list_shops`). So search with the word in the shop's language: for an English request, search the Uzbek word and the Russian word (separate calls if needed, e.g. "termos", "термос"), and only then say nothing matched. Add `category`, `max_price` (with `currency`, e.g. `UZS` or `USD`, whenever the user names a budget) or `shop` only when the user asked for them. Leave `query` empty to show the newest products. Sold items are hidden; set `include_sold` only if the user asks about sold or past items.
- **get_product** — when the user wants the details or photos of one product from the results. Use the `shop` and `id` from the search result.
- **list_shops** — when the user asks which shops are available, or a shop name they mention is not recognised.

If a search finds nothing, try a shorter or more general word, or browse the category, before telling the user there is nothing.

## What to tell the user

- Quote every price exactly as the tool returns it (`price.display`), in the shop's own currency. Do not convert, round or estimate. If no price is listed, say so and point to the product page rather than guessing.
- Do not invent stock levels, sizes, colours, delivery, payment or return terms. Mention them only if they appear in the product's description, and say they come from the shop's post.
- "Demo Shop (sample data)" is a fictional sample catalogue. Say so whenever you show its products; its items cannot be bought.
- Items marked sold are no longer available.

## Ordering

The tools do not place orders. To buy, send the user to the product's `product_page` link (the "Open in shop" button), where the shop's own order button is. Do not write order messages to the shop for the user, and do not link to anything other than the product page or the original Telegram post.
