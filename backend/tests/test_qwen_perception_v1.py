import json
import numpy as np
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import qwen_perception
from geometry import CoordinateSpace, CoordinateTransform
from qwen_perception import (
    DeclarationEvidenceItem,
    GroqQwenProvider,
    OpenRouterQwenProvider,
    PerceptionResult,
    PreparedPerceptionBatch,
    get_groq_recent_logs,
    perception_to_classified_fields,
    prepare_perception_batch,
    validate_semantic_declarations,
)


def _dummy_transform(w=600, h=400):
    return CoordinateTransform(
        source_space=CoordinateSpace.CANONICAL_PIXEL,
        target_space=CoordinateSpace.ORIGINAL_PIXEL,
        matrix=[[2.0, 0.0, 10.0], [0.0, 2.0, 20.0], [0.0, 0.0, 1.0]],
        source_dims=(w, h),
        target_dims=(w * 2, h * 2),
    )


def test_semantic_validation_rejects_includes_as_net_quantity():
    # 'Includes: 17g' must NOT become NET_QUANTITY
    items = [
        DeclarationEvidenceItem(
            field="NET_QUANTITY",
            value="17g",
            evidence_text="Includes: 17g",
            face="Face 1",
            status="DETECTED",
        ),
        DeclarationEvidenceItem(
            field="NET_QUANTITY",
            value="17g",
            evidence_text="Includes 17g",
            face="Face 2",
            status="DETECTED",
        ),
        # Real net quantity should be accepted
        DeclarationEvidenceItem(
            field="NET_QUANTITY",
            value="100g",
            evidence_text="Net Quantity: 100g",
            face="Face 3",
            status="DETECTED",
        ),
    ]
    validated = validate_semantic_declarations(items)
    assert len(validated) == 1
    assert validated[0].value == "100g"
    assert validated[0].face == "Face 3"


def test_semantic_validation_rejects_per_serve_as_usp():
    # 'Per 15.69 g Serve' must NOT become USP
    items = [
        DeclarationEvidenceItem(
            field="USP",
            value="₹15.69",
            evidence_text="Per 15.69 g Serve",
            face="Face 1",
            status="DETECTED",
        ),
        DeclarationEvidenceItem(
            field="USP",
            value="15.69 g",
            evidence_text="Per 15.69 g Serve",
            face="Face 1",
            status="DETECTED",
        ),
        # Printed USP with monetary value and unit basis should be accepted
        DeclarationEvidenceItem(
            field="USP",
            value="₹1.08/g",
            evidence_text="USP Rs. 1.08 / g",
            face="Face 2",
            status="DETECTED",
        ),
    ]
    validated = validate_semantic_declarations(items)
    assert len(validated) == 1
    assert validated[0].value == "₹1.08/g"
    assert validated[0].face == "Face 2"


def test_semantic_validation_rejects_mrp_as_usp():
    items = [
        DeclarationEvidenceItem(
            field="MRP",
            value="₹215.00",
            evidence_text="MRP Rs. 215.00",
            face="Face 1",
            status="DETECTED",
        ),
        DeclarationEvidenceItem(
            field="USP",
            value="₹215.00",
            evidence_text="Rs. 215.00",
            face="Face 1",
            status="DETECTED",
        ),
    ]
    validated = validate_semantic_declarations(items)
    fields = [it.field for it in validated]
    assert "MRP" in fields
    assert "USP" not in fields  # Equal to total package MRP and no basis


@pytest.mark.asyncio
async def test_single_face_extraction():
    provider = GroqQwenProvider(api_key="gsk_dummy_test_key_123456789")
    img = np.zeros((200, 300, 3), dtype=np.uint8)
    transform = _dummy_transform(300, 200)
    faces = [("Face 1", img, transform)]

    dummy_groq_resp = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "product_name": {"value": "Test Snack", "face": "Face 1"},
                        "declarations": [
                            {
                                "field": "NET_QUANTITY",
                                "value": "50g",
                                "unit": "g",
                                "face": "Face 1",
                                "evidence_text": "Net Wt 50g",
                                "bbox": [10, 10, 50, 20],
                                "coordinate_space": "CANONICAL",
                                "confidence": 0.95,
                                "status": "DETECTED",
                            }
                        ],
                        "face_metadata": {"Face 1": {"inferred_surface_hypothesis": "PDP"}},
                        "image_quality": {"Face 1": {"package_boundary": "good"}},
                    })
                }
            }
        ],
        "usage": {"prompt_tokens": 1100, "completion_tokens": 120, "total_tokens": 1220},
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = dummy_groq_resp
    mock_resp.headers = {}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await provider.perceive(faces)

        assert mock_post.call_count == 1
        assert res.product_name == "Test Snack"
        assert len(res.declarations) == 1
        assert res.declarations[0].face == "Face 1"
        assert res.declarations[0].value == "50g"
        # Verify canonical -> original coordinate transform was applied
        assert res.declarations[0].bbox_original is not None
        ox, oy, ow, oh = res.declarations[0].bbox_original
        assert ox == 10.0 * 2.0 + 10.0  # 30.0


