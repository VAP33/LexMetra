import cv2

canon_img = cv2.imread("uploads/ref_canon_Hershey's Back.jpeg")

# Let's crop strips at y=100..200
for y in range(100, 220, 20):
    c = canon_img[y:y+35, 80:350]
    cv2.imwrite(f"canon_strip_{y}.jpg", c)
    print(f"Saved canon_strip_{y}.jpg")
