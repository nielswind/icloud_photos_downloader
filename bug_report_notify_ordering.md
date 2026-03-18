# Bug: Mail notifier sent after password wait ends when using webui + 2FA

## Summary

When using `--webui` for password input together with 2FA and a mail notifier (SMTP), the
notification email is sent **after** the user has already entered their password through the
web UI — instead of before. This means the alert arrives too late to serve its purpose of
prompting the user to go to the web UI.

## Steps to Reproduce

1. Configure icloudpd with:
   - `--password-provider webui` (or `webui` in the password providers list)
   - `--mfa-provider webui`
   - SMTP mail notifier configured (`--smtp-username`, `--notification-email`, etc.)
2. Start icloudpd. Let the iCloud session expire (or start fresh with no cached session).
3. On the next authentication attempt, observe the sequence of events.

## Expected Behaviour

1. Mail notification sent — alerting the user to visit the web UI
2. Web UI shows password form (`NEED_PASSWORD`)
3. User enters password
4. Web UI shows 2FA code form (`NEED_MFA`)
5. User enters 2FA code

## Actual Behaviour

1. Web UI shows password form (`NEED_PASSWORD`) — **no notification yet**
2. User enters password (status: `CHECKING_PASSWORD`)
3. Status transitions to `NO_INPUT_NEEDED` — password wait ends
4. **Mail notification sent** — too late, user is already past the password stage
5. Web UI shows 2FA code form (`NEED_MFA`)
6. User enters 2FA code

## Root Cause

In `src/icloudpd/authentication.py`, the `authenticator()` function called
`update_password_status_in_webui()` (the "writer") unconditionally **before** calling
`notificator()`:

```python
# OLD (buggy) order
if valid_password:
    for _, _pair in password_providers.items():
        _, writer = _pair
        writer(username, valid_password[0])   # CHECKING_PASSWORD → NO_INPUT_NEEDED  ← (1)

if icloud.requires_2fa:
    notificator()                              # mail sent                             ← (2)
    ...
```

`update_password_status_in_webui()` transitions the status exchange from
`CHECKING_PASSWORD` to `NO_INPUT_NEEDED`, which is the "stop waiting for password" signal.
The `notificator()` (SMTP mail send) ran only after that transition, so the password wait
had already ended before the email was dispatched.

Additionally, the notification email text says _"Please log in to your server and run the
script manually"_, which is incorrect when the web UI is active — the user should be
directed to the web UI instead.

## Fix

Move the `notificator()` call to **before** the writer call so the mail is sent while the
status is still `CHECKING_PASSWORD`, before the "stop waiting" transition occurs. The
password is then saved to providers (keyring, etc.) and the status is cleared **after** the
notification has been dispatched.

```python
# NEW (fixed) order
if icloud.requires_2fa:
    notificator()                              # mail sent first                       ← (1)
    if valid_password:
        for _, _pair in password_providers.items():
            _, writer = _pair
            writer(username, valid_password[0])  # CHECKING_PASSWORD → NO_INPUT_NEEDED ← (2)
    ...
```

The same reordering is applied to the `requires_2sa` branch for consistency.
A new `else` branch preserves the existing behaviour of saving the password when no MFA
is required at all.

## Affected File

`src/icloudpd/authentication.py` — `authenticator()` function, lines ~98–117

## Secondary Issue

The notification email body reads:

> Please log in to your server and run the script manually to update two-step authentication.

When `--mfa-provider webui` is in use, this instruction is wrong. The user should be told
to visit the web UI, not to run the script manually. The email template in
`src/icloudpd/email_notifications.py` could be made context-aware, or a separate
webui-specific message could be used.
