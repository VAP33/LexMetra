"""
Diagnostic script to test boundary detection on all 3 faces of GEMS and all 3 faces of PRINGLES.
"""

import sys
from pathlib import Path
import cv2

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root / "backend"))

from package_preprocessor import detect_package_boundary

gems_faces = [
    ("Face 1", project_root / "images new" / "GEMS.jpg"),
    ("Face 2", project_root / "images new" / "GEMS 1.jpg"),
    ("Face 3", project_root / "images new" / "GEMS 2.jpg"),
]

pringles_dir = project_root / "DEPENDENCIES" / "images dataset"
pringles_faces = [
    ("Face 1", pringles_dir / "Screenshot_2026-09-06-22-07-11-58_92460851df6f172a4592fca41cc2d2e6.jpg"),
    ("Face 2", pringles_dir / "Screenshot_2026-09-06-22-06-55-06_92460851df6f172a4592fca41cc2d2e6.jpg"),
    ("Face 3", pringles_dir / "Screenshot_2026-09-06-22-07-02-74_92460851df6f172a4592fca41cc2d2e6.jpg"),
]

print("=== GEMS FACES BOUNDARY DETECTION ===")
for face_name, p in gems_faces:
    img = cv2.imread(str(p))
    res = detect_package_boundary(img)
    print(f"GEMS {face_name}: detected={res.get('detected')} method={res.get('method')} conf={res.get('confidence')}")
    print(f"  corners: {res.get('corners')}")

print("\n=== PRINGLES FACES BOUNDARY DETECTION ===")
for face_name, p in pringles_faces:
    img = cv2.imread(str(p))
    res = detect_package_boundary(img)
    print(f"PRINGLES {face_name}: detected={res.get('detected')} method={res.get('method')} conf={res.get('confidence')}")
    print(f"  corners: {res.get('corners')}")
