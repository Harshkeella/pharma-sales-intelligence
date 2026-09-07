# Verification results

- **Source reconciliation:** 45,000 transactions in 13 compatible sheets; gross sales, net sales, quantity, discount, distinct invoices and GST agree with the independent Decimal calculation in `workbook-review.json`.
- **Backend:** 13 pytest cases pass, including financial relationships, combined filters, invalid rows, missing optional data, multi-year comparisons, duplicate-file protection, material conflicts and removal.
- **Frontend:** the Vitest formatting check passes.
- **Browser:** both Playwright workflows pass. The real-workbook workflow checks all ten views, therapy filtering and reset, mobile overflow, PDF/PPTX downloads and complete clearing. The small multi-year workflow checks combining years, matched-date comparison, both exports and individual/final file removal.
- **Export validation:** 9 ordered landscape PDF pages and 9 widescreen PPTX slides. Each slide uses a high-resolution rendered image. The PDF contact sheet was rendered and visually inspected.
- **Visual inspection:** desktop empty state and populated overview inspected; the mobile chart-width issue was corrected and the narrow-screen overflow assertion passes.

The full browser suite completed in approximately 2.3 minutes in the verified run. This is a workflow duration, not a standalone ingestion benchmark or a 500,000-row performance claim.

The application is delivered for local operation. It has not been published to a public host. PDF/PPTX deliberately use condensed four-chart layouts; the web application contains the additional exploratory visuals and tables.
