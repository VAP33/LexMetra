import cv2
import json

raw_img = cv2.imread("uploads/Hershey's Back.jpeg")
canon_img = cv2.imread("uploads/ref_canon_Hershey's Back.jpeg")

print("Raw shape:", raw_img.shape)
print("Canon shape:", canon_img.shape)

# Let's test on raw:
# At raw: y=538..565, x=200..330 was "No. 10012026000226"
crop_raw = raw_img[535:570, 200:340]
cv2.imwrite("test_raw_fssai_correct.jpg", crop_raw)

# Let's test on canon:
# At canon: y=135..165, x=100..320
crop_canon = canon_img[130:170, 95:320]
cv2.imwrite("test_canon_fssai_correct.jpg", crop_canon)
