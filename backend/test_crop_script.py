import cv2
import json
import os

img = cv2.imread("uploads/Hershey's Back.jpeg")
print("Raw shape:", img.shape if img is not None else None)
# Let's crop [200, 532, 140, 32]
if img is not None:
    x, y, w, h = 200, 532, 140, 32
    c = img[y:y+h, x:x+w]
    cv2.imwrite("test_raw_crop_532.jpg", c)
    print("Saved test_raw_crop_532.jpg")

    x2, y2, w2, h2 = 200, 545, 130, 25
    c2 = img[y2:y2+h2, x2:x2+w2]
    cv2.imwrite("test_raw_crop_545.jpg", c2)

# Check all files in uploads for any canonical images
for f in os.listdir("uploads"):
    if "canon" in f.lower() or "hershey" in f.lower():
        print("Uploads file:", f)
