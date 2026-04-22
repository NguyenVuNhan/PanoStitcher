# PanoStitcher — Agent Rules & Knowledge Base

## Project Overview

One-click DJI drone panorama stitching CLI. Takes a folder of 26 DJI sphere images and produces a single equirectangular JPEG with full GPS/XMP metadata for 360° viewers.

## Architecture

```
src/panostitcher/
├── cli.py          # argparse CLI (scan, stitch, check, validate)
├── config.py       # constants, DJI geometry presets, vendor path setup
├── dependencies.py # health check for external tools
├── discovery.py    # DJI folder detection, idempotency markers
├── metadata.py     # ExifTool wrapper (read/write EXIF, inject GPano XMP)
├── stitcher.py     # 10-stage Hugin pipeline (core logic)
└── validator.py    # post-stitch validation (5 checks)
```

## External Dependencies

| Tool        | Purpose                          | Version  |
|-------------|----------------------------------|----------|
| Hugin       | PTO pipeline (pto_gen → enblend) | 2025.0.1 |
| ImageMagick | TIFF → JPEG conversion           | 7.x      |
| ExifTool    | Metadata read/write              | 12+      |

Hugin is stored portably at `vendor/hugin/Hugin/bin` and added to PATH at runtime via `setup_vendor_path()`.

## Key Design Decisions

1. **Offset-aware 2:1 compositing** — The pipeline does NOT manipulate the PTO canvas before rendering (that stretches the equirectangular projection). Instead: (a) nona renders at Hugin's natural AUTO canvas size, (b) enblend crops to the content bounding box but embeds TIFF page offsets, (c) ImageMagick composites the blended content onto a full 2:1 black canvas at the exact TIFF page offset. This preserves the correct equirectangular mapping — zenith/nadir align to the right pixel rows. **NEVER use `-gravity center -extent` for padding** — center-padding shifts content away from its correct projection position, creating a black hole at nadir in 360° viewers.

2. **Broad metadata cloning** — `clone_metadata()` uses `-All:All` from ExifTool to transfer all tags from the source image, excluding only image geometry tags (width, height, orientation, thumbnail) that belong to the stitched output.

3. **GPU with CPU fallback** — `nona -g` attempts GPU remap; on failure, retries without `-g`.

4. **Idempotency** — A `.panostitcher_done` marker file prevents re-stitching. Use `--force` to override.

## Stitching Pipeline (10 stages)

1. `pto_gen` — create PTO from images + lens EXIF
2. Apply priors — set yaw/pitch/roll from gimbal EXIF or DJI preset
3. `cpfind --multirow --celeste` — detect control points
4. `cpclean` — discard outliers
5. `autooptimiser -n` — refine positions (anchored)
6. `pano_modify --projection=2 --fov=360x180 --canvas=AUTO` — equirectangular output
7. `nona -g` — GPU-accelerated remapping (with CPU fallback)
8. `enblend --wrap=horizontal` — seam blending
9. `magick` — TIFF → JPEG at specified quality
10. `exiftool` — clone metadata + inject GPano XMP

## DJI Sphere 26 Preset

- 3 rings of 8 images (yaw 0°/45°/90°/... at pitch -60°/-30°/0°)
- 1 nadir (pitch -90°)
- 1 zenith (pitch +90°)

## Testing

- **Unit tests** (`tests/`): 38+ tests, all mocked (no external tool deps)
- **E2E test** (`tests/test_e2e.py`): Uses real assets in `assets/PANORAMA/100_0240/`, marked `@pytest.mark.e2e`
- Run: `python -m pytest tests/ -v`
- Run E2E only: `python -m pytest tests/ -m e2e -v`

## Build & Release

- **Dev**: `pip install -e .`
- **CLI**: `panostitcher stitch assets/PANORAMA/100_0240`
- **PyInstaller**: `pyinstaller panostitcher.spec`
- **CI**: GitHub Actions matrix (ubuntu/windows × py3.10/3.12)

## Rules

- Always run `python -m pytest tests/ -v` after any code change.
- Before completing, build the CLI and run it against test assets.
- Do NOT enforce strict 2:1 aspect ratio on the output canvas.
- Metadata cloning must use `-All:All` (broad), not selective tag copying.
- Validate with both unit tests and real asset E2E test.
