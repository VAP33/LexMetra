import cv2
from pathlib import Path
from integrity_matching import find_dynamic_bbox, DEMO_REFERENCE_PACKAGES

raw_path = "uploads/Hershey's Back.jpeg"
raw_img = cv2.imread(raw_path)
print("Raw image shape:", raw_img.shape if raw_img is not None else None)

dyn_box_raw = find_dynamic_bbox(raw_img, "fssai_license_number", "10012026000226")
print("Dynamic bbox on raw:", dyn_box_raw)

# Check canonical files
canon_path = "uploads/ref_canon_Hershey's Back.jpeg"
if not Path(canon_path).exists():
    canon_path = "uploads/ref_canon_ref_bbf944c1_Hershey's Back.jpeg"

if Path(canon_path).exists():
    canon_img = cv2.imread(canon_path)
    print("Canon image shape:", canon_img.shape)
    dyn_box_canon = find_dynamic_bbox(canon_img, "fssai_license_number", "10012026000226")
    print("Dynamic bbox on canon:", dyn_box_canon)
else:
    print("Canon image not found at expected path")

# Let's inspect what's at [200, 532, 140, 32] vs [200, 545, 120, 20]
x, y, w, h = 200, 532, 140, 32
crop = raw_img[y:y+h, x:x+w]
cv2.imwrite("test_raw_532.jpg", crop)

# Let's do full OCR on raw_img and print all boxes and text between y=500 and y=600
import pytesseract
data = pytesseract.image_to_data(raw_img, output_type=pytesseract.Output.DICT)
for i in range(len(data['text'])):
    t = data['text'][i].strip()
    y_pos = data['top'][i]
    if 500 <= y_pos <= 600 and t:
        print(f"y={y_pos}, x={data['left'][i]}, w={data['width'][i]}, h={data['height'][i]}: '{t}'")
