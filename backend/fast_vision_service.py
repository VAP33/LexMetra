# ---------------------------------------------------------------------------
# LexMetra - Fast Perception Vision Service
# High-speed multimodal perception for statutory Legal Metrology compliance
# ---------------------------------------------------------------------------

from groq_vision_service import (
    inspect_package_with_groq as inspect_package_fast,
    groq_result_to_classified_fields as perception_to_classified_fields,
    is_groq_available as is_vision_service_available,
    resize_and_compress_image,
    GROQ_INSPECTION_PROMPT as STATUTORY_INSPECTION_PROMPT,
)

__all__ = [
    "inspect_package_fast",
    "perception_to_classified_fields",
    "is_vision_service_available",
    "resize_and_compress_image",
    "STATUTORY_INSPECTION_PROMPT",
]
