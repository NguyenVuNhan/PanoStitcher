"""Command-line interface for PanoStitcher."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .config import logger, setup_vendor_path


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="panostitcher",
        description="Automate DJI drone panorama stitching with GPU acceleration.",
    )
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("-v", "--verbose", action="store_true", help="enable debug logging")

    sub = p.add_subparsers(dest="command")

    # --- scan ---------------------------------------------------------------
    s = sub.add_parser("scan", help="recursively discover & stitch DJI panoramas")
    s.add_argument("root", type=Path, help="root directory to scan")
    s.add_argument("--output-dir", type=Path, default=None, help="write panoramas here instead of next to source")
    s.add_argument("--no-gpu", action="store_true", help="disable OpenCL GPU remapping")
    s.add_argument("--quality", type=int, default=95, help="JPEG quality 1-100 (default: 95)")
    s.add_argument("--dry-run", action="store_true", help="list folders without stitching")

    # --- stitch -------------------------------------------------------------
    s = sub.add_parser("stitch", help="stitch a single panorama folder")
    s.add_argument("folder", type=Path, help="folder containing DJI_*.JPG files")
    s.add_argument("--output", type=Path, default=None, help="output JPEG path")
    s.add_argument("--output-dir", type=Path, default=None, help="output directory")
    s.add_argument("--no-gpu", action="store_true", help="disable GPU")
    s.add_argument("--quality", type=int, default=95, help="JPEG quality (default: 95)")

    # --- check --------------------------------------------------------------
    sub.add_parser("check", help="verify required CLI tools are installed")

    # --- validate -----------------------------------------------------------
    s = sub.add_parser("validate", help="validate a stitched panorama file")
    s.add_argument("file", type=Path, help="panorama JPEG to validate")

    return p


def _cmd_check() -> int:
    from .dependencies import check_dependencies

    report = check_dependencies()
    print("Dependency health check")
    print("=" * 40)
    for t in report.found:
        print(f"  [OK]   {t}")
    for t in report.missing:
        print(f"  [MISS] {t}")
    print()
    if report.ok:
        print("All dependencies satisfied.")
        return 0
    print("Some dependencies are missing – see above.")
    return 1


def _cmd_scan(args: argparse.Namespace) -> int:
    from .dependencies import require_dependencies
    from .discovery import find_panorama_folders
    from .stitcher import stitch_panorama

    require_dependencies()

    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    folders = find_panorama_folders(args.root, output_dir=args.output_dir)
    if not folders:
        print("No unprocessed panorama folders found.")
        return 0

    print(f"Found {len(folders)} panorama folder(s):")
    for f in folders:
        print(f"  • {f}")
    if args.dry_run:
        return 0

    failures = 0
    for folder in folders:
        print(f"\nStitching {folder.name} …")
        result = stitch_panorama(
            folder,
            output_dir=args.output_dir,
            gpu=not args.no_gpu,
            quality=args.quality,
        )
        if result.success:
            print(f"  ✓ {result.output_path}  ({result.duration_s:.1f}s)")
        else:
            print(f"  ✗ {result.error}")
            failures += 1

    return 1 if failures else 0


def _cmd_stitch(args: argparse.Namespace) -> int:
    from .dependencies import require_dependencies
    from .stitcher import stitch_panorama

    require_dependencies()

    result = stitch_panorama(
        args.folder,
        output_path=args.output,
        output_dir=args.output_dir,
        gpu=not args.no_gpu,
        quality=args.quality,
    )
    if result.success:
        print(f"Done → {result.output_path}  ({result.duration_s:.1f}s)")
        return 0
    print(f"Error: {result.error}", file=sys.stderr)
    return 1


def _cmd_validate(args: argparse.Namespace) -> int:
    from .validator import validate_panorama

    report = validate_panorama(args.file)
    print(f"Validation report for {args.file.name}")
    print("=" * 50)
    print(report.summary())
    return 0 if report.passed else 1


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Add vendored tools (Hugin, enblend, etc.) to PATH if present
    setup_vendor_path()

    handlers = {
        "check": lambda: _cmd_check(),
        "scan": lambda: _cmd_scan(args),
        "stitch": lambda: _cmd_stitch(args),
        "validate": lambda: _cmd_validate(args),
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 2
    try:
        return handler()
    except EnvironmentError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nAborted.")
        return 130
