import inspect
import os
import shutil
import threading
import time as real_time
from typing import NamedTuple, NoReturn
from unittest import TestCase, mock

import pytest
from requests import Timeout
from requests.exceptions import ConnectionError
from vcr import VCR

import pyicloud_ipd
from foundation.core import constant
from icloudpd.authentication import authenticator, request_2fa, request_2fa_web
from icloudpd.base import dummy_password_writter
from icloudpd.logger import setup_logger
from icloudpd.mfa_provider import MFAProvider
from icloudpd.status import Status, StatusExchange
from pyicloud_ipd.exceptions import PyiCloudFailedMFAException
from pyicloud_ipd.sms import parse_trusted_phone_numbers_payload
from tests.helpers import path_from_project_root, recreate_path, run_cassette

vcr = VCR(decode_compressed_response=True, record_mode="none")


class AuthenticationTestCase(TestCase):
    @pytest.fixture(autouse=True)
    def inject_fixtures(self) -> None:
        self.root_path = path_from_project_root(__file__)
        self.fixtures_path = os.path.join(self.root_path, "fixtures")
        self.vcr_path = os.path.join(self.root_path, "vcr_cassettes")
        self.data_path = os.path.join(self.root_path, "data")

    def test_failed_auth(self) -> None:
        base_dir = os.path.join(self.fixtures_path, inspect.stack()[0][3])
        cookie_dir = os.path.join(base_dir, "cookie")

        for dir in [base_dir, cookie_dir]:
            recreate_path(dir)

        with vcr.use_cassette(os.path.join(self.vcr_path, "failed_auth.yml")):  # noqa: SIM117
            with self.assertRaises(pyicloud_ipd.exceptions.PyiCloudFailedLoginException) as context:
                authenticator(
                    setup_logger(),
                    "com",
                    {"test": (constant("dummy"), dummy_password_writter)},
                    MFAProvider.CONSOLE,
                    StatusExchange(),
                    "bad_username",
                    lambda: None,
                    None,
                    cookie_dir,
                    "EC5646DE-9423-11E8-BF21-14109FE0B321",
                )

        # self.assertIn(
        #     "Failed to login with srp, falling back to old raw password authentication.",
        #     result.output,
        # )
        self.assertTrue("Invalid email/password combination." in str(context.exception))

    @pytest.mark.skip(reason="No longer support fallback to raw")
    def test_fallback_raw_password(self) -> None:
        base_dir = os.path.join(self.fixtures_path, inspect.stack()[0][3])
        cookie_dir = os.path.join(base_dir, "cookie")

        for dir in [base_dir, cookie_dir]:
            recreate_path(dir)

        result = run_cassette(
            os.path.join(self.vcr_path, "fallback_raw_password.yml"),
            [
                "--username",
                "jdoe@gmail.com",
                "--password",
                "password1",
                "--no-progress-bar",
                "--cookie-directory",
                cookie_dir,
                "--auth-only",
            ],
        )
        self.assertIn(
            "Failed to login with srp, falling back to old raw password authentication.",
            result.output,
        )
        self.assertIn("Authentication completed successfully", result.output)
        self.assertEqual(result.exit_code, 0, "exit code")

    def test_successful_token_validation(self) -> None:
        base_dir = os.path.join(self.fixtures_path, inspect.stack()[0][3])
        cookie_dir = os.path.join(base_dir, "cookie")
        cookie_master_path = os.path.join(self.root_path, "cookie")

        recreate_path(base_dir)

        shutil.copytree(cookie_master_path, cookie_dir)

        result = run_cassette(
            os.path.join(self.vcr_path, "successful_auth.yml"),
            [
                "--username",
                "jdoe@gmail.com",
                "--password",
                "password1",
                "--no-progress-bar",
                "--cookie-directory",
                cookie_dir,
                "--auth-only",
            ],
        )
        self.assertIn("Authentication completed successfully", result.output)
        self.assertEqual(result.exit_code, 0, "exit code")

    def test_password_prompt_2sa(self) -> None:
        base_dir = os.path.join(self.fixtures_path, inspect.stack()[0][3])
        cookie_dir = os.path.join(base_dir, "cookie")

        for dir in [base_dir, cookie_dir]:
            recreate_path(dir)

        result = run_cassette(
            os.path.join(self.vcr_path, "2sa_flow_valid_code.yml"),
            [
                "--username",
                "jdoe@gmail.com",
                "--password",
                "password1",
                "--no-progress-bar",
                "--cookie-directory",
                cookie_dir,
                "--auth-only",
            ],
            input="0\n654321\n",
        )
        self.assertIn("Authenticating...", result.output)
        self.assertIn(
            "Two-step authentication is required",
            result.output,
        )
        self.assertIn("  0: SMS to *******03", result.output)
        self.assertIn("Please choose an option: [0]: 0", result.output)
        self.assertIn("Please enter two-step authentication code: 654321", result.output)
        self.assertIn(
            "Great, you're all set up. The script can now be run without "
            "user interaction until 2SA expires.",
            result.output,
        )
        self.assertEqual(result.exit_code, 0, "exit code")

    def test_password_prompt_2fa(self) -> None:
        base_dir = os.path.join(self.fixtures_path, inspect.stack()[0][3])
        cookie_dir = os.path.join(base_dir, "cookie")

        for dir in [base_dir, cookie_dir]:
            recreate_path(dir)

        result = run_cassette(
            os.path.join(self.vcr_path, "2fa_flow_valid_code.yml"),
            [
                "--username",
                "jdoe@gmail.com",
                "--password",
                "password1",
                "--no-progress-bar",
                "--cookie-directory",
                cookie_dir,
                "--auth-only",
            ],
            input="654321\n",
        )
        self.assertIn("Authenticating...", result.output)
        self.assertIn(
            "Two-factor authentication is required",
            result.output,
        )
        self.assertIn("  a: (***) ***-**81", result.output)
        self.assertIn(
            "Please enter two-factor authentication code or device index (a) to send SMS with a code: 654321",
            result.output,
        )
        self.assertIn(
            "Great, you're all set up. The script can now be run without "
            "user interaction until 2FA expires.",
            result.output,
        )
        self.assertNotIn("Failed to parse response with JSON mimetype", result.output)
        self.assertEqual(result.exit_code, 0, "exit code")

    def test_parse_trusted_phone_numbers_payload_valid(self) -> None:
        html_path = os.path.join(self.data_path, "parse_trusted_phone_numbers_payload_valid.html")
        with open(html_path, encoding="UTF-8") as file:
            html = file.read()
        expected = _TrustedDevice(id=1, obfuscated_number="(***) ***-**81")
        result = parse_trusted_phone_numbers_payload(html)
        self.assertEqual(1, len(result), "number of numbers parsed")
        self.assertEqual(expected, result[0], "parsed number")

    def test_parse_trusted_phone_numbers_payload_minimal(self) -> None:
        html = '<script type="application/json" class="boot_args">{"direct":{"twoSV":{"phoneNumberVerification":{"trustedPhoneNumbers":[{"numberWithDialCode":"+1 (•••) •••-••81","pushMode":"sms","obfuscatedNumber":"(•••) •••-••81","lastTwoDigits":"81","id":1}]},"authInitialRoute":"auth/verify/phone"}}}</script>'  # noqa: E501
        expected = _TrustedDevice(id=1, obfuscated_number="(***) ***-**81")
        result = parse_trusted_phone_numbers_payload(html)
        self.assertEqual(1, len(result), "number of numbers parsed")
        self.assertEqual(expected, result[0], "parsed number")

    def test_parse_trusted_phone_numbers_payload_missing_node0(self) -> None:
        html = '<script type="application/json" class="boot_args">{"MISSINGdirect":{"twoSV":{"phoneNumberVerification":{"trustedPhoneNumbers":[{"numberWithDialCode":"+1 (•••) •••-••81","pushMode":"sms","obfuscatedNumber":"(•••) •••-••81","lastTwoDigits":"81","id":1}]},"authInitialRoute":"auth/verify/phone"}}}</script>'  # noqa: E501
        result = parse_trusted_phone_numbers_payload(html)
        self.assertEqual(0, len(result), "number of numbers parsed")

    def test_parse_trusted_phone_numbers_payload_missing_node1(self) -> None:
        html = '<script type="application/json" class="boot_args">{"direct":{"MISSINGtwoSV":{"phoneNumberVerification":{"trustedPhoneNumbers":[{"numberWithDialCode":"+1 (•••) •••-••81","pushMode":"sms","obfuscatedNumber":"(•••) •••-••81","lastTwoDigits":"81","id":1}]},"authInitialRoute":"auth/verify/phone"}}}</script>'  # noqa: E501
        result = parse_trusted_phone_numbers_payload(html)
        self.assertEqual(0, len(result), "number of numbers parsed")

    def test_parse_trusted_phone_numbers_payload_missing_node2(self) -> None:
        html = '<script type="application/json" class="boot_args">{"direct":{"twoSV":{"MISSINGphoneNumberVerification":{"trustedPhoneNumbers":[{"numberWithDialCode":"+1 (•••) •••-••81","pushMode":"sms","obfuscatedNumber":"(•••) •••-••81","lastTwoDigits":"81","id":1}]},"authInitialRoute":"auth/verify/phone"}}}</script>'  # noqa: E501
        result = parse_trusted_phone_numbers_payload(html)
        self.assertEqual(0, len(result), "number of numbers parsed")

    def test_parse_trusted_phone_numbers_payload_missing_node3(self) -> None:
        html = '<script type="application/json" class="boot_args">{"direct":{"twoSV":{"phoneNumberVerification":{"MISSINGtrustedPhoneNumbers":[{"numberWithDialCode":"+1 (•••) •••-••81","pushMode":"sms","obfuscatedNumber":"(•••) •••-••81","lastTwoDigits":"81","id":1}]},"authInitialRoute":"auth/verify/phone"}}}</script>'  # noqa: E501
        result = parse_trusted_phone_numbers_payload(html)
        self.assertEqual(0, len(result), "number of numbers parsed")

    def test_parse_trusted_phone_numbers_payload_empty_list(self) -> None:
        html = '<script type="application/json" class="boot_args">{"direct":{"twoSV":{"phoneNumberVerification":{"trustedPhoneNumbers":[]},"authInitialRoute":"auth/verify/phone"}}}</script>'  # noqa: E501
        result = parse_trusted_phone_numbers_payload(html)
        self.assertEqual(0, len(result), "number of numbers parsed")

    def test_parse_trusted_phone_numbers_payload_invalid_missing_id(self) -> None:
        html = '<script type="application/json" class="boot_args">{"direct":{"twoSV":{"phoneNumberVerification":{"trustedPhoneNumbers":[{"numberWithDialCode":"+1 (•••) •••-••81","pushMode":"sms","obfuscatedNumber":"(•••) •••-••81","lastTwoDigits":"81","MISSINGid":1}]},"authInitialRoute":"auth/verify/phone"}}}</script>'  # noqa: E501
        result = parse_trusted_phone_numbers_payload(html)
        self.assertEqual(0, len(result), "number of numbers parsed")

    def test_parse_trusted_phone_numbers_payload_invalid_missing_number(self) -> None:
        html = '<script type="application/json" class="boot_args">{"direct":{"twoSV":{"phoneNumberVerification":{"trustedPhoneNumbers":[{"numberWithDialCode":"+1 (•••) •••-••81","pushMode":"sms","MISSINGobfuscatedNumber":"(•••) •••-••81","lastTwoDigits":"81","id":1}]},"authInitialRoute":"auth/verify/phone"}}}</script>'  # noqa: E501
        result = parse_trusted_phone_numbers_payload(html)
        self.assertEqual(0, len(result), "number of numbers parsed")

    def test_non_2fa(self) -> None:
        base_dir = os.path.join(self.fixtures_path, inspect.stack()[0][3])
        cookie_dir = os.path.join(base_dir, "cookie")

        for dir in [base_dir, cookie_dir]:
            recreate_path(dir)

        with vcr.use_cassette(os.path.join(self.vcr_path, "auth_non_2fa.yml")) as cass:
            # To re-record this HTTP request,
            # delete ./tests/vcr_cassettes/auth_requires_2fa.yml,
            # put your actual credentials in here, run the test,
            # and then replace with dummy credentials.
            authenticator(
                setup_logger(),
                "com",
                {"test": (constant("dummy"), dummy_password_writter)},
                MFAProvider.CONSOLE,
                StatusExchange(),
                "jdoe@gmail.com",
                lambda: None,
                None,
                cookie_dir,
                "EC5646DE-9423-11E8-BF21-14109FE0B321",
            )

            self.assertTrue(cass.all_played)

    def test_failed_auth_503(self) -> None:
        base_dir = os.path.join(self.fixtures_path, inspect.stack()[0][3])
        cookie_dir = os.path.join(base_dir, "cookie")

        for dir in [base_dir, cookie_dir]:
            recreate_path(dir)

        result = run_cassette(
            os.path.join(self.vcr_path, "failed_auth_503.yml"),
            [
                "--username",
                "jdoe@gmail.com",
                "--password",
                "password1",
                "--no-progress-bar",
                "--cookie-directory",
                cookie_dir,
                "--auth-only",
            ],
        )
        self.assertNotIn(
            "Failed to login with srp, falling back to old raw password authentication.",
            result.output,
        )
        self.assertIn("Apple iCloud is temporary refusing to serve icloudpd", result.output)
        self.assertEqual(result.exit_code, 1, "exit code")

    def test_failed_auth_503_watch(self) -> None:
        base_dir = os.path.join(self.fixtures_path, inspect.stack()[0][3])
        cookie_dir = os.path.join(base_dir, "cookie")

        for dir in [base_dir, cookie_dir]:
            recreate_path(dir)

        result = run_cassette(
            os.path.join(self.vcr_path, "failed_auth_503.yml"),
            [
                "--username",
                "jdoe@gmail.com",
                "--password",
                "password1",
                "--no-progress-bar",
                "--directory",
                base_dir,
                "--cookie-directory",
                cookie_dir,
                "--watch-with-interval",
                "1",
            ],
        )
        self.assertNotIn(
            "Failed to login with srp, falling back to old raw password authentication.",
            result.output,
        )
        self.assertEqual(
            2,
            result.output.count("Apple iCloud is temporary refusing to serve icloudpd"),
        )
        self.assertEqual(2, result.output.count("Waiting for 1 sec..."))
        # self.assertTrue("Can't overwrite existing cassette" in str(context.exception))
        self.assertEqual(result.exit_code, 1, "exit code")

    def test_connection_error(self) -> None:
        base_dir = os.path.join(self.fixtures_path, inspect.stack()[0][3])
        cookie_dir = os.path.join(base_dir, "cookie")

        for dir in [base_dir, cookie_dir]:
            recreate_path(dir)

        def mock_raise_response_error(*args, **kwargs) -> NoReturn:  # type: ignore [no-untyped-def]
            raise ConnectionError("Simulated Connection Error")

        with mock.patch(
            "requests.Session.request", side_effect=mock_raise_response_error
        ) as pa_request:
            result = run_cassette(
                os.path.join(self.vcr_path, "failed_auth_503.yml"),
                [
                    "--username",
                    "jdoe@gmail.com",
                    "--password",
                    "password1",
                    "--no-progress-bar",
                    "--directory",
                    base_dir,
                    "--cookie-directory",
                    cookie_dir,
                    # "--watch-with-interval",
                    # "1",
                ],
            )
            pa_request.assert_called_once()
            self.assertIn(
                "Authenticating...",
                result.output,
            )
            self.assertIn(
                "Cannot connect to Apple iCloud service",
                result.output,
            )
            self.assertEqual(result.exit_code, 1, "exit code")

    def test_timeout_error(self) -> None:
        base_dir = os.path.join(self.fixtures_path, inspect.stack()[0][3])
        cookie_dir = os.path.join(base_dir, "cookie")

        for dir in [base_dir, cookie_dir]:
            recreate_path(dir)

        def mock_raise_response_error(*args, **kwargs) -> NoReturn:  # type: ignore [no-untyped-def]
            raise TimeoutError("Simulated TimeoutError")

        with mock.patch(
            "requests.Session.request", side_effect=mock_raise_response_error
        ) as pa_request:
            result = run_cassette(
                os.path.join(self.vcr_path, "failed_auth_503.yml"),
                [
                    "--username",
                    "jdoe@gmail.com",
                    "--password",
                    "password1",
                    "--no-progress-bar",
                    "--directory",
                    base_dir,
                    "--cookie-directory",
                    cookie_dir,
                    # "--watch-with-interval",
                    # "1",
                ],
            )
            pa_request.assert_called_once()
            self.assertIn(
                "Authenticating...",
                result.output,
            )
            self.assertIn(
                "Cannot connect to Apple iCloud service",
                result.output,
            )
            self.assertEqual(result.exit_code, 1, "exit code")

    def test_timeout(self) -> None:
        base_dir = os.path.join(self.fixtures_path, inspect.stack()[0][3])
        cookie_dir = os.path.join(base_dir, "cookie")

        for dir in [base_dir, cookie_dir]:
            recreate_path(dir)

        def mock_raise_response_error(*args, **kwargs) -> NoReturn:  # type: ignore [no-untyped-def]
            raise Timeout("Simulated Timeout")

        with mock.patch(
            "requests.Session.request", side_effect=mock_raise_response_error
        ) as pa_request:
            result = run_cassette(
                os.path.join(self.vcr_path, "failed_auth_503.yml"),
                [
                    "--username",
                    "jdoe@gmail.com",
                    "--password",
                    "password1",
                    "--no-progress-bar",
                    "--directory",
                    base_dir,
                    "--cookie-directory",
                    cookie_dir,
                    # "--watch-with-interval",
                    # "1",
                ],
            )
            pa_request.assert_called_once()
            self.assertIn(
                "Authenticating...",
                result.output,
            )
            self.assertIn(
                "Cannot connect to Apple iCloud service",
                result.output,
            )
            self.assertEqual(result.exit_code, 1, "exit code")


