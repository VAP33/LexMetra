# ANTI2.md
## Wiring-only execution brief — connect what's already built

This is a companion to `antigravity.md`, scoped narrowly to one thing: **plugging the two
finished-but-disconnected modules into the live request path, and removing the one genuinely dead
folder.** No new algorithms, no rule-engine changes, no threshold tuning. If `antigravity.md` is the
diagnosis, this is the patch list. Read the honest caveat in Section 2 before you assume this alone
fixes font-height scoring — it doesn't, fully, and you need to know that going in.

---

## 1. Wire `barcode_decode.py` into the live pipeline

**Target files:** `backend/main.py`, functions `/extract-preview` (~line 687) and `/scan` (~line 794).

**What to add**, right next to the existing `run_ocr(pil_img)` call in each endpoint's per-image loop:

```python
import barcode_decode
...
# inside the same per-image loop that already does: ocr_lines = run_ocr(pil_img)
symbol_result = barcode_decode.decode_symbols(img, image_id=image_id)
```

Then, after the loop (mirroring how `all_ocr_lines` is accumulated), merge across images:

```python
images_for_barcode = [(m["image_id"], img) for m, img in zip(images_meta, all_raw_images)]
merged_symbols = barcode_decode.decode_across_images(images_for_barcode)
```
(You'll need to keep a list of the raw `img` arrays alongside `images_meta` — they're already read
once per upload via `_read_image_upload`; don't re-read the file, just keep the reference.)

**Use it for `suggested_product_id`,** ahead of the existing `common_name` → `manufacturer_name` →
random-hex fallback chain (`main.py:752–763`):

```python
if merged_symbols.status == barcode_decode.SymbolStatus.DECODED and merged_symbols.symbols:
    best = merged_symbols.symbols[0]  # already deduped by payload in decode_across_images
    suggested_pid = best.gtin13 or suggested_pid
    id_source = "barcode_scan" if best.method == barcode_decode.ReadMethod.CV_BARS_DECODED else "barcode_ocr_checked"
    needs_confirmation = best.method != barcode_decode.ReadMethod.CV_BARS_DECODED
# else fall through to the existing common_name / manufacturer_name / random-hex chain
```

**Surface `needs_confirmation` and `merged_symbols.status == CONFLICTING` to the frontend** — add both
to the `suggested_details` / `field_extractions` response payload so `InspectionApp.tsx` can show
"read from barcode" vs "read from OCR digits, please confirm" vs "two different codes found across
your photos" instead of a flat product ID string. This is the module's own designed distinction
(see its docstring) — don't collapse it back down in the API response.

**Never render the random-hex fallback as if it were a read.** Tag it
`id_source: "unidentified_placeholder"` in the response so the frontend can grey it out / mark
"type manually" instead of showing it as a confident value (this was already flagged in
`antigravity.md` §1 — repeating here because it's part of the same edit).

**Test:** `backend/tests/test_barcode_decode.py` already exists and passes standalone — after wiring,
add one integration-level test (in `test_api_integration.py`'s style) asserting `/extract-preview`
returns a non-placeholder `product_id` for at least one of your real dataset images that has a
legible barcode.

---

## 2. Wire `geometry.py` + `calibration.py` into the live pipeline — **with an honest caveat**

**Target files:** same two endpoints, `backend/main.py`.

**What to add**, using the image already decoded for OCR:

```python
import geometry
import calibration

pkg_geom = geometry.detect_package_geometry(img, source_image=image_id, image_quality=iq)
pdp_geom = geometry.detect_pdp_geometry(img, source_image=image_id, package_geometry=pkg_geom,
                                         ocr_boxes=[l.bbox for l in ocr_lines if l.bbox])
```

This part is a pure win and safe to add immediately: `detect_package_geometry`/`detect_pdp_geometry`
need only the image (plus the OCR boxes you already have) — no new capture step, no new UI. It gives
you a real PDP bounding region instead of nothing, which is useful evidence on its own (e.g. for
`bbox_overlap_fraction` sanity checks) even before area is calibrated.

**The part that is NOT a pure wiring fix — read this before you promise font-height will start
passing:** `calibration.measure_pdp_area(pdp_geom, shape, calibration_info)` needs a
`CalibrationInfo` with `pixels_per_mm` set, and every path that produces one
(`calibrate_from_reference_object`, `calibrate_from_known_package_dimension`,
`calibrate_from_user_reference`, `calibrate_from_depth` — `calibration.py:70,104,139,172`) needs an
**actual physical measurement input that does not currently exist anywhere in this app**:
- `calibrate_from_reference_object` needs a known-size object (coin, ISO card) visible in the same
  frame — there is no reference-object detector in this repo today; nothing localises a coin or card
  in the image.
- `calibrate_from_known_package_dimension` needs an independently-known real-world dimension (e.g. a
  declared bottle height) — nothing in this codebase currently supplies that either; it is not the
  same as `net_quantity` (volume/weight doesn't imply a linear dimension without a shape assumption).
- `calibrate_from_user_reference` / `calibrate_from_depth` need explicit user input or depth-camera
  data — neither exists in the capture flow.

**So: wiring `geometry.py` in gets you PDP localisation for free today. It does NOT get you a
passing font-height rule until one of the calibration inputs above is actually captured.** The
cheapest realistic path, if you want Rule 7(2) to ever return PASS/FAIL instead of UNCERTAIN:
- **Fastest to ship:** ask the inspector to place a common reference object (a ₹1/₹2 coin, or a
  printed card of known size) in-frame for one photo per inspection, and add a small
  `reference_object_detection.py` (Hough circle for a coin, or a simple ArUco/checkerboard-style
  card detector) that returns a pixel length to feed `calibrate_from_reference_object`. This is new,
  small, scoped work — budget for it, don't fold it silently into "just wire geometry in."
- **Slower but zero new capture UX:** build a small lookup table of typical container dimensions by
  declared category + net quantity (e.g. "500 ml cylindrical bottle → typical height range") to feed
  `calibrate_from_known_package_dimension`, accepting its higher stated uncertainty
  (`scale_uncertainty_relative=0.08` by default) and lower confidence (0.55) — the module already
  discounts appropriately for this being an estimate, not a measurement.

Pick one. Either is real, scoped work — a day or two, not a wiring afternoon — but it's the only way
Section 3 of `antigravity.md` (the guaranteed-UNCERTAIN font-height rule) actually stops being
guaranteed. Do not skip this and expect the score to move on that specific rule; every other rule
that doesn't depend on `pdp_area_cm2` will benefit from the PDP-region wiring alone.

**Test:** `test_geometry.py` and `test_calibration.py` already exist and pass in isolation — add one
integration test that runs an image through the new `/scan` code path and asserts
`pdp_geometry.bbox is not None` for a well-lit dataset image, without asserting a calibrated area
(since that's still gated on the caveat above).

---

## 3. Clean up the dead CLAUDE 2 folder

`CLAUDE 2/proj/backend/` (vision_pipeline.py, evidence_fusion.py, orientation_ocr.py, ocr_engines.py,
live_capture.py, measurement.py, package_boundary.py, product_identity.py — ~32 MB with its own
tests) has zero references from canonical `backend/`. Its ideas were independently rewritten into
`ocr_engine.py` / `region_detection.py` / `orientation.py` by whoever did the real integration pass.
Confirm this with one grep before deleting anything:

```bash
grep -rn "vision_pipeline\|evidence_fusion\|orientation_ocr\|ocr_engines\|live_capture\|measurement\|package_boundary\|product_identity" backend/ frontend/ | grep -v "^CLAUDE 2"
```

If that returns nothing (it did when I checked), move the folder to an `archive/` directory outside
the active repo tree rather than deleting outright — some of its docstrings/tests may still be
useful reference for the reference-object detector in Section 2. Do not leave it sitting in the
active tree; it inflates repo size and misleads anyone auditing "what's integrated" the way it
misled the previous audit.

---

## 4. Order of operations

1. Section 1 (barcode) — isolated, additive, no dependency on Section 2. Ship first.
2. Section 2's wiring half (`detect_package_geometry`/`detect_pdp_geometry` only) — additive, ship
   second.
3. Decide and scope Section 2's calibration half (reference object vs lookup table) as its own
   ticket — don't block 1–2 on this decision.
4. Section 3 (archive CLAUDE 2) — do this last, after the grep confirms nothing depends on it, so a
   half-finished Section 1/2 branch can still reference it if you discover you need something from
   it mid-implementation.

---

## 5. On your other question: does adding Gemini (or any other VLM) simplify this?

**Not necessary right now, and it wouldn't fix any of the three problems above.** Concretely:

- There's already a VLM call in this codebase — `backend/vlm_verifier.py`, wired and called at
  `main.py:546`. It defaults to Claude (`ANTHROPIC_API_KEY`) but is explicitly provider-agnostic
  (`verify_ambiguous_field_with_provider` takes any `provider_call: Callable`), so swapping in Gemini
  later is a config change, not an architecture change, if you ever want to.
- Its job is narrow and deliberately so: given text OCR already extracted, decide if the *wording* is
  ambiguous enough to need human review. It never sees the image, never determines compliance, never
  supplies a missing fact — that scope is enforced in its own system prompt. It is not a general
  vision model and isn't trying to be.
- None of today's three failures are "the model isn't smart enough": the product-ID problem is a
  barcode decoder that's built and unused; the score problem is a measurement input that's never
  computed; the net-quantity problem is OCR failing on a specific glare/curvature case. A stronger
  VLM could plausibly help with the *last* one — reading garbled numerals off a curved, glared label
  is exactly the kind of fuzzy perception task a multimodal model is better at than classical OCR —
  but that's a targeted enhancement to `ocr_extraction.py`'s digit-repair path for hard cases, not a
  replacement for the rule engine, the geometry module, or the barcode decoder, and not something
  that fixes the two integration gaps above.

**Recommendation: don't add Gemini or any new model yet.** Finish Sections 1–2 first. If, after that,
your harness (per `antigravity.md` §3 step 3) shows OCR accuracy on curved/glared surfaces is still
the dominant remaining gap — not wiring, not scoring — that's the point where a VLM-assisted OCR
fallback (e.g. "if classical OCR confidence is below threshold on a numeric field, ask a multimodal
model to read just that cropped region") becomes worth scoping as its own ticket. Adding it earlier
just adds a second thing you'd have to debug on top of two things you already know are broken.

## 6. Is anything else missing, beyond integration and this pipeline?

Based on this audit: no other structural gap of this size. The rule engine, OCR/region-detection
core, auth/RBAC, PDF reporting, and DB persistence are all real, wired, and doing their job. The
three items above (barcode, geometry+calibration wiring, and the calibration-input gap they expose)
are the whole list. Get those integrated and re-measure with the harness before assuming anything
else needs building — most of what looks broken today is these three things compounding, not a
fourth hidden problem.

---

## 7. Swap the VLM default from Claude to Gemini (no Anthropic key on hand)

**You don't need to design anything new here — `vlm_verifier.py` was already built provider-agnostic
for exactly this situation.** `verify_ambiguous_field_with_provider()` (line 324) takes a plain
`provider_call: Callable[[str], str]` — it hands you the already-built user prompt as a string and
expects the model's raw text back. `_parse_response()` then validates/parses that text the same way
regardless of which vendor produced it. You're writing ~15 lines, not a new module.

**Get a free key:** Google AI Studio (`ai.google.dev` / `aistudio.google.com`) issues a Gemini API
key with no credit card and no billing account — sign in with a Google account and generate one.
The free tier is Flash-family models only (Pro moved behind billing during 2026); check
`ai.google.dev/pricing` for the current free model name and its requests-per-minute/per-day ceiling,
since Google has changed these more than once this year. For this use case — one short ambiguity
check per flagged field, not per image — even the tightest published free-tier ceiling is more than
enough; you are not doing high-volume image inference here, just short text-in/text-out calls.

**Wire it in:**

```python
# backend/config.py — add alongside ANTHROPIC_API_KEY
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# backend/vlm_verifier.py — add near the top, no changes to the existing
# Anthropic path or the parsing/contract logic
def _gemini_provider_call(prompt: str, *, model: str = "gemini-2.5-flash-lite") -> str:
    import google.generativeai as genai
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. The semantic verifier requires an "
            "explicit API key and does not fabricate an offline model result."
        )
    genai.configure(api_key=api_key)
    client = genai.GenerativeModel(model, system_instruction=VERIFIER_SYSTEM_PROMPT)
    response = client.generate_content(prompt, generation_config={"temperature": 0})
    return (response.text or "").strip()
```

Then at the one call site, `backend/main.py:546`, swap:

```python
# before
verification = verify_ambiguous_field(field, extracted_text, rule_requirement)
# after
verification = verify_ambiguous_field_with_provider(
    field, extracted_text, rule_requirement,
    provider_call=_gemini_provider_call, model="gemini-2.5-flash-lite", provider_name="gemini",
)
```

Add `google-generativeai` to `backend/requirements.txt`. That's the entire change — no change to
`_parse_response`, the JSON contract, the system prompt, or anything downstream that reads
`VerifierResult`. **Verify the exact free-tier model name at wiring time** (it may have moved on from
`gemini-2.5-flash-lite` by the time you implement this — check the AI Studio model list), the rest of
this snippet won't need to change.

One behavioral note worth knowing rather than discovering later: Anthropic's client raises
structured exceptions that `verify_ambiguous_field` catches narrowly; `_gemini_provider_call` above
lets any `google.generativeai` exception propagate up through `verify_ambiguous_field_with_provider`,
which is fine — that function already wraps `provider_call` failures into the same fail-closed
"review required" behavior (check its body once before you rely on this, since I'm describing it
from the source, not re-verifying that specific except-clause here).

---

## 8. Is preprocessing actually running? — yes, confirmed, no fix needed here

Checked directly: `backend/preprocess.py` is imported and actively called by `ocr_engine.py`
(`build_variants`, `measure_quality`, `recapture_guidance`) and `region_detection.py`
(`crop_screenshot_chrome`, `preprocess_region`, `_to_gray` in five separate detection paths) — not
just imported and unused like the barcode/geometry modules. It's doing real work on every OCR call:
CLAHE contrast normalization, glare suppression and glare masking, adaptive/Otsu thresholding,
unsharp masking, denoising, perspective rectification, and a quality-driven recipe planner
(`plan_recipes`) that picks which of those to apply per image based on measured blur/glare/exposure.
This is one of the genuinely solid, already-integrated parts of the pipeline — nothing to add here.
If curved-surface OCR is still weak after Sections 1–2 above are wired in, the fix is *tuning*
`preprocess.py`'s existing recipes for cylindrical glare (it's built for this, see `suppress_glare`/
`glare_mask`), not adding a new preprocessing stage from scratch.

---

## 9. YOLO — not used, and here's the honest state of region/layout detection

**Confirmed: no YOLO model anywhere in this codebase.** The only mentions of "YOLO" in the entire
repo are inside `PROJECT_MANIFEST.json` files, listed as a **known, unaddressed gap** — verbatim:
*"No trained OCR layout model... OCR relies on Tesseract general model + regex heuristics. Degrades
on real Indian product labels... fix: fine-tune LayoutLM or YOLO-based detector."* That's the
project's own prior self-assessment, not something this audit is newly discovering — it's just never
been acted on.

What you have instead, doing the same job, is `region_detection.py`: classical computer vision
(contour detection, MSER-style text-region candidates, symbology-region localisation) plus Tesseract
OCR and regex/heuristic field classification in `ocr_extraction.py`. This works reasonably on clean,
well-lit, flat labels and is the known weak point on the exact input you're testing with — curved,
glared, in-aisle phone photos — because a classical contour/MSER approach doesn't generalize across
lighting and curvature the way a model trained on real label photos would.

**Don't add YOLO as a fix for the current three problems.** None of Sections 1–3's failures
(product ID, net quantity, score) are "the region detector missed the field" in the cases I traced —
they're "the barcode decoder exists and isn't called," "the calibration input doesn't exist yet,"
and "OCR read garbled text on one hard photo." A trained layout/detection model is a real, valid
future improvement for exactly the class of failure in Section 2 of `antigravity.md` (curved-surface
OCR misses), but it's a genuinely separate project — data collection and labeling on your real photos,
training or fine-tuning, a new inference dependency — not something to fold into the wiring work in
Sections 1–2 here. Sequence it after you've re-measured with the harness and confirmed classical
region detection, not model capability, is the actual remaining bottleneck.

---

## 10. Google AR Depth / ARCore — not integrated; this is the missing half of calibration, not a bonus feature

This connects directly to the caveat in Section 2. `calibration.py` has a function named exactly for
this — `calibrate_from_depth(pixels_per_mm, depth_confidence, source_image)` (line 172) — but **it is
a pure function that takes an already-computed `pixels_per_mm` number as input; it does not talk to
a camera, ARCore, ARKit, or any depth sensor itself.** Confirmed by grep: the only callers anywhere in
the repo are its own unit test (`test_calibration.py`), which passes it a fabricated
`pixels_per_mm=3.0` — there is no ARCore Depth API call, no WebXR depth session, no LiDAR/ToF sensor
read, anywhere in `frontend/` or `backend/`. The name in the codebase describes an *intended* input
source, not a built integration. This is the same shape of gap as `calibrate_from_reference_object`
and `calibrate_from_known_package_dimension` discussed in Section 2 — three doors into calibration,
all currently unopened.

Of the three, depth is the **heaviest lift**, not the natural first choice:
- It requires a depth-capable device (most Android phones with ARCore Depth API support, iOS with
  LiDAR on Pro models — not universal across whatever hardware your inspectors actually carry).
- It requires native or WebXR-bridge capture code in the frontend that doesn't exist today (no
  ARCore/ARKit/WebXR reference anywhere in `frontend/react-app/src`), which is a real mobile-capture
  feature, not a backend wiring change.
- Depth-derived scale is only trusted here when `depth_confidence >= 0.75` (see the function body),
  so even after building it you'd still fall back to UNCERTAIN on lower-confidence reads — it doesn't
  remove the need for a fallback calibration path.

**Recommendation, unchanged from Section 2:** start with the reference-object detector (a coin or
printed card in frame) — it works on any phone, needs no AR capability check, and is a small,
self-contained classical-CV addition (`calibrate_from_reference_object` is already written and
waiting for exactly this input). Treat AR depth as a later enhancement for devices that support it,
not a blocker for getting Rule 7(2) off permanent UNCERTAIN.
