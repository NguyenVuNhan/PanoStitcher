"""Recursive discovery of DJI panorama folders."""

from __future__ import annotations

from pathlib import Path

from .config import DJI_IMAGE_GLOB, MIN_IMAGES_FOR_SPHERE, OUTPUT_SUFFIX, STITCH_MARKER, logger


def is_panorama_folder(folder: Path) -> bool:
    """Return True when *folder* contains enough DJI JPEGs for a sphere pano."""
    if not folder.is_dir():
        return False
    count = sum(1 for _ in folder.glob(DJI_IMAGE_GLOB))
    return count >= MIN_IMAGES_FOR_SPHERE


def _output_path_for(folder: Path, output_dir: Path | None) -> Path:
    """Derive the expected output JPEG path for a panorama folder."""
    name = folder.name + OUTPUT_SUFFIX
    if output_dir:
        return output_dir / name
    return folder.parent / name


def is_already_stitched(folder: Path, output_dir: Path | None = None) -> bool:
    """Check idempotency: skip if output or marker already exists."""
    marker = folder / STITCH_MARKER
    if marker.exists():
        return True
    out = _output_path_for(folder, output_dir)
    return out.exists()


def find_panorama_folders(
    root: Path,
    *,
    output_dir: Path | None = None,
    include_done: bool = False,
) -> list[Path]:
    """Walk *root* recursively and return DJI panorama folders.

    Parameters
    ----------
    root:
        Top-level directory to scan.
    output_dir:
        Optional separate output directory (used for idempotency check).
    include_done:
        When False (default), skip folders that already have output.

    Returns
    -------
    Sorted list of folder paths containing panorama source images.
    """
    if not root.is_dir():
        raise FileNotFoundError(f"Root directory does not exist: {root}")

    folders: list[Path] = []
    for candidate in sorted(root.rglob("*")):
        if not candidate.is_dir():
            continue
        if not is_panorama_folder(candidate):
            continue
        if not include_done and is_already_stitched(candidate, output_dir):
            logger.info("Skipping (already stitched): %s", candidate)
            continue
        folders.append(candidate)
        logger.info("Discovered panorama folder: %s", candidate)

    return folders


def list_images(folder: Path) -> list[Path]:
    """Return sorted list of DJI JPEGs in *folder*."""
    return sorted(folder.glob(DJI_IMAGE_GLOB))
