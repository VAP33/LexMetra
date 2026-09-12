# ANTIGRAVITY.md
## Build Brief v2 — Why product ID, Net Quantity, and compliance score are still broken

**Read this before touching code.** This supersedes the previous `antigravity.md` in this repo.
The previous brief's Section 1.1 (blank confirm-form) has been **partially fixed** — `/extract-preview`
now exists (`backend/main.py:687`) and is called from the frontend (`InspectionApp.tsx:713`). Good.
But the three things you're reporting today are **not that bug** — they are three different,
confirmed integration gaps, verified by direct inspection of this exact codebase on 2026‑09‑08.
Every claim below is a file:line reference you can go check yourself.

---

## 0. The one-sentence diagnosis

**Every module that could reliably identify a product or measure a package already exists in this
repo, fully written, and none of it is called from `main.py`.** OCR is the only thing that runs
because OCR is the only thing that's wired up. This isn't "the pipeline has a bug" — it's "80% of
the pipeline was never plugged in."

---

## 1. Product ID / SKU is never actually identified — confirmed cause

**Claim:** `product_id` comes out as a random 6-hex-character string (`PROD-F04821` in your example
is literally `f"PROD-{uuid.uuid4().hex[:6].upper()}"` at `backend/main.py:757`), because every real
identification path was skipped.

**What exists but is never called:**

1. **`backend/barcode_decode.py` (32 KB, fully implemented, has its own module docstring describing
   testing against your exact 29-photo dataset)** — decodes barcodes via two paths: OpenCV's
   `cv2.barcode.BarcodeDetector` (`_cv_decode`), and an OCR-plus-GS1-check-digit fallback for the
   human-readable digits under the bars (`_read_hri` / `decode_symbols` / `decode_across_images`,
   lines 625–830). The module's own docstring explains *why* it exists: `cv2`'s decoder fails on
   cylindrical packaging (jars, bottles) exactly like your test images, so it built a second read
   path. **This is the correct fix for your Bru-jar-style curved photos. It is never imported by
   `main.py`.** Grep confirms zero references outside its own file and `region_detection.py`'s
   comment about it.