@pytest.mark.asyncio
async def test_three_faces_sent_in_exactly_one_request():
    provider = GroqQwenProvider(api_key="gsk_dummy_test_key_123456789")
    img = np.zeros((400, 400, 3), dtype=np.uint8)
    faces = [
        ("Face 1", img, _dummy_transform(400, 400)),
        ("Face 2", img, _dummy_transform(400, 400)),
        ("Face 3", img, _dummy_transform(400, 400)),
    ]

    dummy_groq_resp = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "product_name": {"value": "Biscuits", "face": "Face 1"},
                        "declarations": [
                            {
                                "field": "MRP",
                                "value": "₹50.00",
                                "face": "Face 1",
                                "evidence_text": "MRP ₹50.00",
                                "bbox": [10, 10, 40, 20],
                                "coordinate_space": "CANONICAL",
                                "confidence": 0.95,
                                "status": "DETECTED",
                            },
                            {
                                "field": "NET_QUANTITY",
                                "value": "120g",
                                "unit": "g",
                                "face": "Face 2",
                                "evidence_text": "Net Qty: 120g",
                                "bbox": [15, 15, 45, 25],
                                "coordinate_space": "CANONICAL",
                                "confidence": 0.92,
                                "status": "DETECTED",
                            },
                            {
                                "field": "MFD",
                                "value": "01/2026",
                                "face": "Face 3",
                                "evidence_text": "MFD 01/2026",
                                "bbox": [20, 20, 50, 20],
                                "coordinate_space": "CANONICAL",
                                "confidence": 0.90,
                                "status": "DETECTED",
                            },
                        ],
                        "face_metadata": {
                            "Face 1": {"inferred_surface_hypothesis": "PDP"},
                            "Face 2": {"inferred_surface_hypothesis": "Side"},
                            "Face 3": {"inferred_surface_hypothesis": "Back"},
                        },
                        "image_quality": {
                            "Face 1": {"package_boundary": "good"},
                            "Face 2": {"package_boundary": "good"},
                            "Face 3": {"package_boundary": "good"},
                        },
                    })
                }
            }
        ],
        "usage": {"prompt_tokens": 1950, "completion_tokens": 280, "total_tokens": 2230},
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = dummy_groq_resp
    mock_resp.headers = {}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await provider.perceive(faces)

        # Confirm exactly ONE Qwen request was made for all 3 faces
        assert mock_post.call_count == 1

        # Check payload contained all three faces
        call_args, call_kwargs = mock_post.call_args
        payload = call_kwargs.get("json") or {}
        user_content = payload["messages"][1]["content"]
        # Extract text labels
        texts = [c["text"] for c in user_content if c["type"] == "text"]
        assert any("Face 1" in t for t in texts)
        assert any("Face 2" in t for t in texts)
        assert any("Face 3" in t for t in texts)

        # Confirm declarations maintain Face 1, Face 2, Face 3 identity
        face_map = {d.field: d.face for d in res.declarations}
        assert face_map["MRP"] == "Face 1"
        assert face_map["NET_QUANTITY"] == "Face 2"
        assert face_map["MFD"] == "Face 3"

        # Check field bridging preserves coordinates and face attribution
        classified = perception_to_classified_fields(res)
        assert classified["mrp"]["face"] == "Face 1"
        assert classified["net_quantity"]["face"] == "Face 2"
        assert classified["mfg_date"]["face"] == "Face 3"


