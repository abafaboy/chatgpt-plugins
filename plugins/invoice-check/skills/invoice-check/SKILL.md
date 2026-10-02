---
name: invoice-check
description: Use when the user uploads or pastes a supplier proforma, quotation, invoice, счёт на оплату or коммерческое предложение (КП) and wants it checked — totals, VAT, discount, freight, amount in words, currency, validity or Incoterms — or wants two versions of a quotation, or a proforma and the final invoice, compared.
---

# Checking a proforma, quotation or invoice

## Which tool

- One document to check: call `check_invoice` with the attached file. Pass `as_of` (YYYY-MM-DD)
  only when the user wants validity judged against a date other than today. Pass `tolerance`
  only when the user says rounding differences up to some amount are acceptable.
- Two versions of the same document (quotation v1 and v2, proforma and final invoice): call
  `compare_quotations` with the earlier one as `old_file` and the later one as `new_file`. If the
  order is unclear, ask which is newer, or use the dates on the documents.
- The user asks what is checked, or what a rule id such as IL104 means: call `list_invoice_rules`.

## Explaining the result

- Go through each error first, then warnings, then info. For each one, show the arithmetic the
  finding gives (for example "2 × 6,180.00 = 12,360.00, but the line says 12,630.00, a difference
  of +270.00") in the document's own number format, so the user can paste it to the supplier.
- Say which figure is probably wrong and what the corrected total would be only when the finding
  shows it; do not recompute figures yourself beyond what the tool reported.
- Findings marked as heuristic (Incoterms insurance and freight) are prompts to confirm with the
  supplier, not proven errors. Say so.
- If the result mentions that no line items or no total could be found, tell the user the table
  was not read and the arithmetic was therefore not checked.
- Offer to draft a short, polite message to the supplier listing the errors with their arithmetic.

## What not to claim

- Never call a document "correct", "valid" or "safe to pay". With no findings, say that nothing
  inconsistent was found in the arithmetic and consistency checks.
- The tool does not check whether prices are fair or match the market, whether the supplier is
  genuine, bank details, tax registration, or legal validity. Say so if the user asks.

## Files the tool cannot read

- The tool needs a file: PDF with a text layer, XLSX, CSV or JSON. If the user pasted a table as
  text, ask them to attach the original file (or save the table as CSV or XLSX).
- Scanned or photographed PDFs have no text layer and are rejected; ask for the original PDF or
  a spreadsheet export. Word files and images are not supported.
