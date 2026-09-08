"""
Generates a SYNTHETIC demo dataset: programmatically-drawn mock package fronts with
declaration fields (MRP, net quantity, mfg date, manufacturer, consumer care).

WHY THIS EXISTS: your project plan (section 3.1) correctly requires REAL, human-verified
product photos as the actual dataset asset. This script does NOT produce that. What it
produces is useful for a different purpose: letting your CV/backend/rule-engine tracks
integration-test the full pipeline (detection -> OCR -> field extraction -> rule engine)
before real photography is done, and for demoing the paired compliant/violation concept
in section 3.1. Every image's metadata is tagged "synthetic": true so it can never be
mistaken for evidence. Do NOT present these as product photos to judges — present them
as "synthetic pipeline test fixtures" if asked, and show real photos for the actual demo.

Produces 25 products x 2 variants (1 compliant + 1 violation) = 50 images, split by
PRODUCT (not image) into train/val/test so there is no leakage — see plan section 3.4.
"""
import json
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

random.seed(42)

OUT_IMG = Path(__file__).parent / "images"
OUT_ANN = Path(__file__).parent / "annotations"
OUT_IMG.mkdir(exist_ok=True, parents=True)
OUT_ANN.mkdir(exist_ok=True, parents=True)

CATEGORIES = ["food", "beverage", "personal_care", "household"]
BRANDS = ["Suraj", "Nandini", "Kavya", "Trishul", "Amber", "Meadow", "Ganga", "Zenith",
          "Orbit", "Lotus", "Bharat", "Sunrise", "Anand", "Prime", "Coral", "Maple",
          "Delta", "Harmony", "Vivid", "Rustic", "Elm", "Nova", "Sable", "Ember", "Quartz"]
GENERIC_NAMES = {
    "food": ["Wheat Flour", "Basmati Rice", "Toor Dal", "Refined Sugar", "Cooking Oil"],
    "beverage": ["Fruit Juice", "Soft Drink", "Packaged Water", "Tea Powder", "Instant Coffee"],
    "personal_care": ["Herbal Soap", "Shampoo", "Toothpaste", "Talcum Powder", "Hand Wash"],
    "household": ["Detergent Powder", "Dish Wash Liquid", "Floor Cleaner", "Air Freshener", "Toilet Cleaner"],
}
UNITS = {"food": "g", "beverage": "ml", "personal_care": "ml", "household": "ml"}

try:
    FONT_REG = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    FONT_SM = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 9)
    FONT_TINY = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 5)
    FONT_TITLE = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
except Exception:
    FONT_REG = FONT_SM = FONT_TINY = FONT_TITLE = ImageFont.load_default()

VIOLATION_TYPES = ["missing_consumer_care", "missing_mfg_date", "tiny_mrp_font", "missing_mrp"]

W, H = 500, 700


def draw_field(draw, xy, label, value, font, color=(20, 20, 20)):
    x, y = xy
    draw.text((x, y), f"{label}: {value}", font=font, fill=color)
    bbox = draw.textbbox((x, y), f"{label}: {value}", font=font)
    return {"field": label.lower().replace(" ", "_"), "value": value, "bbox": list(bbox)}


