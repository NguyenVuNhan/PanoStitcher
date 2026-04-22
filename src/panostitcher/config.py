"""Default configuration and DJI sphere geometry presets."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("panostitcher")

# ---------------------------------------------------------------------------
# Vendored tool discovery
# ---------------------------------------------------------------------------
# When running from source: <project>/vendor/hugin/Hugin/bin
# When frozen (PyInstaller):  <exe_dir>/vendor/hugin/Hugin/bin

def _find_vendor_bin() -> Path | None:
    """Return the vendor bin directory if it exists."""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        # Walk up from src/panostitcher/config.py → project root
        base = Path(__file__).resolve().parent.parent.parent

    candidate = base / "vendor" / "hugin" / "Hugin" / "bin"
    if candidate.is_dir():
        return candidate
    return None


def setup_vendor_path() -> Path | None:
    """Prepend the vendored tool directory to PATH if it exists.

    Returns the vendor bin path or None.
    """
    vendor_bin = _find_vendor_bin()
    if vendor_bin is None:
        return None
    vendor_str = str(vendor_bin)
    if vendor_str not in os.environ.get("PATH", ""):
        os.environ["PATH"] = vendor_str + os.pathsep + os.environ.get("PATH", "")
        logger.info("Added vendored tools to PATH: %s", vendor_str)
    return vendor_bin

# ---------------------------------------------------------------------------
# Output defaults
# ---------------------------------------------------------------------------
DEFAULT_JPEG_QUALITY = 95
OUTPUT_SUFFIX = "_panorama.jpg"
STITCH_MARKER = ".panostitcher_done"

# ---------------------------------------------------------------------------
# DJI panorama detection
# ---------------------------------------------------------------------------
DJI_IMAGE_GLOB = "DJI_*.JPG"
MIN_IMAGES_FOR_SPHERE = 20  # reject folders with fewer images

# ---------------------------------------------------------------------------
# DJI 26-image sphere geometry fallback
# ---------------------------------------------------------------------------
# Used when EXIF gimbal tags are unavailable.
# Layout: 3 rings of 8 + nadir + zenith.
# Yaw values are compass-style (°); pitch: +up / -down.


def _ring(pitch: float, count: int = 8, yaw_offset: float = 0.0):
    return [(yaw_offset + i * (360.0 / count), pitch, 0.0) for i in range(count)]


DJI_SPHERE_26: list[tuple[float, float, float]] = [
    # Images 0-7:  upper ring
    *_ring(pitch=45.0, yaw_offset=0.0),
    # Images 8-15: middle ring (22.5° offset for overlap)
    *_ring(pitch=0.0, yaw_offset=22.5),
    # Images 16-23: lower ring
    *_ring(pitch=-45.0, yaw_offset=0.0),
    # Image 24: nadir
    (0.0, -90.0, 0.0),
    # Image 25: zenith
    (0.0, 90.0, 0.0),
]

DJI_SPHERE_34: list[tuple[float, float, float]] = [
    *_ring(pitch=60.0, yaw_offset=0.0),
    *_ring(pitch=20.0, yaw_offset=22.5),
    *_ring(pitch=-20.0, yaw_offset=0.0),
    *_ring(pitch=-60.0, yaw_offset=22.5),
    (0.0, -90.0, 0.0),
    (0.0, 90.0, 0.0),
]

GEOMETRY_PRESETS: dict[int, list[tuple[float, float, float]]] = {
    26: DJI_SPHERE_26,
    34: DJI_SPHERE_34,
}
