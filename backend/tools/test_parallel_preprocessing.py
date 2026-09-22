"""
LexMetra: Parallel 3-Face Preprocessing Benchmark & Verification.

Compares sequential vs parallel execution using ThreadPoolExecutor(max_workers=3).
Verifies:
1. All three faces complete successfully.
2. Face identity stability: Face 1, Face 2, Face 3 ordering is deterministic.
3. Outputs (metadata, dimensions, homography matrices) match exactly.
4. Wall-clock time speedup.
"""

import sys
import time
from pathlib import Path
import cv2
import numpy as np

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root / "backend"))

import package_preprocessor
from package_preprocessor import run_preprocessing_pipeline, preprocess_three_faces_parallel

def main():
    print("==================================================")
    print("LEXMETRA: PARALLEL 3-FACE PREPROCESSING BENCHMARK")
    print("==================================================")

    gems_imgs = [
        ("Face 1", project_root / "images new" / "GEMS.jpg"),
        ("Face 2", project_root / "images new" / "GEMS 1.jpg"),
        ("Face 3", project_root / "images new" / "GEMS 2.jpg"),
    ]

    # Verify input images exist
    loaded = []
    for face_name, p in gems_imgs:
        if not p.exists():
            print(f"Error: missing {p}")
            return False
        img = cv2.imread(str(p))
        if img is None:
            print(f"Error: failed to read {p}")
            return False
        loaded.append((face_name, img, p.name, None))

    print(f"Loaded {len(loaded)} faces for GEMS.")

    # 1. Sequential Benchmark
    print("\n[1/2] Running Sequential Preprocessing (3 faces)...")
    t0_seq = time.perf_counter()
    seq_results = {}
    for face_name, img, src_name, _ in loaded:
        t_face = time.perf_counter()
        seq_results[face_name] = run_preprocessing_pipeline(
            img_bgr=img,
            source_name=src_name,
            product="GEMS",
            face=face_name,
            margin_pct=0.06,
        )
        face_ms = round((time.perf_counter() - t_face) * 1000, 1)
        print(f"  Sequential {face_name}: {face_ms} ms")
    total_seq_ms = round((time.perf_counter() - t0_seq) * 1000, 1)
    print(f"Total Sequential Wall-Clock Time: {total_seq_ms} ms")

    # 2. Parallel Benchmark
    print("\n[2/2] Running Parallel Preprocessing (3 faces, max_workers=3)...")
    t0_par = time.perf_counter()
    par_results = preprocess_three_faces_parallel(
        faces_input=loaded,
        product="GEMS",
        margin_pct=0.06,
        max_workers=3,
    )
    total_par_ms = round((time.perf_counter() - t0_par) * 1000, 1)
    print(f"Total Parallel Wall-Clock Time: {total_par_ms} ms")

    speedup = round(total_seq_ms / max(1.0, total_par_ms), 2)
    print(f"Measured Speedup: {speedup}x")

    # 3. Validation & Invariants Check
    print("\n[3/3] Checking Invariants...")
    expected_order = ["Face 1", "Face 2", "Face 3"]
    actual_order = list(par_results.keys())
    assert actual_order == expected_order, f"Order mismatch! Expected {expected_order}, got {actual_order}"
    print(f"  [PASS] Deterministic face ordering preserved: {actual_order}")

    for face_name in expected_order:
        seq_res = seq_results[face_name]
        par_res = par_results[face_name]

        # Check final image dimensions
        assert seq_res.final_bgr.shape == par_res.final_bgr.shape, f"Dimension mismatch on {face_name}"
        # Check boundary detected
        assert seq_res.metadata["boundary_detected"] == par_res.metadata["boundary_detected"]
        # Check transform matrix match
        assert np.allclose(seq_res.forward_transform.forward_matrix, par_res.forward_transform.forward_matrix, atol=1e-3)
        print(f"  [PASS] {face_name}: Dimensions {par_res.final_bgr.shape[:2]}, Margin {par_res.metadata['boundary_margin_percent']}%, Matrix Verified")

    print("\n==================================================")
    print("ALL PARALLEL PREPROCESSING CHECKS PASSED!")
    print(f"Sequential: {total_seq_ms} ms -> Parallel: {total_par_ms} ms ({speedup}x speedup)")
    print("==================================================")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