@pytest.mark.asyncio
async def test_two_faces_sent_in_exactly_one_request():
    provider = GroqQwenProvider(api_key="gsk_dummy_test_key_123456789")
    img = np.zeros((300, 300, 3), dtype=np.uint8)
    faces = [
        ("Face 1", img, _dummy_transform(300, 300)),
        ("Face 2", img, _dummy_transform(300, 300)),
    ]

    dummy_groq_resp = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "product_name": {"value": "Juice", "face": "Face 1"},
                        "declarations": [
                            {
                                "field": "NET_QUANTITY",
                                "value": "1 L",
                                "unit": "l",
                                "face": "Face 1",
                                "evidence_text": "Net Vol: 1 L",
                                "bbox": [10, 10, 40, 20],
                                "status": "DETECTED",
                            },
                            {
                                "field": "MRP",
                                "value": "₹99.00",
                                "face": "Face 2",
                                "evidence_text": "MRP ₹99.00",
                                "bbox": [20, 20, 50, 20],
                                "status": "DETECTED",
                            },
                        ],
                        "face_metadata": {},
                        "image_quality": {},
                    })
                }
            }
        ],
        "usage": {"prompt_tokens": 1500, "completion_tokens": 180, "total_tokens": 1680},
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = dummy_groq_resp
    mock_resp.headers = {}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await provider.perceive(faces)

        assert mock_post.call_count == 1
        call_args, call_kwargs = mock_post.call_args
        payload = call_kwargs.get("json") or {}
        user_content = payload["messages"][1]["content"]
        texts = [c["text"] for c in user_content if c["type"] == "text"]
        assert any("Face 1" in t for t in texts)
        assert any("Face 2" in t for t in texts)
        assert not any("Face 3" in t for t in texts)


@pytest.mark.asyncio
async def test_cache_deduplication_avoids_duplicate_groq_calls():
    provider = GroqQwenProvider(api_key="gsk_dummy_test_key_123456789")
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    faces = [("Face 1", img, _dummy_transform(200, 200))]

    dummy_groq_resp = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "product_name": {"value": "Soap", "face": "Face 1"},
                        "declarations": [],
                        "face_metadata": {},
                        "image_quality": {},
                    })
                }
            }
        ],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 50, "total_tokens": 1050},
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = dummy_groq_resp
    mock_resp.headers = {}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        # First call hits API
        res1 = await provider.perceive(faces)
        assert mock_post.call_count == 1
        assert res1.product_name == "Soap"

        # Second call with same faces uses cache (0 additional HTTP calls)
        res2 = await provider.perceive(faces)
        assert mock_post.call_count == 1
        assert res2.product_name == "Soap"


@pytest.mark.asyncio
async def test_groq_429_rate_limit_controlled_retry_and_failover_to_openrouter():
    """
    Primary Groq provider receives HTTP 429:
    - performs at most ONE controlled retry
    - if retry fails, fails over to OpenRouter for the same model
    - OpenRouter succeeds with the same prepared batch
    """
    fallback = OpenRouterQwenProvider(api_key="sk-or-v1-dummy-fallback-key")
    provider = GroqQwenProvider(api_key="gsk_dummy_test_key_123456789", fallback_provider=fallback)
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    faces = [("Face 1", img, _dummy_transform(100, 100))]

    mock_429 = MagicMock()
    mock_429.status_code = 429
    mock_429.text = '{"error":{"message":"Rate limit reached for model qwen/qwen3.8-27b. Please try again in 0.05s."}}'
    mock_429.headers = {"retry-after": "0.05"}

    mock_openrouter_200 = MagicMock()
    mock_openrouter_200.status_code = 200
    mock_openrouter_200.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "product_name": {"value": "Fallback Cookie", "face": "Face 1"},
                        "declarations": [
                            {
                                "field": "MRP",
                                "value": "₹30.00",
                                "face": "Face 1",
                                "evidence_text": "MRP ₹30",
                                "bbox": [5, 5, 20, 10],
                                "status": "DETECTED",
                            }
                        ],
                    })
                }
            }
        ],
        "usage": {"prompt_tokens": 1200, "completion_tokens": 80, "total_tokens": 1280},
    }

    # Calls sequence:
    # 1: Groq attempt 1 -> 429
    # 2: Groq controlled retry (attempt 2) -> 429
    # 3: OpenRouter fallback request -> 200
    calls = []

    async def mock_post(url, *args, **kwargs):
        calls.append(url)
        if "api.groq.com" in url:
            return mock_429
        elif "openrouter.ai" in url:
            return mock_openrouter_200
        raise ValueError(f"Unexpected url: {url}")

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        res = await provider.perceive(faces)

        # Verify Groq was called exactly twice (attempt 1 + 1 controlled retry)
        groq_calls = [c for c in calls if "api.groq.com" in c]
        openrouter_calls = [c for c in calls if "openrouter.ai" in c]

        assert len(groq_calls) == 2, f"Expected 2 Groq calls, got {len(groq_calls)}"
        assert len(openrouter_calls) == 1, f"Expected 1 OpenRouter fallback call, got {len(openrouter_calls)}"
        assert res.provider_name == "OpenRouterQwenProvider"
        assert res.used_fallback is True
        assert res.product_name == "Fallback Cookie"
        assert len(res.declarations) == 1
        assert res.declarations[0].field == "MRP"


