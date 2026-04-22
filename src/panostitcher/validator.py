"""Post-stitch validation for equirectangular panoramas."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .config import logger
from .metadata import read_date_taken, read_gps, read_image_dimensions


@dataclass
class ValidationReport:
    checks: dict[str, bool] = field(default_factory=dict)
    details: dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(self.checks.values())

    def summary(self) -> str:
        lines = []
        for name, ok in self.checks.items():
            icon = "PASS" if ok else "FAIL"
            detail = self.details.get(name, "")
            lines.append(f"  [{icon}] {name}  {detail}")
        return "\n".join(lines)


def validate_panorama(image: Path) -> ValidationReport:
    """Run all validation checks on a stitched panorama.

    Checks
    ------
    1. File exists and is non-empty
    2. 2:1 aspect ratio (equirectangular standard)
    3. GPS coordinates present
    4. Date-taken timestamp present
    5. XMP GPano ProjectionType == equirectangular
    """
    report = ValidationReport()

    # 1. File existence
    exists = image.is_file() and image.stat().st_size > 0
    report.checks["file_exists"] = exists
    if not exists:
        report.details["file_exists"] = str(image)
        return report  # no point continuing

    # 2. Aspect ratio (equirectangular = 2:1, post-render padded)
    try:
        w, h = read_image_dimensions(image)
        ratio = w / h if h else 0
        is_2to1 = abs(ratio - 2.0) < 0.02
        report.checks["aspect_ratio_2to1"] = is_2to1
        report.details["aspect_ratio_2to1"] = f"{w}x{h} (ratio={ratio:.4f})"
    except Exception as exc:
        report.checks["aspect_ratio_2to1"] = False
        report.details["aspect_ratio_2to1"] = str(exc)

    # 3. GPS
    try:
        gps = read_gps(image)
        has_gps = gps is not None and "lat" in gps
        report.checks["gps_present"] = has_gps
        if has_gps:
            report.details["gps_present"] = f"({gps['lat']:.6f}, {gps['lon']:.6f})"
        else:
            report.details["gps_present"] = "no GPS tags found"
    except Exception as exc:
        report.checks["gps_present"] = False
        report.details["gps_present"] = str(exc)

    # 4. Timestamp
    try:
        dt = read_date_taken(image)
        report.checks["date_taken"] = dt is not None
        report.details["date_taken"] = dt or "no DateTimeOriginal"
    except Exception as exc:
        report.checks["date_taken"] = False
        report.details["date_taken"] = str(exc)

    # 5. ProjectionType
    try:
        result = subprocess.run(
            ["exiftool", "-json", "-XMP-GPano:ProjectionType", str(image)],
            capture_output=True, text=True,
        )
        data = json.loads(result.stdout)
        proj = data[0].get("ProjectionType", "")
        is_equirect = proj.lower() == "equirectangular"
        report.checks["projection_type"] = is_equirect
        report.details["projection_type"] = proj or "(not set)"
    except Exception as exc:
        report.checks["projection_type"] = False
        report.details["projection_type"] = str(exc)

    status = "ALL PASSED" if report.passed else "SOME FAILED"
    logger.info("Validation %s for %s", status, image.name)
    return report
