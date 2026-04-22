"""Dependency health-check for external CLI tools."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field

from .config import logger

# ---------------------------------------------------------------------------
# Required tools and their version-check commands
# ---------------------------------------------------------------------------
_TOOLS: list[tuple[str, list[str], str]] = [
    # (display_name, version_command, package_hint)
    ("pto_gen (Hugin)", ["pto_gen", "--help"], "hugin-tools"),
    ("cpfind (Hugin)", ["cpfind", "--help"], "hugin-tools"),
    ("autooptimiser (Hugin)", ["autooptimiser", "--help"], "hugin-tools"),
    ("pano_modify (Hugin)", ["pano_modify", "--help"], "hugin-tools"),
    ("nona (Hugin)", ["nona", "--help"], "hugin-tools"),
    ("enblend", ["enblend", "--version"], "enblend-enfuse"),
    ("exiftool", ["exiftool", "-ver"], "libimage-exiftool-perl"),
]

# ImageMagick can be either 'magick' (v7) or 'convert' (v6).
_IMAGEMAGICK_CANDIDATES = [
    ("magick (ImageMagick 7)", ["magick", "--version"], "imagemagick"),
    ("convert (ImageMagick 6)", ["convert", "--version"], "imagemagick"),
]


@dataclass
class HealthReport:
    found: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    imagemagick_cmd: str | None = None

    @property
    def ok(self) -> bool:
        return len(self.missing) == 0


def check_dependencies() -> HealthReport:
    """Verify all required CLI tools are reachable on PATH."""
    report = HealthReport()

    for display, cmd, hint in _TOOLS:
        if shutil.which(cmd[0]):
            report.found.append(display)
            logger.debug("Found %s", display)
        else:
            report.missing.append(f"{display}  (install: {hint})")
            logger.warning("Missing %s – install package '%s'", display, hint)

    # ImageMagick: accept either v7 or v6
    for display, cmd, hint in _IMAGEMAGICK_CANDIDATES:
        if shutil.which(cmd[0]):
            report.found.append(display)
            report.imagemagick_cmd = cmd[0]
            logger.debug("Found %s", display)
            break
    else:
        report.missing.append("ImageMagick (magick or convert)  (install: imagemagick)")

    return report


def require_dependencies() -> HealthReport:
    """Check dependencies and raise if any are missing."""
    report = check_dependencies()
    if not report.ok:
        missing_str = "\n  • ".join(report.missing)
        raise EnvironmentError(
            f"Missing required tools:\n  • {missing_str}\n"
            "Install the missing packages and ensure they are on PATH."
        )
    return report