@pytest.mark.asyncio
async def test_groq_429_retry_success_no_failover():
    """
    Primary Groq provider receives HTTP 429 on attempt 1, but controlled retry succeeds:
    - OpenRouter is NOT called
    - provider_name="GroqQwenProvider", used_fallback=False
    """
    fallback = OpenRouterQwenProvider(api_key="sk-or-v1-dummy-fallback-key")
    provider = GroqQwenProvider(api_key="gsk_dummy_test_key_123456789", fallback_provider=fallback)
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    faces = [("Face 1", img, _dummy_transform(100, 100))]

    mock_429 = MagicMock()
    mock_429.status_code = 429
    mock_429.text = '{"error":{"message":"Rate limit reached. Please try again in 0.05s."}}'
    mock_429.headers = {"retry-after": "0.05"}

    mock_groq_200 = MagicMock()
    mock_groq_200.status_code = 200
    mock_groq_200.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "product_name": {"value": "Groq Cookie", "face": "Face 1"},
                        "declarations": [],
                    })
                }
            }
        ],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 50, "total_tokens": 1050},
    }

    call_count = 0

    async def mock_post(url, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        assert "api.groq.com" in url
        if call_count == 1:
            return mock_429
        return mock_groq_200

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        res = await provider.perceive(faces)

        assert call_count == 2
        assert res.provider_name == "GroqQwenProvider"
        assert res.used_fallback is False
        assert res.product_name == "Groq Cookie"


@pytest.mark.asyncio
async def test_groq_transient_5xx_failover_to_openrouter():
    """
    Groq returns 500 on attempt 1, 503 on retry -> fails over to OpenRouter.
    """
    fallback = OpenRouterQwenProvider(api_key="sk-or-v1-dummy-fallback-key")
    provider = GroqQwenProvider(api_key="gsk_dummy_test_key_123456789", fallback_provider=fallback)
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    faces = [("Face 1", img, _dummy_transform(100, 100))]

    mock_500 = MagicMock()
    mock_500.status_code = 500
    mock_500.text = "Internal Server Error"

    mock_openrouter_200 = MagicMock()
    mock_openrouter_200.status_code = 200
    mock_openrouter_200.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "product_name": {"value": "OpenRouter Result", "face": "Face 1"},
                        "declarations": [],
                    })
                }
            }
        ],
        "usage": {"prompt_tokens": 1100, "completion_tokens": 40},
    }

    calls = []

    async def mock_post(url, *args, **kwargs):
        calls.append(url)
        if "api.groq.com" in url:
            return mock_500
        elif "openrouter.ai" in url:
            return mock_openrouter_200

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        res = await provider.perceive(faces)

        groq_calls = [c for c in calls if "api.groq.com" in c]
        openrouter_calls = [c for c in calls if "openrouter.ai" in c]
        assert len(groq_calls) == 2
        assert len(openrouter_calls) == 1
        assert res.provider_name == "OpenRouterQwenProvider"
        assert res.used_fallback is True


