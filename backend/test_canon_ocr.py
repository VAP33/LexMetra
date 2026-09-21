import cv2
import pytesseract
from PIL import Image

canon_path = "uploads/ref_canon_Hershey's Back.jpeg"
canon_img = cv2.imread(canon_path)
print("Canon shape:", canon_img.shape)

data = pytesseract.image_to_data(canon_img, output_type=pytesseract.Output.DICT)
for i in range(len(data['text'])):
    t = data['text'][i].strip()
    if t:
        print(f"y={data['top'][i]}, x={data['left'][i]}, w={data['width'][i]}, h={data['height'][i]}: '{t}'")
