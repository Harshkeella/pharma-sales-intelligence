# Pharma Sales Intelligence

A pharmaceutical sales intelligence website built with Next.js, TypeScript, Tailwind, Apache ECharts, FastAPI, Pandas, OpenPyXL and DuckDB. No dashboard data is bundled or automatically loaded.

The production deployment uses two Vercel projects from this repository: `frontend` for the public Next.js site and `backend` for the FastAPI service. The frontend proxies `/api` to the backend through `BACKEND_URL`. A private Vercel Blob store holds uploaded XLSX files, normalized session frames and the session manifest; `BLOB_READ_WRITE_TOKEN` is shared by both projects. `ALLOWED_ORIGINS` contains the production frontend URL, and `CRON_SECRET` protects the backend's daily cleanup route.

## Start on Windows

Install Node.js 20.9+ and Python 3.12. In PowerShell, from this folder:

```powershell
.\setup.ps1
.\run.ps1
```

Open http://localhost:3000. Keep the terminal running. Press Ctrl+C to stop. The backend listens only on 127.0.0.1:8000; the browser connects through Next.js. Run a single backend worker.

For development, activate `.venv`, run `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`, then run `npm run dev` inside `frontend` in another terminal.

## Use

1. Drop one or more XLSX workbooks or choose **Browse workbooks**. Each sheet is identified from its headings, not its name.
2. Review **Data quality**. The supplied workbook has 215 source-year inconsistencies; invoice dates remain authoritative.
3. Navigate Overview, Sales trends, Products, Customers, Geography, Commercial, Supply chain, Pharma risk, Tax & terms and Explorer.
4. Use the filter bar, **All filters**, or selectable chart categories. Filters carry across pages. Clear a chip or choose **Reset filters** to restore the context.
5. Add historical workbooks using **Add data**. Identical file bytes are rejected to prevent double counting. The dataset panel offers replacement after a duplicate upload.
6. Compare fiscal years on Sales trends. Comparisons use month/day values with activity in both years. This is a transparent matched-active-date comparison, not an inferred complete fiscal-year growth rate.
7. Use Explorer for search, sorting, columns, row details, batch data and filtered CSV downloads. Only 50 rows are displayed per page.
8. Export a selection or all nine analytical pages as landscape PDF or widescreen PowerPoint. Export layouts contain four key charts per page, current filters, date coverage, dataset names, timestamp and page numbers. They use one atomic backend snapshot and exclude application navigation.
9. Remove individual workbooks from **Your dataset**, or use **Clear all data**. Removing the last file destroys its session and returns the interface to the empty state.

## Financial and schema rules

Required: Invoice Date, Invoice Number, Payer, Material, Quantity, Sale Value, Net Amount. Recommended and optional headings are shown in **View expected schema** and defined centrally in `backend/schema.py`.

- Gross sales = Sale Value. Net sales = Net Amount. Discount cost = gross minus net.
- Source Discount Value is expected to equal net minus gross. Weighted discount is discount cost divided by gross, not the mean source Discount Rate.
- Source amounts are parsed as Decimal and rounded half-up to integer paise for authoritative sums. Row formula tolerance is ₹0.02. Chart presentation uses numeric conversions of these sums.
- All four GST components must be available to report total GST; unknown components are not silently zero-filled.
- Invoice dates determine calendar year, April-start fiscal year, month, quarter and fiscal quarter.
- Required malformed rows are rejected and counted. Negative transactions and potential duplicates remain included and are flagged rather than silently deleted.
- Lead-time measures exclude negative chronological intervals. Shelf life is measured at sale; negative shelf life is retained as expired-at-sale exposure.
- Refrigeration/2–8°C descriptions identify cold-chain sales. These are source-description classifications, not a validated product handling specification.
- Exact file hashes prevent duplicate uploads. Content overlaps between different files are audited, not automatically deduplicated.

## Privacy and limits

Browser state contains aggregates and the current table page, not the full dataset. No workbook is saved to the repository. Local sessions stay in memory and expire after one hour. Production sessions use private Vercel Blob storage so they survive serverless instance changes; the scheduled cleanup removes session files after 24 hours. Clearing data removes its private Blob objects immediately. Reloading the page starts empty, while its abandoned server session expires automatically.

Limits: 100 MB compressed per workbook, 800 MB uncompressed workbook XML and 600,000 rows per session. The 45,000-row supplied workbook is verified; 500,000+ row performance is not benchmarked. The public deployment does not include user accounts; anyone with its URL can create an isolated temporary session.

Charts with unavailable values show an explicit empty state. Maps are intentionally absent because the input contains no verified coordinates. PDF/PPTX use condensed export layouts rather than every exploratory visual and table. PowerPoint slides contain high-resolution rendered dashboard images, not editable native charts.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe tests/make_fixtures.py
.\.venv\Scripts\python.exe tests/review_workbook.py 'C:\path\pharma_sales_45000_with_material_master.xlsx'
cd frontend
npm test
npm run build
# With both servers running:
npm run test:e2e
```

Set `PHARMA_TEST_WORKBOOK` for a different location of the supplied fixture. The independent control review expects its documented 45,000 rows. Small synthetic yearly workbooks are generated by `make_fixtures.py` solely for tests.

The tests cover financial relationships and totals, optional missing fields, invalid rows, filters, multi-year comparison, duplicate hashes, material conflicts, removal, frontend formatting and the browser workflow. The workbook review and saved screenshots/exports live under `reports`. Exact repeated query results are cached per session in the browser; mutations clear the cache. Superseded requests are canceled. Explorer search is debounced without unmounting its input.

## Structure

- `backend/schema.py`: explicit aliases, required fields and filter whitelist.
- `backend/engine.py`: ingestion, audit, normalization, measures, analytics and Explorer.
- `backend/main.py`: session lifecycle, isolated API, upload limits and atomic export snapshots.
- `frontend/app`: application shell, shared styling and server-rendered exports.
- `frontend/components`: ECharts rendering, dashboard views and fiscal comparison.
- `backend/tests`, `frontend/e2e`, `tests`: automated verification and independent source controls.

Read `reports/brief-review.md` for the brief interpretation and workbook findings.

Read `reports/verification.md` for the completed verification record. Optional independent export inspection uses `tests/verify_exports.py` with `pypdf`, `pypdfium2` and `Pillow`; these QA-only packages are not required to run the website.