@pytest.mark.asyncio
async def test_groq_timeout_failover_to_openrouter():
    """
    Groq times out on attempt 1 and attempt 2 -> fails over to OpenRouter.
    """
    import httpx
    fallback = OpenRouterQwenProvider(api_key="sk-or-v1-dummy-fallback-key")
    provider = GroqQwenProvider(api_key="gsk_dummy_test_key_123456789", fallback_provider=fallback)
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    faces = [("Face 1", img, _dummy_transform(100, 100))]

    mock_openrouter_200 = MagicMock()
    mock_openrouter_200.status_code = 200
    mock_openrouter_200.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "product_name": {"value": "Recovered After Timeout", "face": "Face 1"},
                        "declarations": [],
                    })
                }
            }
        ],
        "usage": {"prompt_tokens": 1100, "completion_tokens": 40},
    }

    calls = []

    async def mock_post(url, *args, **kwargs):
        calls.append(url)
        if "api.groq.com" in url:
            raise httpx.ReadTimeout("Groq connection timed out")
        elif "openrouter.ai" in url:
            return mock_openrouter_200

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        res = await provider.perceive(faces)

        assert len([c for c in calls if "api.groq.com" in c]) == 2
        assert len([c for c in calls if "openrouter.ai" in c]) == 1
        assert res.provider_name == "OpenRouterQwenProvider"
        assert res.used_fallback is True


@pytest.mark.asyncio
async def test_groq_malformed_response_immediate_failover():
    """
    Groq returns HTTP 200 but content is invalid JSON -> immediately fails over to OpenRouter.
    """
    fallback = OpenRouterQwenProvider(api_key="sk-or-v1-dummy-fallback-key")
    provider = GroqQwenProvider(api_key="gsk_dummy_test_key_123456789", fallback_provider=fallback)
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    faces = [("Face 1", img, _dummy_transform(100, 100))]

    mock_groq_malformed = MagicMock()
    mock_groq_malformed.status_code = 200
    mock_groq_malformed.json.return_value = {
        "choices": [{"message": {"content": "This is raw non-JSON text from Groq!"}}]
    }

    mock_openrouter_200 = MagicMock()
    mock_openrouter_200.status_code = 200
    mock_openrouter_200.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "product_name": {"value": "Valid From OpenRouter", "face": "Face 1"},
                        "declarations": [],
                    })
                }
            }
        ],
        "usage": {"prompt_tokens": 1100, "completion_tokens": 40},
    }

    calls = []

    async def mock_post(url, *args, **kwargs):
        calls.append(url)
        if "api.groq.com" in url:
            return mock_groq_malformed
        elif "openrouter.ai" in url:
            return mock_openrouter_200

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        res = await provider.perceive(faces)

        # Groq should NOT retry non-retryable malformed response; it should immediately failover
        assert len([c for c in calls if "api.groq.com" in c]) == 1
        assert len([c for c in calls if "openrouter.ai" in c]) == 1
        assert res.provider_name == "OpenRouterQwenProvider"
        assert res.used_fallback is True


@pytest.mark.asyncio
async def test_groq_unavailable_immediate_failover():
    """
    GROQ_API_KEY is not configured or invalid -> fails over directly to OpenRouter without calling Groq.
    """
    fallback = OpenRouterQwenProvider(api_key="sk-or-v1-dummy-fallback-key")
    provider = GroqQwenProvider(api_key="invalid_missing_key", fallback_provider=fallback)
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    faces = [("Face 1", img, _dummy_transform(100, 100))]

    mock_openrouter_200 = MagicMock()
    mock_openrouter_200.status_code = 200
    mock_openrouter_200.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "product_name": {"value": "Direct OpenRouter", "face": "Face 1"},
                        "declarations": [],
                    })
                }
            }
        ],
        "usage": {"prompt_tokens": 900, "completion_tokens": 30},
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_openrouter_200
        res = await provider.perceive(faces)

        assert mock_post.call_count == 1
        call_url = mock_post.call_args[0][0]
        assert "openrouter.ai" in call_url
        assert res.provider_name == "OpenRouterQwenProvider"
        assert res.used_fallback is True


