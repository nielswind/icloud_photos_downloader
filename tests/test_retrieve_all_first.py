import inspect
import os
from unittest import TestCase, mock

import pytest

from pyicloud_ipd.services.photos import PhotoAlbum
from tests.helpers import (
    DEFAULT_ENV,
    TestResult,
    calc_cookie_dir,
    calc_vcr_dir,
    path_from_project_root,
    print_result_exception,
    run_icloudpd_test,
    run_main_env,
)

MARKER = ".icloudpd_initial_sync_complete"


def _run_with_cassette(
    root_path: str, cassette: str, data_dir: str, cookie_dir: str, params: list[str]
) -> TestResult:
    from vcr import VCR

    vcr = VCR(decode_compressed_response=True, record_mode="none")
    vcr_path = calc_vcr_dir(root_path)
    with vcr.use_cassette(os.path.join(vcr_path, cassette)):
        return print_result_exception(
            run_main_env(DEFAULT_ENV, ["-d", data_dir, "--cookie-directory", cookie_dir] + params)
        )


class RetrieveAllFirstTestCase(TestCase):
    @pytest.fixture(autouse=True)
    def inject_fixtures(self) -> None:
        self.root_path = path_from_project_root(__file__)
        self.fixtures_path = os.path.join(self.root_path, "fixtures")

    def test_retrieve_all_first_creates_marker(self) -> None:
        """First run (no marker) should complete the full scan and write the marker file."""
        base_dir = os.path.join(self.fixtures_path, inspect.stack()[0][3])

        with mock.patch("icloudpd.download.download_media") as dp_patched:
            dp_patched.return_value = True
            with mock.patch("icloudpd.download.os.utime"):
                data_dir, result = run_icloudpd_test(
                    self.assertEqual,
                    self.root_path,
                    base_dir,
                    "listing_photos.yml",
                    [],
                    [],
                    [
                        "--username",
                        "jdoe@gmail.com",
                        "--password",
                        "password1",
                        "--retrieve-all-first",
                        "--recent",
                        "3",
                        "--no-progress-bar",
                        "--threads-num",
                        "1",
                    ],
                )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue(
            os.path.exists(os.path.join(data_dir, MARKER)),
            "Marker file should be created after the initial full scan",
        )
        self.assertIn("Initial sync complete.", result.output)

    def test_retrieve_all_first_no_until_found_error(self) -> None:
        """Incremental mode (marker exists) without --until-found should exit with error."""
        base_dir = os.path.join(self.fixtures_path, inspect.stack()[0][3])

        # First run: create the marker
        with mock.patch("icloudpd.download.download_media") as dp_patched:
            dp_patched.return_value = True
            with mock.patch("icloudpd.download.os.utime"):
                data_dir, result = run_icloudpd_test(
                    self.assertEqual,
                    self.root_path,
                    base_dir,
                    "listing_photos.yml",
                    [],
                    [],
                    [
                        "--username",
                        "jdoe@gmail.com",
                        "--password",
                        "password1",
                        "--retrieve-all-first",
                        "--recent",
                        "3",
                        "--no-progress-bar",
                        "--threads-num",
                        "1",
                    ],
                )
        self.assertEqual(result.exit_code, 0)
        self.assertTrue(os.path.exists(os.path.join(data_dir, MARKER)))

        # Second run: no --until-found → should fail
        cookie_dir = calc_cookie_dir(base_dir)
        result2 = _run_with_cassette(
            self.root_path,
            "listing_photos.yml",
            data_dir,
            cookie_dir,
            [
                "--username",
                "jdoe@gmail.com",
                "--password",
                "password1",
                "--retrieve-all-first",
                "--no-progress-bar",
                "--threads-num",
                "1",
            ],
        )

        self.assertEqual(
            result2.exit_code, 1, "Should fail without --until-found in incremental mode"
        )
        self.assertIn(
            "--retrieve-all-first in incremental mode requires --until-found",
            result2.output,
        )

    def test_retrieve_all_first_incremental_uses_descending(self) -> None:
        """Incremental mode (marker exists) should set DESCENDING direction on albums."""
        base_dir = os.path.join(self.fixtures_path, inspect.stack()[0][3])

        # First run: create the marker
        with mock.patch("icloudpd.download.download_media") as dp_patched:
            dp_patched.return_value = True
            with mock.patch("icloudpd.download.os.utime"):
                data_dir, result = run_icloudpd_test(
                    self.assertEqual,
                    self.root_path,
                    base_dir,
                    "listing_photos.yml",
                    [],
                    [],
                    [
                        "--username",
                        "jdoe@gmail.com",
                        "--password",
                        "password1",
                        "--retrieve-all-first",
                        "--recent",
                        "3",
                        "--no-progress-bar",
                        "--threads-num",
                        "1",
                    ],
                )
        self.assertEqual(result.exit_code, 0)

        # Second run: incremental — spy on album direction
        recorded_directions: list[str] = []
        original_iter = PhotoAlbum.__iter__

        def spying_iter(self_album: PhotoAlbum) -> object:
            recorded_directions.append(self_album.direction)
            return original_iter(self_album)

        cookie_dir = calc_cookie_dir(base_dir)
        with (
            mock.patch("icloudpd.download.download_media") as dp_patched,
            mock.patch("icloudpd.download.os.utime"),
            mock.patch.object(PhotoAlbum, "__iter__", spying_iter),
        ):
            dp_patched.return_value = True
            result2 = _run_with_cassette(
                self.root_path,
                "listing_photos.yml",
                data_dir,
                cookie_dir,
                [
                    "--username",
                    "jdoe@gmail.com",
                    "--password",
                    "password1",
                    "--retrieve-all-first",
                    "--until-found",
                    "100",
                    "--recent",
                    "3",
                    "--no-progress-bar",
                    "--threads-num",
                    "1",
                ],
            )

        self.assertEqual(result2.exit_code, 0, result2.output)
        self.assertTrue(len(recorded_directions) > 0, "PhotoAlbum.__iter__ should have been called")
        self.assertTrue(
            all(d == "DESCENDING" for d in recorded_directions),
            f"All albums should use DESCENDING in incremental mode, got: {recorded_directions}",
        )

    def test_retrieve_all_first_incremental_date_cutoff(self) -> None:
        """Incremental mode should stop early when all photos are older than skip-created-before."""
        base_dir = os.path.join(self.fixtures_path, inspect.stack()[0][3])

        # First run: create the marker
        with mock.patch("icloudpd.download.download_media") as dp_patched:
            dp_patched.return_value = True
            with mock.patch("icloudpd.download.os.utime"):
                data_dir, result = run_icloudpd_test(
                    self.assertEqual,
                    self.root_path,
                    base_dir,
                    "listing_photos.yml",
                    [],
                    [],
                    [
                        "--username",
                        "jdoe@gmail.com",
                        "--password",
                        "password1",
                        "--retrieve-all-first",
                        "--recent",
                        "3",
                        "--no-progress-bar",
                        "--threads-num",
                        "1",
                    ],
                )
        self.assertEqual(result.exit_code, 0)

        # Second run: skip-created-before 2019-01-01 — all cassette photos are from 2018
        cookie_dir = calc_cookie_dir(base_dir)
        with mock.patch("icloudpd.download.download_media") as dp_patched:
            dp_patched.return_value = True
            with mock.patch("icloudpd.download.os.utime"):
                result2 = _run_with_cassette(
                    self.root_path,
                    "listing_photos.yml",
                    data_dir,
                    cookie_dir,
                    [
                        "--username",
                        "jdoe@gmail.com",
                        "--password",
                        "password1",
                        "--retrieve-all-first",
                        "--until-found",
                        "100",
                        "--skip-created-before",
                        "2019-01-01",
                        "--no-progress-bar",
                        "--threads-num",
                        "1",
                    ],
                )

        self.assertEqual(result2.exit_code, 0, result2.output)
        self.assertIn("Reached date cutoff", result2.output)
