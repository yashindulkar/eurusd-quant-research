from __future__ import annotations

import logging

import pytest

from eurusd_research.logging_utils import configure_logging


def test_configure_logging_is_idempotent_and_uses_utc(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(logging.WARNING)
    configure_logging(logging.INFO)

    root = logging.getLogger()
    assert root.level == logging.INFO
    assert len(root.handlers) == 1

    logging.getLogger("test.utc").info("lineage ready")
    captured = capsys.readouterr()
    assert "Z INFO test.utc lineage ready" in captured.err
