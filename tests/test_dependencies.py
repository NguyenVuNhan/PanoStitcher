"""Unit tests for the dependency health checker."""

from __future__ import annotations

from unittest.mock import patch

from panostitcher.dependencies import check_dependencies, require_dependencies
import pytest


class TestCheckDependencies:
    @patch("panostitcher.dependencies.shutil.which")
    def test_all_found(self, mock_which):
        mock_which.return_value = "/usr/bin/tool"
        report = check_dependencies()
        assert report.ok
        assert len(report.missing) == 0
        assert report.imagemagick_cmd is not None

    @patch("panostitcher.dependencies.shutil.which")
    def test_nothing_found(self, mock_which):
        mock_which.return_value = None
        report = check_dependencies()
        assert not report.ok
        assert len(report.missing) > 0

    @patch("panostitcher.dependencies.shutil.which")
    def test_imagemagick_v7_preferred(self, mock_which):
        def which_side(name):
            if name == "magick":
                return "/usr/bin/magick"
            if name in ("pto_gen", "cpfind", "autooptimiser", "pano_modify",
                        "nona", "enblend", "exiftool"):
                return f"/usr/bin/{name}"
            return None

        mock_which.side_effect = which_side
        report = check_dependencies()
        assert report.imagemagick_cmd == "magick"

    @patch("panostitcher.dependencies.shutil.which")
    def test_imagemagick_v6_fallback(self, mock_which):
        def which_side(name):
            if name == "magick":
                return None
            if name == "convert":
                return "/usr/bin/convert"
            if name in ("pto_gen", "cpfind", "autooptimiser", "pano_modify",
                        "nona", "enblend", "exiftool"):
                return f"/usr/bin/{name}"
            return None

        mock_which.side_effect = which_side
        report = check_dependencies()
        assert report.imagemagick_cmd == "convert"


class TestRequireDependencies:
    @patch("panostitcher.dependencies.shutil.which", return_value=None)
    def test_raises_on_missing(self, _):
        with pytest.raises(EnvironmentError, match="Missing required tools"):
            require_dependencies()

    @patch("panostitcher.dependencies.shutil.which", return_value="/usr/bin/tool")
    def test_passes_when_all_present(self, _):
        report = require_dependencies()
        assert report.ok
