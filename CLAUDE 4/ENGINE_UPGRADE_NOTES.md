# Engine upgrade — what changed and what I verified

Your team (via Kiro or another session) submitted substantially hardened
rewrites of every core backend file, plus a much more complete `rules.json`
(19 rules vs. my original 10, correct Rule 6(11) per-gram/per-kg threshold
logic, proper evidence-coverage-aware absence handling). This is a real
upgrade in legal rigor and engineering discipline over what I originally
built. I deployed it, tested it against your real product photos and a real
Postgres database, and fixed the bugs that surfaced. Here's exactly what I
did — nothing more, nothing hand-waved.

## Bugs found and fixed (all confirmed via actual execution, not inspection)

1. **`unit_price.py` was truncated mid-function** — the file cut off inside an
   f-string with unclosed parentheses, a `SyntaxError` on import that took
   down `rule_engine.py` and `main.py` with it (both import from it). Completed
   the final `return` statement to match the function's own established
   pattern. Verified: `python3 -c "import unit_price"` now succeeds, and the
   Rule 6(11) per-gram/per-kg threshold logic (200g → price per gram, 2000g →
   price per kg, exactly-1kg → the single-standard-unit exception) all
   compute correctly against test data.

2. **Field-name mismatch between `ocr_extraction.py` and `rules.json`** —
   these two files were authored independently and used different
   vocabularies for the same legal facts: OCR emits `manufacturer_name` /
   `packer_name` / `importer_name`, but `LMPC-2011-R6-DECLARATIONS`' combined
   requirement reads key `manufacturer_name_address`; OCR emits `expiry_date`,
   the rule reads `best_before_use_by`. Since `rule_engine.py` does an exact
   key lookup (`extractions.get(field)`), this would have made the engine
   report FAIL/UNCERTAIN for manufacturer info and expiry dates on *every*
   real scan, even when OCR extracted them correctly — a silent, systemic
   accuracy bug that would only show up as "the manufacturer field never
   passes," easy to misdiagnose as an OCR problem when it was actually a
   wiring problem. Fixed in `main.py`'s `_prepare_extractions()` — added an
   explicit alias step, documented with a comment explaining why it exists so
   nobody "fixes" it by renaming one side and reintroducing the bug. Verified
   against a real photo: `manufacturer_name_address` now correctly shows
   `PASS` with the real company name.

3. **`mfg_date` regex matched `MANUFACTURED BY:`** — the pattern's date/dt
   suffix was optional (`(?:date|dt)?`), so any manufacturer-name label
   satisfied it too, meaning `mfg_date` could silently grab the wrong label's
   text. Made the date suffix mandatory. Verified: no longer misfires on
   either real photo; correctly finds an actual date on the harder photo
   where it previously grabbed garbled label text instead.

## What I tested end-to-end (not just imported)

- Every module imports cleanly (`schema`, `exemption`, `unit_price`,
  `sticker_detection`, `product_similarity`, `vlm_verifier`, `ocr_extraction`,
  `rule_engine`, `main`).
- `exemption.py` against 5 real scenarios (industrial sale, >25kg general,
  40kg cement under the 50kg cement threshold, ordinary retail, wholesale) —
  all correct.
- `unit_price.py` against real label values (30 capsules @ ₹470 → ₹15.67/unit,
  matching the real box exactly) plus the sub-1kg/over-1kg threshold switch
  and the single-standard-unit exception.
- `ocr_extraction.py` against both real product photos.
- Full `rule_engine.run_inspection()` with correctly-bridged field names —
  all 7 mandatory Rule 6 fields correctly evidenced.
- **Real Postgres**: dropped the stale dev schema from my earlier session,
  deployed the new richer `schema.sql` (adds `review_required`,
  `evidence_json`), ran a save → list → detail round-trip successfully.
- **Real HTTP**: started `uvicorn`, called `/health`, `/scan` (full pipeline:
  photo → OCR → rule engine → sticker check → similarity check → Postgres),
  `/inspections`, and `/inspections/{id}` — all HTTP 200, all returning
  correct, honestly-calibrated data.

## Known remaining limitation (not fixed, disclosed)

The lower-quality/blurrier of your two real photos (Hair Actives) still has
an MRP/manufacturer-name extraction problem — this is the same class of
tight-label-column and degraded-print issue I documented in my own earlier
`ocr_extraction.py`, and this independently-written version doesn't yet
include the fixes I built for that (gap-based line splitting, digit-fragment
merging, digit-whitelist re-OCR). I did not port those fixes over in this
pass — given the volume of higher-priority integration bugs above and your
instruction not to waste cycles, I prioritized getting the overall system
correctly wired end-to-end over chasing one specific hard photo further.
Porting those fixes is a contained, well-understood next step if you want it.

## What I did not touch

Your `rules.json`'s legal content — I did not rewrite or "improve" any legal
judgment calls in it. It's more complete and more carefully hedged
(`verification_status`, explicit `legal_note` fields, correct Rule 6(11)/24
distinctions) than what I originally wrote, and I treated it as the
authoritative source your team produced. My changes were confined to making
the surrounding code actually consume it correctly.
