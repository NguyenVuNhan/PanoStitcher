"""ExifTool wrapper – metadata cloning and XMP GPano injection."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .config import logger


class ExifToolError(Exception):
    pass


def _run_exiftool(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = ["exiftool"] + args
    logger.debug("exiftool: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise ExifToolError(f"exiftool failed (rc={result.returncode}): {result.stderr.strip()}")
    return result


# ------------------------------------------------------------------
# Read helpers
# ------------------------------------------------------------------

def read_gimbal_angles(images: list[Path]) -> list[dict] | None:
    """Read DJI gimbal yaw/pitch/roll from EXIF.

    Returns a list of dicts with keys ``yaw``, ``pitch``, ``roll``
    (floats, degrees) in the same order as *images*, or ``None`` if the
    tags are not present on the first image.
    """
    try:
        result = _run_exiftool(
            ["-json", "-n",
             "-GimbalYawDegree", "-GimbalPitchDegree", "-GimbalRollDegree"]
            + [str(p) for p in images],
        )
    except ExifToolError:
        return None

    data = json.loads(result.stdout)
    # Validate first entry has the tags we need
    first = data[0] if data else {}
    if "GimbalYawDegree" not in first:
        return None

    angles: list[dict] = []
    for entry in data:
        angles.append({
            "yaw": float(entry.get("GimbalYawDegree", 0)),
            "pitch": float(entry.get("GimbalPitchDegree", 0)),
            "roll": float(entry.get("GimbalRollDegree", 0)),
        })
    return angles


def read_image_dimensions(image: Path) -> tuple[int, int]:
    """Return (width, height) of *image* via exiftool."""
    result = _run_exiftool(["-json", "-ImageWidth", "-ImageHeight", str(image)])
    data = json.loads(result.stdout)
    return int(data[0]["ImageWidth"]), int(data[0]["ImageHeight"])


def read_gps(image: Path) -> dict | None:
    """Read GPS coordinates and altitude from *image*.

    Returns dict with ``lat``, ``lon``, ``alt`` or None.
    """
    result = _run_exiftool(
        ["-json", "-n", "-GPSLatitude", "-GPSLongitude", "-GPSAltitude", str(image)],
        check=False,
    )
    if result.returncode != 0:
        return None
    data = json.loads(result.stdout)[0]
    if "GPSLatitude" not in data:
        return None
    return {
        "lat": float(data["GPSLatitude"]),
        "lon": float(data["GPSLongitude"]),
        "alt": float(data.get("GPSAltitude", 0)),
    }


def read_date_taken(image: Path) -> str | None:
    """Read DateTimeOriginal from *image*."""
    result = _run_exiftool(
        ["-json", "-DateTimeOriginal", str(image)], check=False,
    )
    if result.returncode != 0:
        return None
    data = json.loads(result.stdout)[0]
    return data.get("DateTimeOriginal")


# ------------------------------------------------------------------
# Write helpers
# ------------------------------------------------------------------

def clone_metadata(source: Path, destination: Path) -> None:
    """Copy all relevant metadata from *source* to *destination*.

    Transfers GPS, timestamps, camera info, and DJI-specific tags.
    Uses two passes:
      1. Copy all tags from source (except orientation/dimensions which
         belong to the stitched output).
      2. ExifTool resolves conflicts by keeping destination-native values
         for image geometry tags.
    """
    _run_exiftool([
        "-overwrite_original",
        "-TagsFromFile", str(source),
        "-All:All",
        "--IFD1:All",           # don't copy thumbnail
        "-ImageWidth=",         # keep destination dimensions
        "-ImageHeight=",
        "-XResolution=",
        "-YResolution=",
        "-Orientation=",
        str(destination),
    ])
    logger.info("Cloned metadata from %s", source.name)


def read_metadata_for_comparison(image: Path) -> dict:
    """Read key metadata fields for comparison between source and output.

    Returns a dict with GPS, timestamp, and camera info.
    """
    result = _run_exiftool(
        ["-json", "-n",
         "-GPSLatitude", "-GPSLongitude", "-GPSAltitude",
         "-DateTimeOriginal", "-CreateDate",
         "-Make", "-Model",
         str(image)],
        check=False,
    )
    if result.returncode != 0:
        return {}
    data = json.loads(result.stdout)
    return data[0] if data else {}


def inject_gpano(image: Path) -> None:
    """Write XMP-GPano tags so 360 viewers activate the immersive mode."""
    width, height = read_image_dimensions(image)
    from . import __version__
    _run_exiftool([
        "-overwrite_original",
        "-XMP-GPano:ProjectionType=equirectangular",
        "-XMP-GPano:UsePanoramaViewer=True",
        f"-XMP-GPano:CroppedAreaImageWidthPixels={width}",
        f"-XMP-GPano:CroppedAreaImageHeightPixels={height}",
        f"-XMP-GPano:FullPanoWidthPixels={width}",
        f"-XMP-GPano:FullPanoHeightPixels={height}",
        "-XMP-GPano:CroppedAreaLeftPixels=0",
        "-XMP-GPano:CroppedAreaTopPixels=0",
        f'-XMP-GPano:StitchingSoftware=PanoStitcher v{__version__}',
        str(image),
    ])
    logger.info("Injected GPano XMP tags (%dx%d)", width, height)
