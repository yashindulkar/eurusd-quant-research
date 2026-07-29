from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from eurusd_research.studies import __main__ as task04_main


def test_task04_cli_receipt(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    result = SimpleNamespace(
        summary={
            "study": {"status": "COMPLETED"},
            "population": {"primary_eligible_dates": 10},
            "primary_result": {"kruskal_p_value": 0.012345},
            "evidence_rating": {"rating": "WEAK"},
        },
        output_directory=tmp_path,
    )
    monkeypatch.setattr(task04_main, "generate_task04_study", lambda *_: result)
    assert task04_main.main(["--root", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "Task 04: COMPLETED | dates=10" in output
    assert "evidence=WEAK" in output