class _TrustedDevice(NamedTuple):
    id: int
    obfuscated_number: str


class TwoFAUnitTestCase(TestCase):
    """Unit tests for request_2fa_web() and request_2fa() push notification behaviour."""

    def _run_web_in_thread(
        self, mock_icloud: mock.MagicMock, status_exchange: StatusExchange
    ) -> tuple[threading.Thread, threading.Event, list[Exception]]:
        logger = setup_logger()
        errors: list[Exception] = []
        done = threading.Event()

        def run() -> None:
            try:
                request_2fa_web(mock_icloud, logger, status_exchange)
            except Exception as e:
                errors.append(e)
            finally:
                done.set()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread, done, errors

    def test_request_2fa_web_triggers_push(self) -> None:
        """request_2fa_web must call trigger_push_notification before waiting for input."""
        push_called = threading.Event()

        def push_ok() -> bool:
            push_called.set()
            return True

        mock_icloud = mock.MagicMock()
        mock_icloud.trigger_push_notification.side_effect = push_ok
        mock_icloud.validate_2fa_code.return_value = True
        mock_icloud.requires_2fa = False

        status_exchange = StatusExchange()
        thread, done, errors = self._run_web_in_thread(mock_icloud, status_exchange)

        self.assertTrue(push_called.wait(timeout=5), "trigger_push_notification was not called")
        mock_icloud.trigger_push_notification.assert_called_once()

        status_exchange.set_payload("654321")
        done.wait(timeout=5)
        thread.join(timeout=5)

        if errors:
            raise errors[0]

    def test_request_2fa_web_push_failure_warns(self) -> None:
        """request_2fa_web logs a warning when push fails and continues to accept a code."""
        push_called = threading.Event()

        def push_fail() -> bool:
            push_called.set()
            return False

        mock_icloud = mock.MagicMock()
        mock_icloud.trigger_push_notification.side_effect = push_fail
        mock_icloud.validate_2fa_code.return_value = True
        mock_icloud.requires_2fa = False

        status_exchange = StatusExchange()

        with self.assertLogs("icloudpd", level="WARNING") as log_ctx:
            thread, done, errors = self._run_web_in_thread(mock_icloud, status_exchange)
            self.assertTrue(push_called.wait(timeout=5), "trigger_push_notification was not called")
            status_exchange.set_payload("654321")
            done.wait(timeout=5)
            thread.join(timeout=5)

        if errors:
            raise errors[0]

        self.assertTrue(
            any("Failed to send 2FA push notification" in line for line in log_ctx.output),
            f"Expected push failure warning, got: {log_ctx.output}",
        )

    def test_request_2fa_push_failure_warns(self) -> None:
        """request_2fa logs a WARNING (not DEBUG) when trigger_push_notification fails."""
        mock_icloud = mock.MagicMock()
        mock_icloud.trigger_push_notification.return_value = False
        mock_icloud.get_trusted_phone_numbers.return_value = []
        mock_icloud.validate_2fa_code.return_value = True

        logger = setup_logger()

        with (
            self.assertLogs("icloudpd", level="WARNING") as log_ctx,
            mock.patch("builtins.input", return_value="654321"),
        ):
            request_2fa(mock_icloud, logger)

        self.assertTrue(
            any("Failed to send 2FA push notification" in line for line in log_ctx.output),
            f"Expected push failure warning, got: {log_ctx.output}",
        )

    def test_request_2fa_web_wrong_initial_status_raises(self) -> None:
        """request_2fa_web raises if status is not NO_INPUT_NEEDED when called."""
        mock_icloud = mock.MagicMock()
        se = StatusExchange()
        se._status = Status.NEED_MFA

        with self.assertRaises(PyiCloudFailedMFAException) as ctx:
            request_2fa_web(mock_icloud, setup_logger(), se)

        self.assertIn("Expected NO_INPUT_NEEDED", str(ctx.exception))

    def test_request_2fa_web_unexpected_status_in_loop_raises(self) -> None:
        """request_2fa_web raises when status becomes an unexpected value mid-loop."""
        mock_icloud = mock.MagicMock()
        mock_icloud.trigger_push_notification.return_value = True

        mock_status = mock.MagicMock(spec=StatusExchange)
        # First call (NO_INPUT_NEEDED → NEED_MFA) succeeds; second (SUPPLIED_MFA → CHECKING_MFA) fails
        mock_status.replace_status.side_effect = [True, False]
        mock_status.get_status.return_value = (
            Status.CHECKING_PASSWORD
        )  # not NEED_MFA → falls through

        with self.assertRaises(PyiCloudFailedMFAException) as ctx:
            request_2fa_web(mock_icloud, setup_logger(), mock_status)

        self.assertIn("Failed to change status", str(ctx.exception))

    def test_request_2fa_web_empty_payload_raises(self) -> None:
        """request_2fa_web raises when SUPPLIED_MFA status has no associated payload."""
        mock_icloud = mock.MagicMock()
        mock_icloud.trigger_push_notification.return_value = True

        mock_status = mock.MagicMock(spec=StatusExchange)
        mock_status.replace_status.side_effect = [True, True]  # initial + SUPPLIED→CHECKING
        mock_status.get_status.return_value = Status.SUPPLIED_MFA  # skips NEED_MFA sleep
        mock_status.get_payload.return_value = None  # no payload available

        with self.assertRaises(PyiCloudFailedMFAException) as ctx:
            request_2fa_web(mock_icloud, setup_logger(), mock_status)

        self.assertIn("Internal error", str(ctx.exception))

    def test_request_2fa_web_set_error_fails_raises(self) -> None:
        """request_2fa_web raises when validate fails and set_error cannot reset state."""
        mock_icloud = mock.MagicMock()
        mock_icloud.trigger_push_notification.return_value = True
        mock_icloud.validate_2fa_code.return_value = False

        mock_status = mock.MagicMock(spec=StatusExchange)
        mock_status.replace_status.side_effect = [True, True]
        mock_status.get_status.return_value = Status.SUPPLIED_MFA
        mock_status.get_payload.return_value = "111111"
        mock_status.set_error.return_value = False  # cannot transition back

        with self.assertRaises(PyiCloudFailedMFAException) as ctx:
            request_2fa_web(mock_icloud, setup_logger(), mock_status)

        self.assertIn("Failed to chage status of invalid code", str(ctx.exception))

    def test_request_2fa_web_invalid_code_retries(self) -> None:
        """request_2fa_web loops back to wait for another code when validation fails."""
        push_called = threading.Event()

        def push_ok() -> bool:
            push_called.set()
            return True

        mock_icloud = mock.MagicMock()
        mock_icloud.trigger_push_notification.side_effect = push_ok
        mock_icloud.validate_2fa_code.side_effect = [False, True]  # first bad, second good
        mock_icloud.requires_2fa = False

        se = StatusExchange()
        errors: list[Exception] = []
        done = threading.Event()

        def run() -> None:
            try:
                request_2fa_web(mock_icloud, setup_logger(), se)
            except Exception as e:
                errors.append(e)
            finally:
                done.set()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

        push_called.wait(timeout=5)
        se.set_payload("111111")  # wrong code → validate returns False → loops back to NEED_MFA

        # Wait for status to return to NEED_MFA after set_error resets it
        deadline = real_time.time() + 5
        while real_time.time() < deadline:
            if se.get_status() == Status.NEED_MFA:
                break
            real_time.sleep(0.02)

        se.set_payload("654321")  # correct code
        done.wait(timeout=5)
        thread.join(timeout=5)

        if errors:
            raise errors[0]

        self.assertEqual(mock_icloud.validate_2fa_code.call_count, 2)
