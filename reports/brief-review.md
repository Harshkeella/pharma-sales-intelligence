# Brief and workbook review

The brief describes an analytical application, not a static website. Its essential contract is reusable ingestion, audited measures, server-side filtering and complete removal of session data. The supplied workbook is suitable for this contract.

## Verified source

- 45,000 transaction rows in 13 compatible sheets; Summary is excluded.
- 72 source columns, including material-master attributes embedded in each transaction.
- Invoice dates: 1 April 2026 through 3 April 2027.
- 45,000 distinct invoices, 120 payer IDs, 700 materials, 46 brands and 9 therapies.
- Many financial values are text containing comma separators. Dates use day-month-year strings. Identifiers, including payment terms with leading zeroes, must remain strings.

## Independent financial controls

| Measure | Verified value |
|---|---:|
| Gross sales | ₹1,50,18,97,473.35 |
| Net sales | ₹1,27,67,82,225.55 |
| Discount cost | ₹22,51,15,247.80 |
| Quantity | 1,44,41,150 |
| GST | ₹10,80,75,647.78 |
| Weighted discount | 14.9887227187% |
| Average invoice value | ₹28,372.9383456 |

These totals were calculated independently from the workbook and reconciled to the analytical engine. They are development controls, never production dashboard constants.

## Requirements that needed interpretation

1. The brief's Total GST expression contains Markdown bullets where plus signs were intended. GST is the sum of CGST, SGST, IGST and UTGST. If a required tax component is unavailable, the total remains unavailable.
2. Source Discount Value is negative for a reduction. The audit checks `Discount Value = Net Amount − Sale Value`; the displayed Discount Cost is the positive `Sale Value − Net Amount`.
3. The source Year field remains `2026–27` on 215 April 2027 transactions. Invoice dates place these in FY 2027–28. The app derives the fiscal year from dates and reports the disagreement.
4. April 2027 has 215 rows and only three active invoice days, ending before month-end. This supports a **potential partial month** warning. No rows are automatically removed.
5. Repeated invoice numbers are not necessarily duplicate transactions: invoice line items are legitimate. The audit reports repeated IDs separately and never drops them automatically.
6. There are no verified coordinates, targets, margins, profit or inventory positions. Geography uses rankings; shelf-life exposure describes sales at invoice time, not current stock at risk.
7. The requested Next.js/Python stack requires a Python-capable host. Cloudflare Sites' JavaScript runtime is not a direct deployment target for this backend. This delivery runs locally on Windows.

## Audit outcome

No rows were rejected. All implemented financial relationship checks passed within ₹0.02 per transaction. No material-master conflicts were found. The source-year mismatch is the only nonzero audit category in this workbook. See `workbook-review.json` for reproducible source controls and sheet counts.

## Engineering boundaries

Session datasets are isolated in process memory and expire after one hour of inactivity. One server process is required. Workbooks are not permanently copied into the application. Large-scale deployment, authentication, distributed storage and 500,000-row load testing require a deployment-specific follow-up; no such performance claim is made here.
