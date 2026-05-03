# Task Reload: Fix notify-before-password-status-clear

## Task Summary
Fix the ordering bug where the mail notification for 2FA was sent **after** the user
had already entered their password through the web UI, instead of before.

## Status: Fix implemented, tests passing — needs PR

## What Was Wrong

The previous fix (commit `8ca16a7`) only reordered `notificator()` before `writer()` inside
`authentication.py`. Both calls still happened **after** `PyiCloudService.__init__()` returned,
which is itself after `get_password_from_webui()` had already blocked and the user had entered
their password. The notification still arrived too late.

## What Was Fixed (current branch: fix/notify-before-password-status-clear)

The notification must fire **before** `get_password_from_webui()` blocks for input.

### Changes Made

#### `src/icloudpd/base.py`

1. **`get_password_from_webui()`** — added `notificator: Callable[[], None]` parameter.
   Calls it immediately after transitioning to `NEED_PASSWORD` (before the blocking loop).
   This is the moment the webui password form appears — the correct time to alert the user.

2. **User loop in `run_with_configs()`** — three changes:
   - Moved `notificator = partial(notificator_builder, ...)` construction **before**
     `password_providers_dict` so it's available when wiring the webui reader.
   - Created a **one-shot wrapper** (`one_shot_notificator`) using a `_make_one_shot()`
     factory function with a `List[bool]` flag. Prevents double-notification: when the
     webui reader fires it early, the later call in `authenticator()` (for the 2FA/2SA
     branch) becomes a no-op.
   - Passes `one_shot_notificator` (not the raw `notificator`) to both the webui
     password reader (`partial(get_password_from_webui, ..., one_shot_notificator)`)
     and to `core_single_run()`.

#### `src/icloudpd/authentication.py`
No changes needed — the `notificator()` call before the writer is already correct.
With the one-shot wrapper it becomes a no-op when webui was used for the password.

### Correct sequence after fix:
1. icloudpd needs to re-authenticate
2. `get_password_from_webui()` → status = `NEED_PASSWORD` → **notification sent**
3. Webui shows password form
4. User sees email, visits webui, enters password
5. Status → `CHECKING_PASSWORD`, `PyiCloudService` returns
6. `authenticator()` calls `notificator()` (one-shot, no-op — already fired)
7. `writer()` transitions `CHECKING_PASSWORD` → `NO_INPUT_NEEDED`
8. Webui shows 2FA form → user enters code

### Case: password from keyring, 2FA via webui
- `get_password_from_webui()` is NOT called → one-shot not fired
- `authenticator()` calls `notificator()` → notification sent (before `request_2fa_web()` blocks) ✓

## Test Results
- All tests passing except `test_folder_structure_de_posix` (pre-existing locale issue, unrelated)
- `mypy` type check: clean

## What Still Needs Doing

### A. PR
Create PR against `master` with the fix. Branch: `fix/notify-before-password-status-clear`

### B. Secondary issue (not yet fixed)
The notification email body reads:
> "Please log in to your server and run the script manually to update two-step authentication."

When `--mfa-provider webui` is in use this is wrong — user should be told to visit the web UI.
File: `src/icloudpd/email_notifications.py`

### C. Coverage
New lines in `get_password_from_webui()` (lines 139-163 in base.py) are uncovered.
The project requires 100% coverage for PRs. Need tests that:
- Exercise `get_password_from_webui()` with a mock notificator
- Verify notificator is called before the blocking loop
- Verify one-shot wrapper prevents double calls

### D. CHANGELOG.md
Add to the Unreleased section.

## Files Modified
- `src/icloudpd/base.py` (get_password_from_webui + user loop in run_with_configs)
