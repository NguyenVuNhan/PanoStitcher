"""Unit tests for post-stitch validation (exiftool mocked)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from panostitcher.validator import validate_panorama


def _mock_exiftool_json(data: dict) -> MagicMock:
    return MagicMock(returncode=0, stdout=json.dumps([data]), stderr="")


class TestValidatePanorama:
    def test_missing_file(self, tmp_path: Path):
        report = validate_panorama(tmp_path / "nope.jpg")
        assert not report.passed
        assert report.checks["file_exists"] is False

    @patch("panostitcher.validator.subprocess.run")
    @patch("panostitcher.validator.read_date_taken", return_value="2024:06:15 14:30:00")
    @patch("panostitcher.validator.read_gps", return_value={"lat": 48.0, "lon": 2.0, "alt": 100})
    @patch("panostitcher.validator.read_image_dimensions", return_value=(8192, 4096))
    def test_all_pass(self, _dim, _gps, _date, mock_run, tmp_path: Path):
        pano = tmp_path / "test_pano.jpg"
        pano.write_bytes(b"\xff\xd8fake jpeg content")

        mock_run.return_value = _mock_exiftool_json(
            {"ProjectionType": "equirectangular"}
        )

        report = validate_panorama(pano)
        assert report.passed
        assert report.checks["file_exists"] is True
        assert report.checks["aspect_ratio_2to1"] is True
        assert report.checks["gps_present"] is True
        assert report.checks["date_taken"] is True
        assert report.checks["projection_type"] is True

    @patch("panostitcher.validator.subprocess.run")
    @patch("panostitcher.validator.read_date_taken", return_value=None)
    @patch("panostitcher.validator.read_gps", return_value=None)
    @patch("panostitcher.validator.read_image_dimensions", return_value=(6000, 4000))
    def test_failures(self, _dim, _gps, _date, mock_run, tmp_path: Path):
        pano = tmp_path / "bad.jpg"
        pano.write_bytes(b"\xff\xd8bad")

        mock_run.return_value = _mock_exiftool_json({"SourceFile": "bad.jpg"})

        report = validate_panorama(pano)
        assert not report.passed
        assert report.checks["aspect_ratio_2to1"] is False  # 6000/4000 = 1.5
        assert report.checks["gps_present"] is False
        assert report.checks["date_taken"] is False
        assert report.checks["projection_type"] is False
