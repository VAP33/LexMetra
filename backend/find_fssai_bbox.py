import cv2
import json
from PIL import Image
import os
import pytesseract

paths = ['uploads/Hershey\'s Back.jpeg', 'images new/Hershey\'s Back.jpeg']
for path in paths:
    if os.path.exists(path):
        im = Image.open(path)
        print("FOUND:", path, "size:", im.size)
        try:
            data = pytesseract.image_to_data(im, output_type=pytesseract.Output.DICT)
            for i in range(len(data['text'])):
                t = data['text'][i].strip()
                if any(k in t.lower() for k in ['10012026000226', '10012', 'lic', 'fssai', '000226']):
                    print(f"  MATCH '{t}' at x={data['left'][i]}, y={data['top'][i]}, w={data['width'][i]}, h={data['height'][i]}")
        except Exception as e:
            print("  OCR error:", e)
    else:
        print("NOT FOUND:", path)
