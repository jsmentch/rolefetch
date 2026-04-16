from __future__ import annotations

import pytest

from rolefetch import __version__
from rolefetch.cli import _default_amazon_out_path, _default_google_out_path, main


def test_default_amazon_path_includes_loc_and_query() -> None:
    p = _default_amazon_out_path(
        loc_query="United States",
        base_query="scientist",
        fmt="jsonl",
    )
    assert "United_States__scientist" in str(p)
    assert p.name.endswith("_all.jsonl")


def test_default_google_path_includes_location_and_query() -> None:
    p = _default_google_out_path(
        location="United States",
        query="engineer",
        fmt="jsonl",
    )
    assert "United_States__engineer" in str(p)


def test_version_prints_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert __version__ in out