2. **`backend/product_similarity.py`** — real phash + HSV-histogram visual matching against a
   catalog (`find_similar`, `load_index`). This *is* called (`main.py:660,1040`, `nearest_matches`
   key), **but `backend/product_index.json` contains exactly one synthetic entry**
   (`PROD-COMMON-NAME-FRUIT-JU`, built from `dataset/generate_dataset.py`'s generated images). No
   real product you photograph will ever match it. The similarity search machinery is fine; the
   catalog behind it is empty for your purposes.
3. The `suggested_product_id` fallback logic in `/extract-preview` (`main.py:752–763`) tries
   `common_name` → `manufacturer_name` → **random hex**, in that order, and never tries a barcode.
   When OCR can't read the label (curved surface, glare — see Section 3), it silently falls to the
   random string with no visual signal to the inspector that this is a placeholder, not an
   identification.

**Fix, in order:**
- Wire `barcode_decode.decode_across_images()` into `/extract-preview` and `/scan`, run it on every
  uploaded image alongside `run_ocr()`, and make a successful `CV_BARS_DECODED` result the
  **first** candidate for `suggested_product_id` (ahead of `common_name`), with
  `OCR_HRI_CHECK_DIGIT_VALIDATED` second and `needs_confirmation=True` surfaced to the inspector per
  the module's own design intent (it already returns this flag — main.py just needs to read it).
- Populate `product_index.json` from your real 29 test photos (or a real retail catalog) instead of
  synthetic generated images, so `product_similarity.find_similar` has something real to match
  against. Until then, expect near-zero useful matches on any real photo — this is not a bug in
  `product_similarity.py`, it's an empty database.
- Never let the random-hex fallback render as if it were a read value. Today the frontend shows
  `PROD-F04821` with no visual distinction from a genuinely-decoded ID. At minimum, tag it
  `source: "unidentified-placeholder"` and show it struck-through / grey with "type manually" —
  right now it looks like a successful identification, which is actively misleading.

---

## 2. Net Quantity "autofill" — confirmed cause

Your evidence: *"Declaration label 'Jere, WMA abe NET WEIGHT: we y' detected, but quantity amount
was not detected."* That garbled string is genuine OCR output on that image — this is not a wiring
bug, it's an **OCR quality failure on that specific photo**, and it's real: the label text is
present in the frame but numerically unreadable at the resolution/angle/glare that image was shot
at. `_extract_numeric_field` (`main.py`, called at line ~732) correctly returned nothing because
there was nothing reliable to extract — that's the system behaving conservatively, per design.

Two real fixes, not one:
1. **Curved-surface / glare OCR is a documented, known weak spot** (see the previous
   `antigravity.md` Section 1.2, still accurate) — `ocr_extraction.py`'s digit-repair passes were
   validated on flat-panel photos only. If you want net-quantity numerals to read reliably off
   curved jars, that needs targeted work on `ocr_extraction.py`/`preprocess.py` (deskew +
   unwarp-for-cylinder before OCR, not just perspective correction) — genuinely unsolved, not a
   quick wire-up.
2. **Do not conflate "OCR failed on this photo" with "pipeline is broken."** Right now both look
   identical to the inspector (blank field, "Not detected," 0% review confidence). Add a
   distinction in the API response: `not_attempted` (module never ran) vs `attempted_low_confidence`
   (OCR ran, found candidate text, confidence below threshold — show the raw candidate text so a
   human can read it even when the model won't commit) vs `not_present_in_frame`. Today all three
   collapse into "Not detected," which is why you can't tell whether this is a wiring problem or an
   image-quality problem — from the outside they're indistinguishable, which is exactly the
   confusion in your report.

---

## 3. Compliance score ~1/10 (11%) on *every* product — confirmed cause, and it's two compounding bugs

**Bug A — geometry/calibration are still not wired (confirmed unchanged from previous audit):**
`backend/geometry.py` and `backend/calibration.py` are never imported by `main.py` (`grep -n
"geometry\|calibrat" backend/main.py` returns nothing). `pdp_area_cm2` — the one input
`rule_engine._evaluate_font_height()` needs to ever return PASS/FAIL instead of UNCERTAIN
(`rule_engine.py:846–870`) — is **only** ever populated from a client-submitted form field
(`main.py:803`, `827`), and that form field has **no input control anywhere in the frontend**
(`grep pdpAreaCm2 InspectionApp.tsx` returns exactly one line, a pass-through with no `<input>`
behind it). So `pdp_area_cm2` is `None` on literally every request that has ever hit this backend
through the UI. Rule 7(2) (font height) is therefore **structurally incapable of returning
PASS on any product**, full stop — not "unlucky on your photos," but mathematically guaranteed
UNCERTAIN every time, on every product, forever, until this is wired.

**Bug B — the score formula makes "cautious" look identical to "failing":**
`frontend/react-app/src/lib/adapters.ts:128` (`computeScore`) counts **only** declarations with
status `VERIFIED` as satisfied; `UNCERTAIN`, `MISSING`, and `NOT_VISIBLE` all score as zero, with no
distinction between them in the number shown. This is arguably correct legal-metrology behavior
(an unread field genuinely isn't verified) — but it means a single-panel photo that correctly,
honestly reports "7 of 9 fields not visible in this frame, 2 read cleanly" renders as an 11%
**failure** indistinguishable from a photo where the product is actually non-compliant. Combined
with Bug A guaranteeing one whole rule category (font height) is permanently UNCERTAIN, your score
denominator has at least one field that can never pass, on every single inspection.

**This is why every product scores ~1/10 regardless of which product or which photo:** it isn't the
rule engine misjudging any particular product — it's the score arithmetic having a structurally
unreachable numerator (Bug A) and no visual language for "correctly cautious" vs "actually
non-compliant" (Bug B).

**Fix, in order:**
1. Wire `geometry.py`'s `detect_pdp_geometry()` + `calibration.py`'s `measure_pdp_area()` into the
   `/scan` and `/extract-preview` request path so `pdp_area_cm2` gets computed from the photo itself
   (this is literally what these modules were built for — see `geometry.py`'s own docstring, lines
   1–30, which says explicitly "produces evidence for calibration.py and the rule engine"). This is
   the single highest-leverage fix available: it unblocks an entire rule category that is currently
   dead on arrival.
2. Split the score UI into two numbers instead of one: **"Verified compliant: X/N"** (today's strict
   count) and **"Reviewed/attempted: Y/N"** (VERIFIED + confidently UNCERTAIN + confidently
   MISSING — i.e. "the system looked and formed a real judgment," as opposed to "never got the
   chance to look," e.g. Bug A's structurally-blocked font-height check). An inspector staring at
   "11%" with no context reasonably concludes the product or the tool is broken; staring at
   "2 verified / 4 correctly flagged for a second photo / 1 blocked pending a fix you're already
   making" tells them what to actually do next.
3. Build the small labelled-photo harness `ENGINEERING_ASSESSMENT_AND_ROADMAP.md`'s Step 9 already
   calls for (per-field ground truth on ~10 real photos → per-field precision/recall, per-rule
   PASS/UNCERTAIN/FAIL breakdown) **before** touching thresholds anywhere. You need to know, after
   fixes 1–2 land, how much of the remaining gap is genuine OCR weakness on curved surfaces (Section
   2) versus anything else. Do not loosen the rule engine's PASS/UNCERTAIN thresholds to make the
   number look better — that's the exact anti-pattern the roadmap's 18-invariant safety contract
   was written to prevent, and a confident wrong PASS is worse for this product's actual purpose
   than an honest low score.

---

## 4. What is genuinely working (do not re-litigate these)

- `run_ocr()` / `classify_fields()` (`ocr_extraction.py`) and `region_detection.py` are real,
  wired, and doing the job they were designed for — the *reading* half of the pipeline is not the
  problem.
- `/extract-preview` exists, is called at the right point in the frontend flow (`InspectionApp.tsx
  :713`), and does return real classified fields with per-field confidence and source image —
  the "confirm screen shows nothing" complaint from the previous brief is resolved. What's still
  missing is barcode as an identity source (Section 1) and geometry as a measurement source
  (Section 3), not the wiring of the preview call itself.
- `product_similarity.py`'s matching algorithm (phash + histogram) is sound; it just has an empty
  catalog behind it.
- The rule engine's conservatism (UNCERTAIN over false PASS) is a deliberate, correct design choice
  documented in `ENGINEERING_ASSESSMENT_AND_ROADMAP.md`'s invariants. Don't relax it to inflate the
  score — fix the UI's presentation of it and the missing inputs feeding it instead (Sections 1–3).

---

## 5. Ordered execution plan

1. **Wire `barcode_decode.py` into `/extract-preview` and `/scan`.** Highest leverage on the
   product-ID complaint; module is finished, just disconnected.
2. **Wire `geometry.py` + `calibration.py` into the same two endpoints** to compute `pdp_area_cm2`
   from the photo. Highest leverage on the score complaint; unblocks Rule 7(2) entirely.
3. **Rebuild `product_index.json` from real product photos**, not the synthetic dataset generator's
   output, so visual similarity matching has something to match against.
4. **Split the frontend score into "verified" vs "reviewed" counts** and stop rendering the
   random-hex product-ID fallback as if it were a real read.
5. **Only after 1–4 are in:** build the per-field/per-rule labelled harness and re-measure. Expect
   the number to still be well under 100% on curved-surface photos — that's the honest ceiling of
   what OCR can currently read off glare-heavy cylindrical packaging (Section 2), and is the next
   real piece of work, not a wiring fix.

Do these in this order. Steps 1–2 alone will very likely move you off "1/10 on everything," because
they eliminate two guaranteed-zero paths rather than improving accuracy at the margins.