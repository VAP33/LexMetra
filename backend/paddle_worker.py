"""
Standalone PaddleOCR worker process for LexMetra runtime isolation.

This script runs in an independent child process. Any native DLL failure,
segmentation fault, or access violation inside PaddlePaddle, PaddleX,
ModelScope, or PyTorch is contained within this process and cannot crash
the parent LexMetra application or test suite.

Communication protocol: JSON-lines over stdin / stdout.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

# Suppress verbose third-party logs
logging.getLogger("ppocr").setLevel(logging.ERROR)
logging.getLogger().setLevel(logging.WARNING)


class PaddleWorker:
    def __init__(self) -> None:
        self._reader = None
        self._api_version: str = ""
        self._init_error: str = ""

    def _lazy_init(self) -> bool:
        if self._reader is not None:
            return True
        if self._init_error:
            return False

        try:
            from paddleocr import PaddleOCR

            # PaddleOCR 3.x. Disable document-level orientation/unwarping:
            # LexMetra performs its own per-region orientation and geometry.
            try:
                self._reader = PaddleOCR(
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    show_log=False,
                )
                self._api_version = "3.x"
            except TypeError:
                try:
                    self._reader = PaddleOCR(
                        use_doc_orientation_classify=False,
                        use_doc_unwarping=False,
                        use_textline_orientation=False,
                    )
                    self._api_version = "3.x"
                except TypeError:
                    # PaddleOCR 2.x compatibility fallback
                    self._reader = PaddleOCR(use_angle_cls=False, lang="en", show_log=False)
                    self._api_version = "2.x"
            return True
        except Exception as exc:
            self._init_error = f"{type(exc).__name__}: {exc}"
            return False

    @staticmethod
    def _json_payload(result: object) -> Optional[dict]:
        payload = getattr(result, "json", None)
        if callable(payload):
            try:
                payload = payload()
            except Exception:
                payload = None
        if isinstance(payload, dict):
            return payload.get("res", payload)
        if isinstance(result, dict):
            payload = result.get("res", result)
            return payload if isinstance(payload, dict) else None
        return None

    def _read_v3(self, image: np.ndarray, psm: int) -> List[Dict[str, Any]]:
        results = self._reader.predict(image)
        lines: List[Dict[str, Any]] = []
        for result in results or []:
            payload = self._json_payload(result)
            if not payload:
                continue
            texts = payload.get("rec_texts") or []
            scores = payload.get("rec_scores") or []
            boxes = payload.get("rec_boxes") or payload.get("rec_polys") or []
            for idx, text in enumerate(texts):
                text = str(text or "").strip()
                if not text:
                    continue
                try:
                    score = float(scores[idx]) if idx < len(scores) else 0.0
                except (TypeError, ValueError):
                    score = 0.0
                if idx >= len(boxes):
                    continue
                pts = np.asarray(boxes[idx], dtype=np.float32)
                if pts.size < 4:
                    continue
                x, y, w, h = cv2.boundingRect(pts.reshape(-1, 2))
                lines.append(
                    {
                        "text": text,
                        "bbox": [int(x), int(y), max(1, int(w)), max(1, int(h))],
                        "confidence": float(max(0.0, min(1.0, score))),
                        "psm": psm,
                    }
                )
        return lines

    def _read_v2(self, image: np.ndarray, psm: int) -> List[Dict[str, Any]]:
        raw = self._reader.ocr(image, cls=False)
        lines: List[Dict[str, Any]] = []
        for page in raw or []:
            for entry in page or []:
                try:
                    points, (text, score) = entry
                except (TypeError, ValueError):
                    continue
                if not str(text).strip():
                    continue
                pts = np.asarray(points, dtype=np.float32)
                x, y, w, h = cv2.boundingRect(pts)
                lines.append(
                    {
                        "text": str(text).strip(),
                        "bbox": [int(x), int(y), max(1, int(w)), max(1, int(h))],
                        "confidence": float(max(0.0, min(1.0, float(score)))),
                        "psm": psm,
                    }
                )
        return lines

    def read(self, image: np.ndarray, psm: int = 6) -> List[Dict[str, Any]]:
        if not self._lazy_init():
            raise RuntimeError(
                f"PaddleOCR failed to initialize ({self._init_error})"
            )
        if self._api_version == "3.x":
            return self._read_v3(image, psm)
        return self._read_v2(image, psm)

    def handle_request(self, req: Dict[str, Any]) -> Dict[str, Any]:
        cmd = req.get("cmd", "")

        if cmd == "ping":
            return {
                "status": "ok",
                "initialized": self._reader is not None,
                "api_version": self._api_version,
            }

        if cmd == "init":
            if self._lazy_init():
                return {"status": "ok", "api_version": self._api_version}
            return {"status": "error", "error": self._init_error}

        if cmd == "read":
            img_b64 = req.get("image")
            if not img_b64:
                return {"status": "error", "error": "No image payload provided"}
            try:
                raw_bytes = base64.b64decode(img_b64)
                arr = np.frombuffer(raw_bytes, dtype=np.uint8)
                image = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
                if image is None:
                    return {"status": "error", "error": "Failed to decode image"}
                psm = int(req.get("psm", 6))
                lines = self.read(image, psm=psm)
                return {"status": "ok", "lines": lines}
            except Exception as exc:
                return {
                    "status": "error",
                    "error": f"PaddleOCR inference failed ({type(exc).__name__}: {exc})",
                }

        if cmd == "shutdown":
            return {"status": "ok", "shutdown": True}

        return {"status": "error", "error": f"Unknown command: {cmd}"}


def main() -> None:
    worker = PaddleWorker()
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            line_str = line.strip()
            if not line_str:
                continue
            req = json.loads(line_str)
            resp = worker.handle_request(req)
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
            if resp.get("shutdown"):
                break
        except Exception as exc:
            err_resp = {"status": "error", "error": f"Worker loop error: {exc}"}
            try:
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()
            except Exception:
                pass


if __name__ == "__main__":
    main()
