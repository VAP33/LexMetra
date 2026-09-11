"""Standalone PaddleOCR worker for native-runtime isolation.

The parent process communicates with this worker over JSON-lines. PaddleOCR is
imported only inside the child, so native DLL/access-violation failures cannot
take down the FastAPI/test parent.
"""
from __future__ import annotations

import base64
import json
import logging
import sys
from typing import Any, Dict, List

import cv2
import numpy as np

logging.getLogger("ppocr").setLevel(logging.ERROR)


class PaddleWorker:
    def __init__(self) -> None:
        self._reader = None
        self._api_version = ""
        self._init_error = ""

    def _lazy_init(self) -> bool:
        if self._reader is not None:
            return True
        if self._init_error:
            return False
        try:
            from paddleocr import PaddleOCR
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
                    self._reader = PaddleOCR(use_angle_cls=False, lang="en", show_log=False)
                    self._api_version = "2.x"
            return True
        except Exception as exc:
            self._init_error = f"{type(exc).__name__}: {exc}"
            return False

    @staticmethod
    def _payload(result: object) -> dict | None:
        value = getattr(result, "json", None)
        if callable(value):
            try:
                value = value()
            except Exception:
                value = None
        if isinstance(value, dict):
            value = value.get("res", value)
            return value if isinstance(value, dict) else None
        if isinstance(result, dict):
            value = result.get("res", result)
            return value if isinstance(value, dict) else None
        return None

    def _read_v3(self, image: np.ndarray, psm: int) -> List[Dict[str, Any]]:
        lines=[]
        for result in self._reader.predict(image) or []:
            payload=self._payload(result)
            if not payload: continue
            texts=payload.get("rec_texts") or []
            scores=payload.get("rec_scores") or []
            boxes=payload.get("rec_boxes") or payload.get("rec_polys") or []
            for i,text in enumerate(texts):
                text=str(text or "").strip()
                if not text or i >= len(boxes): continue
                pts=np.asarray(boxes[i],dtype=np.float32)
                if pts.size < 4: continue
                x,y,w,h=cv2.boundingRect(pts.reshape(-1,2))
                try: score=float(scores[i]) if i < len(scores) else 0.0
                except (TypeError,ValueError): score=0.0
                lines.append({"text":text,"bbox":[int(x),int(y),max(1,int(w)),max(1,int(h))],
                              "confidence":max(0.0,min(1.0,score)),"psm":psm})
        return lines

    def _read_v2(self, image: np.ndarray, psm: int) -> List[Dict[str, Any]]:
        lines=[]
        for page in self._reader.ocr(image, cls=False) or []:
            for entry in page or []:
                try: points,(text,score)=entry
                except (TypeError,ValueError): continue
                text=str(text).strip()
                if not text: continue
                pts=np.asarray(points,dtype=np.float32)
                x,y,w,h=cv2.boundingRect(pts)
                lines.append({"text":text,"bbox":[int(x),int(y),max(1,int(w)),max(1,int(h))],
                              "confidence":max(0.0,min(1.0,float(score))),"psm":psm})
        return lines

    def read(self,image:np.ndarray,psm:int=6):
        if not self._lazy_init():
            raise RuntimeError(f"PaddleOCR failed to initialize ({self._init_error})")
        return self._read_v3(image,psm) if self._api_version=="3.x" else self._read_v2(image,psm)

    def handle(self, req:dict)->dict:
        cmd=req.get("cmd","")
        if cmd=="ping":
            return {"status":"ok","initialized":self._reader is not None,"api_version":self._api_version}
        if cmd=="init":
            return {"status":"ok","api_version":self._api_version} if self._lazy_init() else {"status":"error","error":self._init_error}
        if cmd=="read":
            try:
                raw=base64.b64decode(req.get("image",""))
                image=cv2.imdecode(np.frombuffer(raw,dtype=np.uint8),cv2.IMREAD_UNCHANGED)
                if image is None: return {"status":"error","error":"Failed to decode image"}
                return {"status":"ok","lines":self.read(image,int(req.get("psm",6)))}
            except Exception as exc:
                return {"status":"error","error":f"PaddleOCR inference failed ({type(exc).__name__}: {exc})"}
        if cmd=="shutdown": return {"status":"ok","shutdown":True}
        return {"status":"error","error":f"Unknown command: {cmd}"}


def main():
    worker=PaddleWorker()
    for line in sys.stdin:
        if not line.strip(): continue
        try:
            response=worker.handle(json.loads(line))
        except Exception as exc:
            response={"status":"error","error":f"Worker loop error: {exc}"}
        print(json.dumps(response),flush=True)
        if response.get("shutdown"): break


if __name__=="__main__":
    main()
