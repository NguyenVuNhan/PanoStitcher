# PanoStitcher

One-click CLI tool that recursively discovers DJI drone panorama folders, stitches them into 360° equirectangular images using Hugin with GPU acceleration, and injects the metadata needed for Immich / Google Photos / Facebook 360 viewers.

## Features

- **Recursive discovery** – walks any directory tree, detects DJI panorama sub-folders (`DJI_*.JPG`)
- **Idempotent** – skips folders already stitched (marker file + output check)
- **GPU-accelerated** – forces `nona -g` (OpenCL); auto-falls back to CPU
- **Geometric priors** – reads DJI EXIF gimbal angles (or uses built-in 26/34-image presets) to prevent horizon flipping
- **Wrap-aware blending** – `enblend --wrap=horizontal` eliminates the 0°/360° seam
- **Metadata preservation** – clones GPS, altitude, timestamp from source images via ExifTool
- **360 viewer injection** – writes XMP-GPano tags (`ProjectionType=equirectangular`) so the immersive viewer activates
- **Post-stitch validation** – checks 2:1 aspect ratio, GPS, date, and projection type
- **CI/CD** – GitHub Actions builds standalone binaries for Linux & Windows via PyInstaller

## Prerequisites

| Tool | Package | Purpose |
|------|---------|---------|
| Hugin CLI | `hugin-tools` | `pto_gen`, `cpfind`, `cpclean`, `autooptimiser`, `pano_modify`, `nona` |
| Enblend | `enblend-enfuse` | Seamless multi-band blending |
| ExifTool | `libimage-exiftool-perl` | Metadata read/write |
| ImageMagick | `imagemagick` | TIFF → JPEG conversion |

```bash
# Ubuntu / WSL2
sudo apt install hugin-tools enblend-enfuse libimage-exiftool-perl imagemagick

# Windows – install Hugin, ExifTool, ImageMagick and add to PATH
```

## Install

```bash
pip install -e .           # editable install
pip install -e ".[dev]"    # + pytest
```

## Usage

```bash
# Check all dependencies are reachable
panostitcher check

# Scan & stitch everything under a directory
panostitcher scan /path/to/photos --quality 95

# Stitch a single folder
panostitcher stitch /path/to/PANORAMA/100_0240

# Validate a finished panorama
panostitcher validate output_panorama.jpg

# Dry-run (list folders without stitching)
panostitcher scan /path/to/photos --dry-run

# Disable GPU
panostitcher scan /path/to/photos --no-gpu
```

## Pipeline

```
pto_gen → apply geometric priors → cpfind → cpclean → autooptimiser
→ pano_modify (equirectangular 360×180) → nona -g (GPU remap)
→ enblend --wrap=horizontal → ImageMagick (TIFF→JPEG)
→ ExifTool (clone GPS/date + inject GPano XMP)
```

## Testing

```bash
# Unit tests (no external tools needed)
pytest -m "not e2e"

# End-to-end test (requires Hugin + ExifTool + ImageMagick + sample assets)
pytest -m e2e
```

## Building Standalone Binary

```bash
pip install pyinstaller
pyinstaller panostitcher.spec
# Binary: dist/panostitcher[.exe]
```

## CI/CD

Push a tag (`v1.0.0`) to trigger the GitHub Actions pipeline which:
1. Runs unit tests on Ubuntu + Windows (Python 3.10, 3.12)
2. Builds standalone binaries via PyInstaller
3. Creates a GitHub Release with the binaries attached

## Project Structure

```
src/panostitcher/
├── __init__.py          # version
├── __main__.py          # python -m entry
├── cli.py               # argparse CLI (scan, stitch, check, validate)
├── config.py            # constants, DJI sphere geometry presets
├── dependencies.py      # tool health-check
├── discovery.py         # recursive folder scanning + idempotency
├── metadata.py          # ExifTool wrapper (GPS, timestamps, GPano XMP)
├── stitcher.py          # full Hugin pipeline + PTO manipulation
└── validator.py         # post-stitch quality checks
tests/
├── conftest.py          # shared fixtures (fake folder trees)
├── test_dependencies.py
├── test_discovery.py
├── test_metadata.py
├── test_stitcher.py
└── test_e2e.py          # real-image integration test
```

## License

MIT
