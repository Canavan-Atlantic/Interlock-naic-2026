"""Headless smoke test for the small Module 4B Streamlit preview addition."""

import pytest
from pathlib import Path

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest


def test_frontend_renders_validation_flow_without_backend() -> None:
    app_path = Path(__file__).resolve().parents[1] / "frontend" / "app.py"
    app = AppTest.from_file(app_path, default_timeout=10).run()

    assert not app.exception
    assert app.title[0].value == "INTERLOCK"
    assert any(button.label == "Validate Project Input" for button in app.button)
