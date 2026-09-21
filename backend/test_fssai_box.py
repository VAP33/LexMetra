import cv2

canon_img = cv2.imread("uploads/ref_canon_Hershey's Back.jpeg")
x, y, w, h = 110, 136, 210, 32
crop = canon_img[y:y+h, x:x+w]
cv2.imwrite("test_canon_fssai_110_136.jpg", crop)

# Also let's check with padding
pad_crop = canon_img[max(0, y-10):min(canon_img.shape[0], y+h+10), max(0, x-10):min(canon_img.shape[1], x+w+10)]
cv2.imwrite("test_canon_fssai_padded.jpg", pad_crop)
print("Saved test_canon_fssai_110_136.jpg and test_canon_fssai_padded.jpg")
