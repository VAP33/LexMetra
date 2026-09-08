# Workstream 4: Consumer Reporting + PDF Generation (USP 3)

## Read first
`handoff/00_PROJECT_STATUS_AND_SPLIT.md` — shared ground truth and the
non-negotiable contract. Don't skip it.

## What exists: nothing. Confirmed by listing every endpoint in main.py —
there is no report data model, no submission endpoint, no authority-facing
view, and no PDF generation anywhere in this project. You're building this
from scratch, which also makes this the workstream with the most freedom
and the least risk of conflicting with the other three.

## Part A: Consumer-to-authority reporting

1. **Data model.** New table: `reports(report_id, inspection_id NULLABLE
   (a report may or may not be linked to a prior /scan), reporter_contact
   (optional — don't require PII you don't need), description TEXT,
   image_filenames TEXT[], location_text, status (submitted/under_review/
   resolved/dismissed), submitted_at, authority_note)`. Link to
   `inspections` when available (`inspection_id`) so an authority reviewing
   a report can see the full automated compliance finding alongside the
   consumer's own account — but a report must also work standalone (a
   consumer photographing a violation without having run it through your
   `/scan` pipeline first).

2. **Endpoints**: `POST /reports` (submit — accepts photo(s) + description +
   optional inspection_id), `GET /reports` (authority-side list, filterable
   by status), `GET /reports/{id}` (detail), `POST /reports/{id}/status`
   (authority updates status + note). Follow the exact same patterns
   already established in `db/persistence.py` and `main.py` for
   inspections — same style, same error handling, same "run it for real
   against Postgres before calling it done" discipline.

3. **Privacy discipline.** A consumer reporting a business for a compliance
   violation is a sensitive action. Don't require identity beyond what's
   functionally necessary; make reporter_contact genuinely optional; think
   about whether reports should be visible to anyone other than the
   relevant authority before you build a public listing view.

## Part B: PDF report generation

1. **What it's for**: turning a `ProductInspection` (or a consumer `Report`)
   into a document an authority can act on or file — not a marketing
   one-pager. Include: product identity, all facts with their status/reason/
   rule citation, overall verdict, the disclaimer text already present on
   `ProductInspection.disclaimer` (do not drop this — it's there because an
   automated screening tool must never look like a legal determination),
   and embedded evidence images where available.

2. **Use a real PDF library** (reportlab, weasyprint from HTML, or
   similar) — don't hand-roll PDF byte generation. Check what's already
   installed/available in the environment before adding a new heavyweight
   dependency.

3. **Endpoint**: `GET /inspections/{id}/report.pdf` and
   `GET /reports/{id}/report.pdf`. Generate on demand rather than storing
   every possible PDF — storage/regeneration tradeoff is fine either way,
   just pick one and say why.

## What to test and report back

- Submit a real report through your endpoint (photo + description, with
  and without a linked inspection_id) and read it back from Postgres.
- Generate an actual PDF from a real inspection already in the database
  (several exist from earlier testing — check `/inspections` for real
  inspection_ids) and open it — confirm it's readable, correctly shows
  PASS/FAIL/UNCERTAIN per field, and includes the disclaimer text.
- Don't just show generated code — show the PDF's actual rendered content
  (describe what's on the page, or note you've placed the file for
  download) as evidence it runs.

## Files to upload to this Claude session

`backend/schema.py`, `backend/db/schema.sql`, `backend/db/persistence.py`,
`backend/main.py`, `handoff/00_PROJECT_STATUS_AND_SPLIT.md`.