@pytest.mark.asyncio
async def test_both_groq_and_openrouter_fail_classical_ocr_fallback():
    """
    If both Groq and OpenRouter fail, falls back to classical OCR (no infinite loop).
    """
    fallback = OpenRouterQwenProvider(api_key="sk-or-v1-dummy-fallback-key")
    provider = GroqQwenProvider(api_key="gsk_dummy_test_key_123456789", fallback_provider=fallback)
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    faces = [("Face 1", img, _dummy_transform(100, 100))]

    mock_err = MagicMock()
    mock_err.status_code = 500
    mock_err.text = "Server Error"

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch.object(fallback, "_fallback_classical", new_callable=AsyncMock) as mock_fb:
        mock_post.return_value = mock_err
        mock_fb.return_value = PerceptionResult(declarations=[], used_fallback=True, provider_name="ClassicalOcrFallback")

        res = await provider.perceive(faces)

        assert mock_fb.call_count == 1
        assert res.provider_name == "ClassicalOcrFallback"
        assert res.used_fallback is True


@pytest.mark.asyncio
async def test_single_preprocessing_invariant_same_payload():
    """
    Verify single preprocessing invariant:
    Images and messages are prepared ONCE into PreparedPerceptionBatch.
    Both Groq and OpenRouter receive the exact same prepared messages.
    """
    img1 = np.zeros((300, 200, 3), dtype=np.uint8)
    img2 = np.zeros((400, 300, 3), dtype=np.uint8)
    faces = [
        ("Face 1", img1, _dummy_transform(200, 300)),
        ("Face 2", img2, _dummy_transform(300, 400)),
    ]

    batch = prepare_perception_batch(faces)
    assert len(batch.face_summaries) == 2
    assert "Face 1" in batch.face_dims
    assert "Face 2" in batch.face_dims

    groq_payload = batch.make_payload("qwen/qwen3.8-27b")
    openrouter_payload = batch.make_payload("qwen/qwen3.8-27b")

    # Multimodal user messages content must be identical
    assert groq_payload["messages"][1]["content"] == openrouter_payload["messages"][1]["content"]
    assert groq_payload["messages"][0]["content"] == openrouter_payload["messages"][0]["content"]


@pytest.mark.asyncio
async def test_perception_audit_logging_fields():
    """
    Verify that all 11 required audit logging fields are present in the log entries:
    provider, request_id, model, face_count, http_status, latency, failure_type,
    retry_count, fallback_provider, prompt_tokens, completion_tokens.
    """
    recent_logs = get_groq_recent_logs(limit=20)
    assert len(recent_logs) > 0

    required_keys = {
        "provider",
        "request_id",
        "model",
        "face_count",
        "http_status",
        "latency",
        "failure_type",
        "retry_count",
        "fallback_provider",
        "prompt_tokens",
        "completion_tokens",
    }

    latest = recent_logs[0]
    for key in required_keys:
        assert key in latest, f"Missing required logging field: {key} in {latest}"


@pytest.mark.asyncio
async def test_finalize_session_coordinate_transform():
    import tempfile
    import cv2
    from auth import CurrentUser

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = f.name

    test_img = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.imwrite(tmp_path, test_img)

    fake_session = {
        "session_id": "test_session_coords",
        "status": "OPEN",
        "product_id": "P123",
        "product_category": "food",
        "sale_type": "retail",
        "mrp": 100.0,
        "net_quantity_value": 50.0,
        "net_quantity_unit": "g",
        "pdp_area_cm2": 45.0,
        "is_export_only": False,
    }

    fake_capture = {
        "image_id": "cap1",
        "image_path": tmp_path,
        "surface_observation": {
            "canonical_image_path": tmp_path,
            "inverse_transform_matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            "pdp_bbox_px": [10, 10, 50, 50],
            "dimensions": {"width": 100, "height": 100},
        },
        "ocr_fields": {
            "mrp": {"value": "100.0", "numeric_value": 100.0, "face": "Face 1"},
            "net_quantity": {"value": "50g", "numeric_value": 50.0, "numeric_unit": "g", "face": "Face 1"},
        },
    }

    user = CurrentUser(user_id=1, username="inspector1", role="inspector")

    with patch("db.persistence.get_session", return_value=fake_session), \
         patch("db.persistence.list_session_captures", return_value=[fake_capture]), \
         patch("db.persistence.save_inspection"), \
         patch("db.persistence.set_inspection_attribution"), \
         patch("db.persistence.finalize_session"), \
         patch("db.persistence.record_audit_event"):
        import main
        result = await main.finalize_session(
            session_id="test_session_coords",
            current_user=user,
        )
        assert result is not None
        assert "P123" in result.inspection_id
        assert len(result.surfaces) >= 1
        assert result.surfaces[0].surface_type == "Face 1"
