"""End-to-end integration test using real DJI sample assets.

Requires Hugin, ExifTool, and ImageMagick to be installed.
Run with:  pytest -m e2e
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from panostitcher.dependencies import check_dependencies
from panostitcher.discovery import list_images
from panostitcher.metadata import read_metadata_for_comparison
from panostitcher.stitcher import stitch_panorama
from panostitcher.validator import validate_panorama

# Skip the entire module when tools are missing
_report = check_dependencies()
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not _report.ok, reason=f"Missing tools: {_report.missing}"),
]


@pytest.fixture()
def sample_pano() -> Path:
    """Resolve the real sample asset folder, skip if absent."""
    p = Path(__file__).resolve().parent.parent / "assets" / "PANORAMA" / "100_0240"
    if not p.is_dir():
        pytest.skip("Sample asset folder not present")
    return p


@pytest.fixture()
def e2e_output_dir(tmp_path: Path) -> Path:
    out = tmp_path / "e2e_output"
    out.mkdir()
    return out


class TestEndToEnd:
    def test_full_stitch_and_validate(self, sample_pano: Path, e2e_output_dir: Path):
        """Stitch the real 100_0240 assets and run all validation checks."""
        images = list_images(sample_pano)
        assert len(images) == 26, f"Expected 26 images, got {len(images)}"

        result = stitch_panorama(
            sample_pano,
            output_dir=e2e_output_dir,
            gpu=True,
            quality=95,
        )

        assert result.success, f"Stitch failed: {result.error}"
        assert result.output_path is not None
        assert result.output_path.is_file()
        assert result.output_path.stat().st_size > 100_000  # sanity: >100 KB

        # Validate
        report = validate_panorama(result.output_path)
        print("\n" + report.summary())

        assert report.checks["file_exists"]
        assert report.checks["aspect_ratio_2to1"], f"Bad ratio: {report.details.get('aspect_ratio_2to1')}"
        assert report.checks["projection_type"], "Missing GPano ProjectionType"

        # GPS + date are best-effort (depends on source images having tags)
        if report.checks.get("gps_present") is False:
            pytest.xfail("Source images may lack GPS data")

    def test_metadata_preserved(self, sample_pano: Path, e2e_output_dir: Path):
        """Verify that stitched output preserves key metadata from source."""
        images = list_images(sample_pano)
        result = stitch_panorama(
            sample_pano,
            output_dir=e2e_output_dir,
            gpu=True,
            quality=95,
        )
        assert result.success, f"Stitch failed: {result.error}"

        source_meta = read_metadata_for_comparison(images[0])
        output_meta = read_metadata_for_comparison(result.output_path)

        # GPS coordinates must match within small tolerance
        assert abs(source_meta["GPSLatitude"] - output_meta["GPSLatitude"]) < 1e-5, \
            f"GPS lat mismatch: {source_meta['GPSLatitude']} vs {output_meta['GPSLatitude']}"
        assert abs(source_meta["GPSLongitude"] - output_meta["GPSLongitude"]) < 1e-5, \
            f"GPS lon mismatch: {source_meta['GPSLongitude']} vs {output_meta['GPSLongitude']}"

        # Timestamps must match exactly
        assert source_meta["DateTimeOriginal"] == output_meta["DateTimeOriginal"], \
            f"DateTimeOriginal mismatch: {source_meta['DateTimeOriginal']} vs {output_meta.get('DateTimeOriginal')}"
        assert source_meta["CreateDate"] == output_meta["CreateDate"], \
            f"CreateDate mismatch: {source_meta['CreateDate']} vs {output_meta.get('CreateDate')}"

        # Camera make/model must match
        assert source_meta["Make"] == output_meta["Make"], \
            f"Make mismatch: {source_meta['Make']} vs {output_meta.get('Make')}"
        assert source_meta["Model"] == output_meta["Model"], \
            f"Model mismatch: {source_meta['Model']} vs {output_meta.get('Model')}"
