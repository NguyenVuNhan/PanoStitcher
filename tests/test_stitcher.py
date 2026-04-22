"""Unit tests for the stitching pipeline (subprocess calls mocked)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from panostitcher.stitcher import (
    StitchError,
    StitchResult,
    _apply_priors,
    _resolve_positions,
    _set_position,
    stitch_panorama,
)


# ------------------------------------------------------------------
# PTO manipulation helpers
# ------------------------------------------------------------------


class TestSetPosition:
    def test_replace_zeros(self):
        line = "i w4000 h3000 f0 v73.7 r0 p0 y0 n\"DJI_0001.JPG\""
        result = _set_position(line, yaw=45.0, pitch=-60.0, roll=1.5)
        assert "y45.0" in result
        assert "p-60.0" in result
        assert "r1.5" in result

    def test_preserves_other_params(self):
        line = "i w4000 h3000 f0 v73.7 Ra0 Rb0 r0 p0 y0 Vy0 n\"test.JPG\""
        result = _set_position(line, 10.0, 20.0, 0.0)
        # Must NOT clobber Ra, Rb, or Vy
        assert "Ra0" in result
        assert "Rb0" in result
        assert "Vy0" in result


class TestApplyPriors:
    def test_writes_priors_and_v_lines(self, tmp_path: Path):
        pto = tmp_path / "test.pto"
        pto.write_text(
            "p f2 w8000 h4000 v360\n"
            "i w4000 h3000 f0 v73.7 r0 p0 y0 n\"img0.jpg\"\n"
            "i w4000 h3000 f0 v=0 r0 p0 y0 n\"img1.jpg\"\n"
            "i w4000 h3000 f0 v=0 r0 p0 y0 n\"img2.jpg\"\n"
        )
        positions = [(0.0, -90.0, 0.0), (0.0, -60.0, 0.0), (45.0, -60.0, 0.0)]
        _apply_priors(pto, positions)

        content = pto.read_text()
        # Image 0 should have pitch -90
        assert "p-90.0" in content
        # Optimisation variable for image 1 but NOT image 0 (anchor)
        assert "v y1 p1 r1" in content
        assert "v y0 p0 r0" not in content


class TestResolvePositions:
    @patch("panostitcher.stitcher.read_gimbal_angles")
    def test_uses_exif_when_available(self, mock_gimbal):
        mock_gimbal.return_value = [
            {"yaw": 0.0, "pitch": -90.0, "roll": 0.0},
            {"yaw": 10.0, "pitch": -60.0, "roll": 0.5},
        ]
        positions = _resolve_positions([Path("a.jpg"), Path("b.jpg")])
        assert positions[0] == (0.0, -90.0, 0.0)
        assert positions[1] == (10.0, -60.0, 0.5)

    @patch("panostitcher.stitcher.read_gimbal_angles", return_value=None)
    def test_falls_back_to_preset(self, _mock):
        images = [Path(f"DJI_{i:04d}.JPG") for i in range(1, 27)]
        positions = _resolve_positions(images)
        assert len(positions) == 26

    @patch("panostitcher.stitcher.read_gimbal_angles", return_value=None)
    def test_unknown_count_raises(self, _mock):
        images = [Path(f"DJI_{i:04d}.JPG") for i in range(1, 13)]
        with pytest.raises(StitchError, match="No EXIF gimbal data"):
            _resolve_positions(images)


# ------------------------------------------------------------------
# Full pipeline (all subprocesses mocked)
# ------------------------------------------------------------------


class TestStitchPanorama:
    @patch("panostitcher.stitcher.inject_gpano")
    @patch("panostitcher.stitcher.clone_metadata")
    @patch("panostitcher.stitcher.read_gimbal_angles", return_value=None)
    @patch("panostitcher.stitcher._resolve_magick", return_value="magick")
    @patch("panostitcher.stitcher.subprocess.run")
    def test_happy_path(
        self, mock_run, mock_magick, mock_gimbal, mock_clone, mock_gpano,
        fake_pano_tree: Path, tmp_path: Path,
    ):
        folder = fake_pano_tree / "PANORAMA" / "100_0001"

        # subprocess.run returns success for every call
        def side_effect_happy(args, **kw):
            # magick identify needs to return dimensions + offsets
            if "identify" in args:
                return MagicMock(returncode=0, stdout="8000 4000 +0 +0", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect_happy

        # We also need to create a fake tiff in the temp dir.
        # Patch tempfile to use a dir we control so we can plant a tiff.
        import tempfile as _tf

        controlled_tmp = tmp_path / "stitch_work"
        controlled_tmp.mkdir()

        orig_td = _tf.TemporaryDirectory

        class FakeTempDir:
            def __init__(self, **kw):
                self.name = str(controlled_tmp)

            def __enter__(self):
                return self.name

            def __exit__(self, *a):
                pass

        with patch("panostitcher.stitcher.tempfile.TemporaryDirectory", FakeTempDir):
            # Plant fake PTO that pto_gen would produce (26 image lines)
            pto_lines = ["p f2 w8000 h4000 v360\n"]
            for i in range(1, 27):
                pto_lines.append(
                    f'i w4000 h3000 f0 v73.7 Ra0 Rb0 Rc0 Rd0 Re0 Eev0 Er1 Eb1 r0 p0 y0 '
                    f'TrX0 TrY0 TrZ0 Tpy0 Tpp0 j0 a0 b0 c0 d0 e0 g0 t0 Va1 Vb0 Vc0 Vd0 '
                    f'Vx0 Vy0 n"DJI_{i:04d}.JPG"\n'
                )
            (controlled_tmp / "project.pto").write_text("".join(pto_lines))
            # Plant fake tiff outputs that nona would produce
            (controlled_tmp / "remapped_0000.tif").write_bytes(b"fake")
            result = stitch_panorama(folder, output_dir=tmp_path)

        assert result.success
        assert mock_run.call_count >= 7  # pto_gen, cpfind, cpclean, autoopt, pano_modify, nona, enblend, magick
        mock_clone.assert_called_once()
        mock_gpano.assert_called_once()

    def test_empty_folder(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        result = stitch_panorama(empty)
        assert not result.success
        assert "No DJI JPEGs" in result.error

    @patch("panostitcher.stitcher.inject_gpano")
    @patch("panostitcher.stitcher.clone_metadata")
    @patch("panostitcher.stitcher.read_gimbal_angles", return_value=None)
    @patch("panostitcher.stitcher._resolve_magick", return_value="magick")
    @patch("panostitcher.stitcher.subprocess.run")
    def test_gpu_fallback(
        self, mock_run, mock_magick, mock_gimbal, mock_clone, mock_gpano,
        fake_pano_tree: Path, tmp_path: Path,
    ):
        """When nona -g fails, pipeline should retry without GPU."""
        folder = fake_pano_tree / "PANORAMA" / "100_0001"
        ok = MagicMock(returncode=0, stdout="", stderr="")

        call_count = 0

        def side_effect(args, **kw):
            nonlocal call_count
            call_count += 1
            # Make the first nona call fail (the one with -g)
            if "nona" in args and "-g" in args:
                return MagicMock(returncode=1, stdout="", stderr="OpenCL error")
            # magick identify needs to return dimensions + offsets
            if "identify" in args:
                return MagicMock(returncode=0, stdout="8000 4000 +0 +0", stderr="")
            return ok

        mock_run.side_effect = side_effect

        import tempfile as _tf

        controlled_tmp = tmp_path / "work"
        controlled_tmp.mkdir()

        class FakeTD:
            def __init__(self, **kw):
                self.name = str(controlled_tmp)

            def __enter__(self):
                return self.name

            def __exit__(self, *a):
                pass

        with patch("panostitcher.stitcher.tempfile.TemporaryDirectory", FakeTD):
            # Plant fake PTO that pto_gen would produce (26 image lines)
            pto_lines = ["p f2 w8000 h4000 v360\n"]
            for i in range(1, 27):
                pto_lines.append(
                    f'i w4000 h3000 f0 v73.7 Ra0 Rb0 Rc0 Rd0 Re0 Eev0 Er1 Eb1 r0 p0 y0 '
                    f'TrX0 TrY0 TrZ0 Tpy0 Tpp0 j0 a0 b0 c0 d0 e0 g0 t0 Va1 Vb0 Vc0 Vd0 '
                    f'Vx0 Vy0 n"DJI_{i:04d}.JPG"\n'
                )
            (controlled_tmp / "project.pto").write_text("".join(pto_lines))
            (controlled_tmp / "remapped_0000.tif").write_bytes(b"fake")
            result = stitch_panorama(folder, output_dir=tmp_path, gpu=True)

        assert result.success
        # Verify nona was called twice (gpu fail, then cpu retry)
        nona_calls = [
            c for c in mock_run.call_args_list
            if any("nona" in str(a) for a in c.args[0])
        ]
        assert len(nona_calls) >= 2
