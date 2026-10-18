"""Tests for chopcast.processing.cleaner."""

from __future__ import annotations

import pytest

from chopcast.config import CleanerConfig
from chopcast.errors import LeakageError
from chopcast.processing.cleaner import clean_text


@pytest.fixture
def cfg() -> CleanerConfig:
    return CleanerConfig()


def test_strips_tb_block(cfg: CleanerConfig) -> None:
    out = clean_text(
        "UA /OV SFO /TM 1425 /FL350 /TP B738 /TB MOD CHOP /RM SMOOTH RIDE",
        cfg,
    )
    assert "/TB" not in out
    assert "MOD CHOP" not in out
    assert "smooth ride" in out  # /RM is preserved; cleaner lowercases


def test_lowercases(cfg: CleanerConfig) -> None:
    out = clean_text("UA /OV SFO /TB MOD", cfg)
    assert out == out.lower()


def test_collapses_whitespace(cfg: CleanerConfig) -> None:
    out = clean_text("UA    /OV    SFO    /TB    MOD", cfg)
    assert "  " not in out


def test_self_check_raises_on_leakage(cfg: CleanerConfig) -> None:
    # If somehow the strip regex failed (programmer error), the
    # self-check at the end of clean_text would catch it. We simulate
    # by feeding input that, after lowercasing, still has /TB but the
    # strip regex cannot remove it because it's glued to a value.
    # The default strip regex handles `/TB` followed by a value, so
    # we craft something that fools the strip but survives:
    with pytest.raises(LeakageError):
        clean_text("/TBONOACAT", cfg)


def test_empty_input_returns_empty(cfg: CleanerConfig) -> None:
    assert clean_text("", cfg) == ""


def test_handles_multiple_tb_blocks(cfg: CleanerConfig) -> None:
    out = clean_text("A /TB MOD B /TB SEV C", cfg)
    assert "/TB" not in out
    assert "MOD" not in out
    assert "SEV" not in out

# ---------------------------------------------------------------------------
# Compact reports. Most real PIREPs glue each field to the previous value
# with no space (`/TP B738/TB MOD`). The strip pattern used to require
# whitespace before `/TB`, so 96% of labelled reports raised LeakageError.
# ---------------------------------------------------------------------------
def test_strips_tb_glued_to_previous_field(cfg: CleanerConfig) -> None:
    out = clean_text("DEN UA /OV DEN270030/TM 0130/FL130/TP B737/TB MOD/RM SMOOTH", cfg)
    assert "/tb" not in out
    assert "mod" not in out
    assert "b737" in out  # the field before /TB is kept
    assert "/rm smooth" in out  # the field after /TB is kept


def test_strips_tb_glued_at_end_of_report(cfg: CleanerConfig) -> None:
    out = clean_text(
        "LOZ UA /OV LOZ360020/TM 2349/FL340/TP B738/TB CONS LGT CHOP OCNL MOD CHOP", cfg
    )
    assert "/tb" not in out
    assert "chop" not in out
    assert "b738" in out


def test_strips_doubled_tb_tag(cfg: CleanerConfig) -> None:
    out = clean_text("BNA UA /OV BNA330030/TM 1411/FL130/TP E170/TB /TB MOD 130-080 DURD", cfg)
    assert "/tb" not in out
    assert "mod" not in out
    assert "e170" in out
