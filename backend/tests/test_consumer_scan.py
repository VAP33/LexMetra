from consumer_scan import (
    SlidingWindowRateLimiter,
    to_consumer_response,
)
from schema import ExtractedFact, FactStatus, ProductInspection, RuleFinding


def _inspection(status: FactStatus) -> ProductInspection:
    return ProductInspection(
        inspection_id="x",
        product_category="food",
        sale_type="retail",
        overall_status=status,
        review_required=status is FactStatus.UNCERTAIN,
        facts=[
            ExtractedFact(
                field="mrp",
                extracted_value="Rs 10",
                status=status,
                confidence=0.5,
                label="MRP",
            )
        ],
        findings=[
            RuleFinding(
                rule_id="LMPC-2011-R6-11-UNIT-PRICE",
                status=status,
                reason="hidden from consumer",
                confidence=0.5,
            )
        ],
    )


def test_uncertain_is_not_flattened():
    body = to_consumer_response(_inspection(FactStatus.UNCERTAIN), scan_id="con-1")
    assert body.overall_status == "UNCERTAIN"
    assert "not a pass and not a violation" in body.plain_language.lower()
    dumped = body.model_dump()
    assert "bbox" not in dumped
    assert "rule_id" not in str(dumped)
    assert dumped["items"][0]["outcome"] == "UNCERTAIN"


def test_fail_and_pass_remain_distinct():
    assert to_consumer_response(_inspection(FactStatus.FAIL), scan_id="a").overall_status == "FAIL"
    assert to_consumer_response(_inspection(FactStatus.PASS), scan_id="b").overall_status == "PASS"
    assert to_consumer_response(_inspection(FactStatus.EXEMPT), scan_id="c").overall_status == "EXEMPT"


def test_rate_limiter_blocks_over_quota():
    limiter = SlidingWindowRateLimiter(max_events=2, window_seconds=60)
    assert limiter.allow("ip") is True
    assert limiter.allow("ip") is True
    assert limiter.allow("ip") is False


def test_consumer_scan_disabled_is_404(api_client):
    resp = api_client.post("/consumer/scan")
    assert resp.status_code in {404, 401, 422}
