"""Unit tests for the metadata / ExifTool wrapper (subprocess mocked)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from panostitcher.metadata import (
    clone_metadata,
    inject_gpano,
    read_date_taken,
    read_gimbal_angles,
    read_gps,
    read_image_dimensions,
    read_metadata_for_comparison,
)


def _exif_ok(stdout: str = "[]") -> MagicMock:
    return MagicMock(returncode=0, stdout=stdout, stderr="")


class TestReadGimbalAngles:
    @patch("panostitcher.metadata.subprocess.run")
    def test_parses_json(self, mock_run):
        data = [
            {"SourceFile": "a.jpg", "GimbalYawDegree": 90.0,
             "GimbalPitchDegree": -60.0, "GimbalRollDegree": 0.5},
            {"SourceFile": "b.jpg", "GimbalYawDegree": 135.0,
             "GimbalPitchDegree": -60.0, "GimbalRollDegree": 0.0},
        ]
        mock_run.return_value = _exif_ok(json.dumps(data))

        result = read_gimbal_angles([Path("a.jpg"), Path("b.jpg")])
        assert result is not None
        assert len(result) == 2
        assert result[0]["yaw"] == 90.0
        assert result[1]["pitch"] == -60.0

    @patch("panostitcher.metadata.subprocess.run")
    def test_returns_none_when_no_tags(self, mock_run):
        mock_run.return_value = _exif_ok(json.dumps([{"SourceFile": "a.jpg"}]))
        assert read_gimbal_angles([Path("a.jpg")]) is None


class TestReadImageDimensions:
    @patch("panostitcher.metadata.subprocess.run")
    def test_returns_tuple(self, mock_run):
        mock_run.return_value = _exif_ok(
            json.dumps([{"ImageWidth": 8000, "ImageHeight": 4000}])
        )
        w, h = read_image_dimensions(Path("pano.jpg"))
        assert (w, h) == (8000, 4000)


class TestReadGps:
    @patch("panostitcher.metadata.subprocess.run")
    def test_parses_coords(self, mock_run):
        mock_run.return_value = _exif_ok(
            json.dumps([{"GPSLatitude": 48.8566, "GPSLongitude": 2.3522, "GPSAltitude": 120}])
        )
        gps = read_gps(Path("img.jpg"))
        assert gps is not None
        assert abs(gps["lat"] - 48.8566) < 0.001

    @patch("panostitcher.metadata.subprocess.run")
    def test_returns_none_when_absent(self, mock_run):
        mock_run.return_value = _exif_ok(json.dumps([{"SourceFile": "x.jpg"}]))
        assert read_gps(Path("x.jpg")) is None


class TestReadDateTaken:
    @patch("panostitcher.metadata.subprocess.run")
    def test_returns_date(self, mock_run):
        mock_run.return_value = _exif_ok(
            json.dumps([{"DateTimeOriginal": "2024:06:15 14:30:00"}])
        )
        assert read_date_taken(Path("x.jpg")) == "2024:06:15 14:30:00"


class TestCloneMetadata:
    @patch("panostitcher.metadata.subprocess.run")
    def test_calls_exiftool(self, mock_run):
        mock_run.return_value = _exif_ok()
        clone_metadata(Path("src.jpg"), Path("dst.jpg"))
        args = mock_run.call_args[0][0]
        assert args[0] == "exiftool"
        assert "-overwrite_original" in args
        assert "-All:All" in args


class TestInjectGpano:
    @patch("panostitcher.metadata.read_image_dimensions", return_value=(8000, 4000))
    @patch("panostitcher.metadata.subprocess.run")
    def test_writes_projection_type(self, mock_run, _dim):
        mock_run.return_value = _exif_ok()
        inject_gpano(Path("pano.jpg"))
        args = mock_run.call_args[0][0]
        assert any("ProjectionType=equirectangular" in a for a in args)
        assert any("UsePanoramaViewer=True" in a for a in args)
        assert any("FullPanoWidthPixels=8000" in a for a in args)


class TestReadMetadataForComparison:
    @patch("panostitcher.metadata.subprocess.run")
    def test_returns_dict(self, mock_run):
        data = [{
            "SourceFile": "a.jpg",
            "GPSLatitude": 12.006,
            "GPSLongitude": 108.343,
            "GPSAltitude": 1418.21,
            "DateTimeOriginal": "2025:01:25 08:59:52",
            "CreateDate": "2025:01:25 08:59:52",
            "Make": "DJI",
            "Model": "FC7303",
        }]
        mock_run.return_value = _exif_ok(json.dumps(data))
        result = read_metadata_for_comparison(Path("a.jpg"))
        assert result["GPSLatitude"] == 12.006
        assert result["Make"] == "DJI"
        assert result["DateTimeOriginal"] == "2025:01:25 08:59:52"

    @patch("panostitcher.metadata.subprocess.run")
    def test_returns_empty_on_error(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        result = read_metadata_for_comparison(Path("missing.jpg"))
        assert result == {}
