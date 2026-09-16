from lexmetra_rules.ocr_normalize import normalize_ocr_text

def test_manufac_tured():
    assert normalize_ocr_text("manufac tured") == "manufactured"

def test_sh_all():
    assert normalize_ocr_text("sh all") == "shall"

def test_th_e():
    assert normalize_ocr_text("th e") == "the"

def test_commod_ity():
    assert normalize_ocr_text("commod ity") == "commodity"

def test_s_can():
    assert normalize_ocr_text("s can") == "scan"

def test_ordinal_15th():
    assert normalize_ocr_text("15 th") == "15th"

def test_ordinal_1st():
    assert normalize_ocr_text("1 st") == "1st"

def test_sentence_with_embedded_artifact():
    inp = "Every package shall be manufac tured and labelled."
    out = normalize_ocr_text(inp)
    assert "manufactured" in out
    assert "shall" in out

def test_sentence_commod_ity_embedded():
    inp = "The commod ity shall bear the name of the manufacturer."
    out = normalize_ocr_text(inp)
    assert "commodity" in out
    assert "manufacturer" in out

def test_preserves_standalone_a():
    assert normalize_ocr_text("a package") == "a package"

def test_preserves_of():
    assert normalize_ocr_text("name of the manufacturer") == "name of the manufacturer"

def test_preserves_in():
    assert normalize_ocr_text("packed in India") == "packed in India"

def test_preserves_or():
    assert normalize_ocr_text("one or two") == "one or two"

def test_preserves_the():
    assert normalize_ocr_text("the package") == "the package"

def test_preserves_and():
    assert normalize_ocr_text("salt and pepper") == "salt and pepper"

def test_preserves_for():
    assert normalize_ocr_text("used for human consumption") == "used for human consumption"

def test_preserves_not():
    assert normalize_ocr_text("shall not apply") == "shall not apply"

def test_preserves_may():
    assert normalize_ocr_text("the rule may be amended") == "the rule may be amended"

def test_preserves_per():
    assert normalize_ocr_text("50 grams per package") == "50 grams per package"

def test_clean_sentence_unchanged():
    s = "Every package shall bear the name of the manufacturer."
    assert normalize_ocr_text(s) == s

def test_empty_string():
    assert normalize_ocr_text("") == ""

def test_multi_fragment_chain():
    result = normalize_ocr_text("man uf act ured")
    assert result.count(' ') < 3
