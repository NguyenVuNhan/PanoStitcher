"""Shared fixtures for the PanoStitcher test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
SAMPLE_PANO = ASSETS_DIR / "PANORAMA" / "100_0240"


@pytest.fixture()
def sample_pano() -> Path:
    """Path to the real DJI sample panorama folder."""
    if not SAMPLE_PANO.is_dir():
        pytest.skip("Sample asset folder not present")
    return SAMPLE_PANO


@pytest.fixture()
def fake_pano_tree(tmp_path: Path) -> Path:
    """Create a disposable directory tree with fake DJI panorama folders."""
    # Good folder – 26 images
    good = tmp_path / "PANORAMA" / "100_0001"
    good.mkdir(parents=True)
    for i in range(1, 27):
        (good / f"DJI_{i:04d}.JPG").write_bytes(b"\xff\xd8fake")

    # Too-few images (should be ignored)
    bad = tmp_path / "PANORAMA" / "100_0002"
    bad.mkdir(parents=True)
    for i in range(1, 6):
        (bad / f"DJI_{i:04d}.JPG").write_bytes(b"\xff\xd8fake")

    # Already stitched
    done = tmp_path / "PANORAMA" / "100_0003"
    done.mkdir(parents=True)
    for i in range(1, 27):
        (done / f"DJI_{i:04d}.JPG").write_bytes(b"\xff\xd8fake")
    (done / ".panostitcher_done").touch()

    # Nested deep
    deep = tmp_path / "Photos" / "2024" / "PANORAMA" / "100_0004"
    deep.mkdir(parents=True)
    for i in range(1, 27):
        (deep / f"DJI_{i:04d}.JPG").write_bytes(b"\xff\xd8fake")

    return tmp_path
