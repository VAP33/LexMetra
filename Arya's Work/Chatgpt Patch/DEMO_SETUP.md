# LexMetra SIH MVP Demo Setup

## What changed in this patch

- PaddleOCR is now requested by default and integrated as a complementary OCR engine.
- The adapter supports the current PaddleOCR 3.x API and retains a legacy 2.x fallback.
- Tesseract remains available as the deterministic fallback when PaddleOCR cannot load.
- Visual Gemini recovery is enabled by default when `GEMINI_API_KEY` is configured.
- Visual recovery is only invoked for weak/partial fields and never replaces stronger OCR automatically.
- `/scan` and multi-surface session capture use the same visual-recovery path.
- Inline manufacturer/packer/importer declarations are extracted from the same OCR line instead of borrowing the next line.
- Explicit Common Name labels are now treated as labels, so they cannot be swallowed by manufacturer extraction.
- Cross-surface conflicts retain the winning evidence value for audit/UI visibility but are marked `REVIEW_REQUIRED` and are not treated as authoritative by the legal layer.
- Canonical declarations are persisted and reloaded from inspection history.
- `/health` now exposes active OCR engines and whether visual recovery is enabled, without exposing credentials.

## OCR installation on Windows

Use a 64-bit Python 3.9-3.13 environment. The official PaddlePaddle Windows documentation currently supports those Python versions and provides CPU/GPU wheels.

CPU:

```powershell
python -m pip install --upgrade pip
python -m pip install paddlepaddle==3.3.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
python -m pip install "paddleocr>=3.1,<4.0"
```

GPU, if the machine is configured for a supported CUDA build, use the matching official PaddlePaddle wheel instead of the CPU command. Do not randomly mix CUDA versions because apparently software enjoys this particular hobby.

Verify PaddlePaddle:

```powershell
python -c "import paddle; paddle.utils.run_check()"
```

Then start LexMetra normally. The backend will load PaddleOCR lazily on first OCR use.

## Verify the LexMetra pipeline

Open:

```text
GET /health
```

The response should show `PADDLEOCR` in `ocr.active_engines` when PaddleOCR loaded successfully. It should also show visual recovery enabled when a Gemini key is configured.

If PaddleOCR is unavailable, the response records the reason and Tesseract remains active. This is intentional MVP fallback behavior, not a fake success state.

## Demo behavior

The evidence hierarchy is:

1. PaddleOCR + Tesseract region OCR
2. deterministic field association and validation
3. image-aware VLM recovery for weak fields
4. deterministic legal rule engine
5. human review when evidence conflicts or is insufficient

The VLM is not the legal authority. It only recovers visible printed evidence. A fallback result is never converted into a fabricated PASS.
