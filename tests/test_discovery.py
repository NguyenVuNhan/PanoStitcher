"""Unit tests for panorama folder discovery."""

from __future__ import annotations

from pathlib import Path

from panostitcher.discovery import (
    find_panorama_folders,
    is_already_stitched,
    is_panorama_folder,
    list_images,
)


class TestIsPanoramaFolder:
    def test_good_folder(self, fake_pano_tree: Path):
        good = fake_pano_tree / "PANORAMA" / "100_0001"
        assert is_panorama_folder(good) is True

    def test_too_few_images(self, fake_pano_tree: Path):
        bad = fake_pano_tree / "PANORAMA" / "100_0002"
        assert is_panorama_folder(bad) is False

    def test_nonexistent(self, tmp_path: Path):
        assert is_panorama_folder(tmp_path / "nope") is False


class TestIsAlreadyStitched:
    def test_marker_file(self, fake_pano_tree: Path):
        done = fake_pano_tree / "PANORAMA" / "100_0003"
        assert is_already_stitched(done) is True

    def test_output_file(self, fake_pano_tree: Path):
        folder = fake_pano_tree / "PANORAMA" / "100_0001"
        # Create the expected output file
        (fake_pano_tree / "PANORAMA" / "100_0001_panorama.jpg").touch()
        assert is_already_stitched(folder) is True

    def test_not_done(self, fake_pano_tree: Path):
        folder = fake_pano_tree / "PANORAMA" / "100_0001"
        assert is_already_stitched(folder) is False

    def test_output_dir(self, fake_pano_tree: Path, tmp_path: Path):
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        folder = fake_pano_tree / "PANORAMA" / "100_0001"
        assert is_already_stitched(folder, out_dir) is False
        (out_dir / "100_0001_panorama.jpg").touch()
        assert is_already_stitched(folder, out_dir) is True


class TestFindPanoramaFolders:
    def test_finds_unprocessed(self, fake_pano_tree: Path):
        found = find_panorama_folders(fake_pano_tree)
        names = [f.name for f in found]
        assert "100_0001" in names
        assert "100_0004" in names  # deeply nested
        assert "100_0002" not in names  # too few images
        assert "100_0003" not in names  # already done

    def test_include_done(self, fake_pano_tree: Path):
        found = find_panorama_folders(fake_pano_tree, include_done=True)
        names = [f.name for f in found]
        assert "100_0003" in names

    def test_nonexistent_root(self, tmp_path: Path):
        import pytest

        with pytest.raises(FileNotFoundError):
            find_panorama_folders(tmp_path / "no_such_dir")

    def test_empty_root(self, tmp_path: Path):
        assert find_panorama_folders(tmp_path) == []


class TestListImages:
    def test_sorted_list(self, fake_pano_tree: Path):
        imgs = list_images(fake_pano_tree / "PANORAMA" / "100_0001")
        assert len(imgs) == 26
        assert imgs[0].name == "DJI_0001.JPG"
        assert imgs[-1].name == "DJI_0026.JPG"
