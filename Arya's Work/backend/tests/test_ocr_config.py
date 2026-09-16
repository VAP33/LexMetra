import os

from lexmetra_rules import config as config_module


def test_locate_tesseract_finds_real_binary_on_path():
    # In this environment tesseract is genuinely installed, so this
    # exercises the real PATH-lookup branch, not a mock.
    found = config_module.locate_tesseract()
    assert found is None or os.path.isfile(found)


def test_explicit_cmd_takes_priority(tmp_path):
    fake_binary = tmp_path / "my_tesseract"
    fake_binary.write_text("#!/bin/sh\necho fake")
    fake_binary.chmod(0o755)
    found = config_module.locate_tesseract(explicit_cmd=str(fake_binary))
    assert found == str(fake_binary)


def test_explicit_cmd_missing_file_returns_none():
    found = config_module.locate_tesseract(explicit_cmd="/definitely/not/a/real/path/tesseract")
    assert found is None


def test_env_var_used_when_no_explicit_cmd(tmp_path, monkeypatch):
    fake_binary = tmp_path / "env_tesseract"
    fake_binary.write_text("#!/bin/sh\necho fake")
    monkeypatch.setenv(config_module.TESSERACT_ENV_VAR, str(fake_binary))
    found = config_module.locate_tesseract()
    assert found == str(fake_binary)


def test_windows_fallback_path_never_hardcoded_as_primary(monkeypatch):
    """
    The brief explicitly says the Windows path must not be hard-coded as
    THE location. Verify PATH discovery (shutil.which) is tried before the
    Windows fallback candidate list.
    """
    monkeypatch.delenv(config_module.TESSERACT_ENV_VAR, raising=False)
    monkeypatch.setattr(config_module.shutil, "which", lambda name: "/usr/bin/tesseract")
    found = config_module.locate_tesseract()
    assert found == "/usr/bin/tesseract"


def test_resolve_ocr_config_never_raises_even_without_tesseract(monkeypatch):
    monkeypatch.setattr(config_module, "locate_tesseract", lambda explicit_cmd=None: None)
    result = config_module.resolve_ocr_config(lang="eng", dpi=200, psm=6)
    assert result.tesseract_cmd is None
    assert result.lang == "eng"


def test_resolve_ocr_config_carries_lang_dpi_psm():
    result = config_module.resolve_ocr_config(lang="eng+osd", dpi=400, psm=3)
    assert result.lang == "eng+osd"
    assert result.dpi == 400
    assert result.psm == 3
