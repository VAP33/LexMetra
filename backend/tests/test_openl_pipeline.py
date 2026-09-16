from datetime import date

from openl.pipeline import (
    load_manifest,
    record_deploy,
    resolve_zip_for_date,
    sha256_file,
)
from openl.resolver import classify_exemption_resolved
from exemption import ExemptionInput, classify_exemption


def test_exemption_resolver_defaults_to_legacy():
    inp = ExemptionInput(
        sale_type="retail",
        product_category="food",
        net_quantity_value=100,
        net_quantity_unit="g",
    )
    legacy = classify_exemption(inp)
    resolved = classify_exemption_resolved(inp, force_openl=False)
    assert resolved.is_exempt == legacy.is_exempt
    assert resolved.exemption_type == legacy.exemption_type


def test_openl_type_mapping_without_http():
    from openl.openl_client import OpenLExemptionClient
    from exemption import ExemptionInput

    client = OpenLExemptionClient()
    inp = ExemptionInput(sale_type="retail", product_category="food", net_quantity_value=5, net_quantity_unit="g")
    none = client.map_type("none", inp)
    assert none.is_exempt is False
    small = client.map_type("rule_26_small_pack", inp)
    assert small.is_exempt is True
    assert small.rule_id == "LMPC-2011-R26-SMALL-PACKS"


def test_manifest_picks_dated_zip_not_future(tmp_path):
    zip_path = tmp_path / "rules.zip"
    zip_path.write_bytes(b"PK\x03\x04fake")
    manifest = tmp_path / "m.jsonl"
    record_deploy(
        rule_family="exemption",
        rule_ids=["LMPC-2011-R3-SCOPE"],
        zip_path=zip_path,
        effective_from="2011-04-01",
        manifest_path=manifest,
    )
    record_deploy(
        rule_family="exemption",
        rule_ids=["LMPC-2011-R3-SCOPE"],
        zip_path=zip_path,
        effective_from="2030-01-01",
        manifest_path=manifest,
    )
    chosen = resolve_zip_for_date(date(2020, 1, 1), rule_family="exemption", manifest_path=manifest)
    assert chosen is not None
    assert chosen["effective_from"] == "2011-04-01"
    missing = resolve_zip_for_date(date(2000, 1, 1), rule_family="exemption", manifest_path=manifest)
    assert missing is None
    assert sha256_file(zip_path)
    assert len(load_manifest(manifest)) == 2
