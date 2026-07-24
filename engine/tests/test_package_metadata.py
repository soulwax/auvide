"""Installed-package metadata contract for the PyPI distribution."""
from __future__ import annotations

from importlib.metadata import metadata, version

import auvide


def test_distribution_metadata_matches_imported_package():
    dist = metadata("auvide")

    assert dist["Name"] == "auvide"
    assert dist["License-Expression"] == "MIT"
    assert version("auvide") == auvide.__version__
    assert dist["Requires-Python"] == ">=3.9"


def test_distribution_declares_project_links():
    project_urls = metadata("auvide").get_all("Project-URL") or []

    assert any(url.startswith("Documentation,") for url in project_urls)
    assert any(url.startswith("Issues,") for url in project_urls)
