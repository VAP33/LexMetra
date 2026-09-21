import cv2, os, pytesseract
from PIL import Image

for f in sorted(os.listdir("uploads")):
    if ("face_2" in f or "capture_2" in f or "back" in f.lower()) and f.endswith(('.jpg', '.jpeg', '.png')):
        path = os.path.join("uploads", f)
        img = cv2.imread(path)
        if img is not None:
            # check OCR for 10012026000226 or 10012
            txt = pytesseract.image_to_string(img)
            has_226 = "10012026000226" in txt or "000226" in txt
            has_243 = "10012026000243" in txt or "000243" in txt
            if has_226 or has_243 or "hershey" in f.lower():
                print(f"{f}: shape={img.shape}, has_226={has_226}, has_243={has_243}")
