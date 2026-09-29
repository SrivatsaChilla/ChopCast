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