"""Keep local native updates on the operator's selected certificate."""
import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    "candidate_build", Path(__file__).resolve().parents[1] / "scripts/build_patched_driver.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_resume_preserves_selected_certificate():
    assert builder.signing_identity(None, {"signing_identity": "local-certificate"}) == "local-certificate"


def test_new_or_legacy_build_retains_adhoc_default():
    assert builder.signing_identity(None) == "-"
    assert builder.signing_identity(None, {"compiled": True}) == "-"


def test_explicit_operator_selection_overrides_previous_identity():
    assert builder.signing_identity("new-certificate", {"signing_identity": "old-certificate"}) == "new-certificate"
    assert builder.signing_identity("-", {"signing_identity": "old-certificate"}) == "-"


@pytest.mark.parametrize("invalid", ["", " ", None, 123])
def test_invalid_saved_identity_does_not_silently_fall_back(invalid):
    with pytest.raises(ValueError):
        builder.signing_identity(None, {"signing_identity": invalid})
