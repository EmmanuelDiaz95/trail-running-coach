from __future__ import annotations

import pytest

from scripts.import_activities_csv import main


def test_main_refuses_default_profile(capsys):
    rc = main(["some.csv", "--profile", "default"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "default" in err