def make_package(idx, brand, category, generic_name, mrp, qty, unit, mfg_date,
                  consumer_care, violation_type=None):
    img = Image.new("RGB", (W, H), (245, 243, 236))
    draw = ImageDraw.Draw(img)

    # background band (color varies by category, purely cosmetic)
    band_color = {"food": (214, 168, 84), "beverage": (94, 158, 173),
                  "personal_care": (196, 148, 178), "household": (140, 176, 120)}[category]
    draw.rectangle([0, 0, W, 160], fill=band_color)
    draw.text((30, 55), brand, font=FONT_TITLE, fill=(255, 255, 255))
    draw.text((30, 95), generic_name, font=FONT_REG, fill=(255, 255, 255))

    fields = []
    y = 200
    fields.append(draw_field(draw, (30, y), "Manufacturer", f"{brand} Industries Pvt Ltd, India", FONT_REG))
    y += 30
    fields.append(draw_field(draw, (30, y), "Common Name", generic_name, FONT_REG))
    y += 30
    fields.append(draw_field(draw, (30, y), "Net Quantity", f"{qty} {unit}", FONT_REG))
    y += 30

    if violation_type == "missing_mfg_date":
        pass  # omit entirely
    else:
        fields.append(draw_field(draw, (30, y), "Mfg Date", mfg_date, FONT_REG))
    y += 30

    if violation_type == "missing_mrp":
        pass
    elif violation_type == "tiny_mrp_font":
        fields.append(draw_field(draw, (30, y), "MRP", f"Rs.{mrp} (incl. all taxes)", FONT_TINY))
    else:
        fields.append(draw_field(draw, (30, y), "MRP", f"Rs.{mrp} (incl. all taxes)", FONT_REG))
    y += 30

    unit_price = round(mrp / qty * (1000 if unit in ("g", "ml") else 1), 2)
    fields.append(draw_field(draw, (30, y), "Unit Price", f"Rs.{unit_price}/kg or litre", FONT_REG))
    y += 30

    if violation_type == "missing_consumer_care":
        pass
    else:
        fields.append(draw_field(draw, (30, y), "Consumer Care", consumer_care, FONT_REG))
    y += 40

    draw.rectangle([20, 190, W - 20, y], outline=(120, 120, 120), width=1)

    fname = f"prod{idx:03d}_{'violation_' + violation_type if violation_type else 'compliant'}.png"
    img.save(OUT_IMG / fname)
    return fname, fields


def main():
    manifest = []
    products = []
    for i, brand in enumerate(BRANDS, start=1):
        category = CATEGORIES[i % len(CATEGORIES)]
        generic_name = random.choice(GENERIC_NAMES[category])
        unit = UNITS[category]
        qty = random.choice([100, 200, 250, 500, 1000] if unit == "g" else [100, 200, 500, 1000])
        mrp = round(random.uniform(15, 350), 2)
        mfg_date = f"{random.randint(1,12):02d}/2026"
        consumer_care = f"1800-{random.randint(100,999)}-{random.randint(1000,9999)} | care@{brand.lower()}.in"
        product_id = f"SYN-{i:03d}"
        products.append(product_id)

        # Compliant variant
        fname_c, fields_c = make_package(i, brand, category, generic_name, mrp, qty, unit,
                                          mfg_date, consumer_care, violation_type=None)
        manifest.append({
            "image_id": fname_c, "product_id": product_id, "synthetic": True,
            "category": category, "brand": brand, "violation_type": None,
            "expected_overall_status": "PASS",
            "mrp": mrp, "net_quantity_value": qty, "net_quantity_unit": unit,
            "fields": fields_c,
        })

        # Violation variant (paired, same product_id -> must stay in same split)
        vtype = VIOLATION_TYPES[i % len(VIOLATION_TYPES)]
        fname_v, fields_v = make_package(i, brand, category, generic_name, mrp, qty, unit,
                                          mfg_date, consumer_care, violation_type=vtype)
        manifest.append({
            "image_id": fname_v, "product_id": product_id, "synthetic": True,
            "category": category, "brand": brand, "violation_type": vtype,
            "expected_overall_status": "FAIL",
            "mrp": mrp, "net_quantity_value": qty, "net_quantity_unit": unit,
            "fields": fields_v,
        })

    # Split by PRODUCT, not image — no leakage (plan section 3.4)
    random.shuffle(products)
    n = len(products)
    train_p = set(products[: int(n * 0.6)])
    val_p = set(products[int(n * 0.6): int(n * 0.8)])
    test_p = set(products[int(n * 0.8):])

    def split_of(pid):
        if pid in train_p: return "train"
        if pid in val_p: return "val"
        return "test"

    for m in manifest:
        m["split"] = split_of(m["product_id"])

    (OUT_ANN / "annotations.json").write_text(json.dumps({
        "_meta": {
            "synthetic": True,
            "note": "Programmatically generated mock packaging for pipeline integration "
                    "testing only. NOT real product photography. Do not use as compliance evidence.",
            "total_images": len(manifest),
            "total_products": n,
        },
        "images": manifest,
    }, indent=2))

    print(f"Generated {len(manifest)} images across {n} products.")
    print(f"Split: train={len(train_p)} val={len(val_p)} test={len(test_p)} products")


if __name__ == "__main__":
    main()
