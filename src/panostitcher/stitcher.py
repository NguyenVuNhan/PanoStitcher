"""Hugin-based stitching pipeline with GPU acceleration."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .config import GEOMETRY_PRESETS, OUTPUT_SUFFIX, STITCH_MARKER, logger
from .discovery import list_images
from .metadata import clone_metadata, inject_gpano, read_gimbal_angles


# ------------------------------------------------------------------
# Data types
# ------------------------------------------------------------------


class StitchError(Exception):
    pass


@dataclass
class StitchResult:
    success: bool
    output_path: Path | None = None
    error: str | None = None
    duration_s: float = 0.0


# ------------------------------------------------------------------
# Subprocess helper
# ------------------------------------------------------------------


def _run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    logger.debug("CMD: %s", " ".join(str(a) for a in args))
    result = subprocess.run(
        [str(a) for a in args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise StitchError(f"{args[0]} failed (rc={result.returncode}): {detail}")
    return result


# ------------------------------------------------------------------
# PTO file manipulation
# ------------------------------------------------------------------

_IMG_LINE_RE = re.compile(r"^i\s")
_PANO_LINE_RE = re.compile(r"^p\s")
_CANVAS_W_RE = re.compile(r"\bw(\d+)")
_PARAM_RE = {
    "y": re.compile(r"(?<!\w)y(-?[\d.]+)"),
    "p": re.compile(r"(?<!\w)p(-?[\d.]+)"),
    "r": re.compile(r"(?<!\w)r(-?[\d.]+)"),
}


def _set_position(line: str, yaw: float, pitch: float, roll: float) -> str:
    """Replace y/p/r values in a PTO image line."""
    line = _PARAM_RE["y"].sub(f"y{yaw}", line, count=1)
    line = _PARAM_RE["p"].sub(f"p{pitch}", line, count=1)
    line = _PARAM_RE["r"].sub(f"r{roll}", line, count=1)
    return line


def _apply_priors(pto: Path, positions: list[tuple[float, float, float]]) -> None:
    """Write geometric priors and optimisation variables into *pto*."""
    lines = pto.read_text().splitlines(keepends=True)

    new_lines: list[str] = []
    img_idx = 0
    for line in lines:
        if _IMG_LINE_RE.match(line) and img_idx < len(positions):
            yaw, pitch, roll = positions[img_idx]
            line = _set_position(line, yaw, pitch, roll)
            img_idx += 1
        new_lines.append(line)

    # Append optimisation variable lines (anchor image 0 – don't optimise it)
    new_lines.append("\n# Optimisation variables\n")
    for i in range(1, img_idx):
        new_lines.append(f"v y{i} p{i} r{i}\n")
    new_lines.append("v\n")  # blank v line signals end

    pto.write_text("".join(new_lines))
    logger.info("Applied geometric priors for %d images", img_idx)


def _resolve_positions(images: list[Path]) -> list[tuple[float, float, float]]:
    """Determine initial yaw/pitch/roll for each image.

    Tries DJI EXIF gimbal tags first; falls back to a geometry preset.
    """
    angles = read_gimbal_angles(images)
    if angles:
        logger.info("Using DJI EXIF gimbal data for initial positions")
        return [(a["yaw"], a["pitch"], a["roll"]) for a in angles]

    n = len(images)
    if n in GEOMETRY_PRESETS:
        logger.info("Using built-in geometry preset for %d images", n)
        return GEOMETRY_PRESETS[n]

    raise StitchError(
        f"No EXIF gimbal data and no geometry preset for {n} images. "
        "Cannot determine initial image positions."
    )


# ------------------------------------------------------------------
# ImageMagick helper
# ------------------------------------------------------------------


def _resolve_magick() -> str:
    """Return the ImageMagick command ('magick' v7 or 'convert' v6)."""
    if shutil.which("magick"):
        return "magick"
    if shutil.which("convert"):
        return "convert"
    raise StitchError("ImageMagick not found (tried 'magick' and 'convert')")


def _read_pto_canvas_width(pto: Path) -> int:
    """Read canvas width from the PTO panorama line."""
    for line in pto.read_text().splitlines():
        if _PANO_LINE_RE.match(line):
            m = _CANVAS_W_RE.search(line)
            if m:
                return int(m.group(1))
    raise StitchError("Cannot read canvas width from PTO")


def _read_tiff_page_offset(magick: str, tiff: Path) -> tuple[int, int, int, int]:
    """Read (width, height, x_offset, y_offset) from a TIFF's page geometry.

    enblend embeds page offsets in its output TIFF, indicating where the
    content sits within the original nona canvas.
    """
    identify_cmd = (
        [magick, "identify"] if magick == "magick" else ["identify"]
    )
    result = _run(identify_cmd + ["-format", "%w %h %X %Y", str(tiff)])
    parts = result.stdout.strip().split()
    w, h = int(parts[0]), int(parts[1])
    off_x = int(parts[2].lstrip("+")) if len(parts) > 2 else 0
    off_y = int(parts[3].lstrip("+")) if len(parts) > 3 else 0
    return w, h, off_x, off_y


# ------------------------------------------------------------------
# Main pipeline
# ------------------------------------------------------------------


def stitch_panorama(
    folder: Path,
    *,
    output_path: Path | None = None,
    output_dir: Path | None = None,
    gpu: bool = True,
    quality: int = 95,
) -> StitchResult:
    """Run the full stitching pipeline on a DJI panorama *folder*.

    Pipeline stages
    ---------------
    1. ``pto_gen``     – create project from images + lens EXIF
    2. Apply priors    – set yaw/pitch/roll from gimbal EXIF or preset
    3. ``cpfind``      – detect control points
    4. ``cpclean``     – discard outliers
    5. ``autooptimiser`` – refine positions (anchored)
    6. ``pano_modify`` – force equirectangular 360×180
    7. ``nona -g``     – GPU-accelerated remapping
    8. ``enblend -w``  – wrap-aware blending (kills the 0°/360° seam)
    9. ImageMagick     – TIFF → JPEG
    10. ExifTool       – clone metadata + inject GPano XMP
    """
    t0 = time.monotonic()

    images = list_images(folder)
    if not images:
        return StitchResult(success=False, error="No DJI JPEGs found")

    if output_path is None:
        dest_dir = output_dir or folder.parent
        output_path = dest_dir / (folder.name + OUTPUT_SUFFIX)

    magick = _resolve_magick()

    try:
        positions = _resolve_positions(images)
    except StitchError as exc:
        return StitchResult(success=False, error=str(exc))

    with tempfile.TemporaryDirectory(prefix="panostitcher_") as _tmp:
        tmp = Path(_tmp)
        pto = tmp / "project.pto"

        # 1. Generate base PTO (lens data from EXIF)
        _run(["pto_gen", "-o", str(pto), "-p", "0", "-f", "73.7"]
             + [str(p) for p in images])

        # 2. Apply geometric priors + optimisation variables
        _apply_priors(pto, positions)

        # 3. Control-point detection
        _run(["cpfind", "--multirow", "--celeste", "-o", str(pto), str(pto)])

        # 4. Clean control points
        _run(["cpclean", "-o", str(pto), str(pto)])

        # 5. Optimise positions from priors (do NOT auto-align from scratch)
        _run(["autooptimiser", "-n", "-o", str(pto), str(pto)])

        # 6. Force equirectangular 360×180 output
        _run([
            "pano_modify",
            "--projection=2", "--fov=360x180", "--canvas=AUTO",
            "-o", str(pto), str(pto),
        ])

        # 7. GPU-accelerated remap
        prefix = tmp / "remapped_"
        nona_cmd = ["nona", "-m", "TIFF_m"]
        if gpu:
            nona_cmd.append("-g")
        nona_cmd += ["-o", str(prefix), str(pto)]
        try:
            _run(nona_cmd)
        except StitchError:
            if gpu:
                logger.warning("GPU remap failed – retrying on CPU")
                nona_cmd.remove("-g")
                _run(nona_cmd)
            else:
                raise

        # 8. Blend with horizontal wrap (fixes 0°/360° seam)
        tiffs = sorted(tmp.glob("remapped_*.tif"))
        if not tiffs:
            return StitchResult(success=False, error="nona produced no TIFF outputs")
        blended = tmp / "blended.tif"
        _run(["enblend", "--wrap=horizontal", "-o", str(blended)]
             + [str(t) for t in tiffs])

        # 9. TIFF → JPEG with correct equirectangular framing
        #    enblend crops its output to the content bounding box and embeds
        #    TIFF page offsets indicating where the content sits within the
        #    full nona canvas (which is already 2:1 for 360×180).
        #    We composite the blended content onto a full-size black canvas
        #    at the correct offset so zenith/nadir map to the right places.
        canvas_w = _read_pto_canvas_width(pto)
        canvas_h = canvas_w // 2  # exact 2:1 for equirectangular 360×180
        blend_w, blend_h, off_x, off_y = _read_tiff_page_offset(magick, blended)
        logger.info(
            "Compositing %dx%d+%d+%d onto %dx%d canvas",
            blend_w, blend_h, off_x, off_y, canvas_w, canvas_h,
        )

        magick_cmd = [magick] if magick == "magick" else ["convert"]
        if blend_w == canvas_w and blend_h == canvas_h:
            # Already full canvas, just convert
            _run(magick_cmd + [
                str(blended), "-quality", str(quality), str(output_path),
            ])
        else:
            # Composite onto full equirectangular canvas at correct offset
            _run(magick_cmd + [
                "-size", f"{canvas_w}x{canvas_h}", "xc:black",
                str(blended), "-geometry", f"+{off_x}+{off_y}",
                "-composite",
                "-quality", str(quality),
                str(output_path),
            ])

    # 10a. Clone GPS + timestamp from first source image
    try:
        clone_metadata(images[0], output_path)
    except Exception as exc:
        logger.warning("Metadata clone failed (non-fatal): %s", exc)

    # 10b. Inject XMP GPano tags for 360° viewers
    try:
        inject_gpano(output_path)
    except Exception as exc:
        logger.warning("GPano injection failed (non-fatal): %s", exc)

    # Write idempotency marker
    (folder / STITCH_MARKER).touch()

    elapsed = time.monotonic() - t0
    logger.info("Stitched %s → %s in %.1fs", folder.name, output_path, elapsed)
    return StitchResult(success=True, output_path=output_path, duration_s=elapsed)
