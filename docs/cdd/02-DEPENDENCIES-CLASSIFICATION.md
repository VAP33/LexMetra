# 02 — `DEPENDENCIES/` Classification & Archiving Instruction

**Classified by:** ARCH-01. **Executed by:** DEVOPS-01 (per DEVOPS-01 package item 1).
**Rule:** ARCH-01 decides the classification; DEVOPS-01 executes it. **Archive, do not delete.**
**Last updated:** 2026-09-15 @ commit `ccd795c`

---

## 1. Verdict

The **entire `DEPENDENCIES/` tree is NON-CORE** and should be moved out of the active
working tree (to a clearly-labelled `archive/pre-lexmetra` branch or an external
location). **Nothing may be destroyed** — a later agent may need to diff against the
earlier snapshot.

## 2. Item-by-item classification

| Path | What it is | Classification | Action |
|---|---|---|---|
| `DEPENDENCIES/LMPC-Compliance-Platform/` | Earlier snapshot of this same project (LMPC = project's former name); `backend/` here differs from current `backend/` in ~63 files | Historical snapshot, operationally dead | Archive |
| `DEPENDENCIES/archives/LMPC_current.zip` (38 MB) | Zipped copy of the same snapshot | Redundant binary | Archive (candidate for `.gitignore` / Git LFS or removal from history if repo bloat matters) |
| `DEPENDENCIES/apply_scripts/apply_build02–06*.py` | Scripts that mechanically applied past BUILD_01–12 patch sessions | Historically useful, operationally dead | Archive |
| `DEPENDENCIES/patches/amendments_patch.diff` | A past diff patch | Historical | Archive |
| `DEPENDENCIES/need fixing/` (~26 loose `.py`/`.ts`/`.json`) | Ad-hoc staging copies of modules (schema.py, rule_engine.py, ocr_*, region_detection.py, InspectionApp.tsx, …) | Staging cruft, NOT the live modules | Archive |
| `DEPENDENCIES/docs/` (`12 hardening.txt`, `anti2.md`, `antigravity.md`) | Loose notes | Historical docs | Archive (or move to `docs/history/` if any are worth keeping — DEVOPS-01's call) |

## 3. ⚠️ Correction to Stage 1: `DEPENDENCIES/` is NOT reference-free

Stage 1 / the DEVOPS-01 package assumed "nothing in the active build references that
folder." **That assumption is wrong and was verified wrong by ARCH-01.** The following
active files contain a fallback reference to `DEPENDENCIES/images dataset`:

- `backend/tests/test_barcode_decode.py`
- `backend/tools/eval_pipeline.py`
- `backend/tools/bench_ocr.py`
- `backend/tools/dump_fields.py`
- `backend/tools/rebuild_product_index.py`
- `backend/tools/test_bru_real_scan.py`

They all use the pattern:

```
_ROOT / "images dataset"  if it exists  else  _ROOT / "DEPENDENCIES" / "images dataset"
```

**However — that fallback path is already dead.** Verified on disk:

- `images dataset` (repo root) → **does not exist**
- `DEPENDENCIES/images dataset` → **does not exist**
- The real dataset is at **`dataset/images dataset`** (plus `dataset/real images`).

So both branches of that ternary resolve to a non-existent path today. Consequences:

1. **Archiving `DEPENDENCIES/` will NOT break these references** — they don't resolve to
   anything real either way. The DEVOPS-01 concern ("verify nothing breaks") is
   satisfied *for the move itself*.
2. **But these references are stale bugs on their own.** Any tool/test relying on the
   dataset is pointing at the wrong place; the data moved to `dataset/`. This is a
   TEST-01 finding (it affects whether dataset-dependent tests can pass) and a small
   fix belongs to whoever owns those tools — **not** DEVOPS-01 (infra-only) and **not**
   ARCH-01 (no feature code). Flagged here, routed in §4.

## 4. Handoff / routing

- **DEVOPS-01:** Execute the archive move in §1–§2. After the move, run
  `docker compose up --build` and confirm success (nothing in the *active build path*
  references `DEPENDENCIES/`; the only references are the already-dead dataset
  fallbacks in tools/tests, which the build does not exercise). Then update
  `.gitignore` if the 38 MB zip is being pulled out of the tree.
- **TEST-01:** When establishing the baseline, note that dataset-dependent tools/tests
  point at a non-existent `images dataset` fallback; record whether
  `test_barcode_decode.py` skips, xfails, or errors because of it — don't let it be
  mistaken for a code regression.
- **Owner of `backend/tools/`** (OCR-01 / whoever picks up eval tooling): the correct
  dataset path is `dataset/images dataset`; the `DEPENDENCIES/...` fallback should be
  repointed or removed. Out of ARCH-01 and DEVOPS-01 scope; logged so it isn't lost.

## 5. Non-destructive guarantee

DEVOPS-01 must **archive, not delete**. Acceptable targets: a `archive/pre-lexmetra`
git branch, or an external/offline copy. The zip may be removed from the *working tree*
but a copy must survive somewhere referenceable.
