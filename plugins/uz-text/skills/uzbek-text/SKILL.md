---
name: uzbek-text
description: Convert Uzbek text between Cyrillic, Latin (1995) and the new Latin alphabet, write money amounts in Uzbek words for invoices and contracts, fix Uzbek apostrophes, and look up the Central Bank of Uzbekistan's official exchange rates. Use whenever the user writes or asks for Uzbek text in a particular script, needs "summa so'z bilan" / "сумма прописью" in Uzbek, or needs today's official soʻm rate.
---

# Uzbek text and soʻm amounts

## Which tool

- **Transliteration or "write this in Cyrillic/Latin"** → `convert_uzbek_script`. Do not transliterate
  Uzbek yourself: the rules for ts/s, ye/e, yo/ё and the tutuq belgisi (ʼ) are easy to get wrong.
  For a long document, convert it in parts of up to 20,000 characters.
- **Amount in words for an invoice, contract or payment order** → `write_amount_in_uzbek_words`.
  Pass the amount exactly as written (spaces and a decimal comma are fine). Pass `currency` and
  `subunit` in Uzbek for anything other than soʻm (e.g. "AQSH dollari" / "sent").
- **Messy apostrophes** (O'zbek, O`zbek, G‘ulom) → `normalize_uzbek_text`.
- **Official exchange rate** → `get_uzbek_exchange_rates` with ISO codes. Quote the date the tool
  returns; it is the date the Central Bank set the rate, which may differ from today.

## Rules

- The new Latin alphabet (Ö Ğ Ş Ç) was approved by the Senate on 10 September 2026. Until the law is
  signed and in force, tell the user to keep the 1995 Latin alphabet for official documents unless they
  confirm otherwise. The tool adds this note; repeat it, don't drop it.
- Only the Central Bank's current rates are available. Do not invent historical rates; say the tool
  cannot provide them.
- Russian is not Uzbek Cyrillic. If the user gives Russian text, say the tool converts Uzbek only.
- Show converted text exactly as the tool returns it.
