# 2FA Code Not Appearing on Apple Devices (2026+)

## Summary

Starting with iOS 26.4, Apple devices stop receiving the push notification that delivers a
two-factor authentication (2FA) code when icloudpd requests one. The code input prompt
appears in icloudpd, but nothing arrives on the iPhone or iPad. This document explains
why, what was fixed, and how to work around the issue on older versions.

---

## Root Causes

### 1. Missing push trigger (primary cause)

Apple's authentication API now requires a dedicated `PUT` request to initiate code delivery
to trusted devices:

```
PUT https://idmsa.apple.com/appleauth/auth/verify/trusteddevice/securitycode
```

This request has no body. It tells Apple's servers to push a 6-digit code to all trusted
devices associated with the account.

Prior to the fix, icloudpd never made this call. It only used a `POST` to the same endpoint
to *validate* a code the user had already entered — but it never asked Apple to *send* one.
The device therefore received no notification and displayed nothing.

### 2. SMS fallback silently broken (secondary cause)

Apple moved the `trustedPhoneNumbers` field in the HTML auth payload to a new location:

| Version | JSON path |
|---|---|
| Before 2026 | `direct.twoSV.phoneNumberVerification.trustedPhoneNumbers` |
| 2026+ | `direct.twoSV.bridgeInitiateData.phoneNumberVerification.trustedPhoneNumbers` |

The parser in `pyicloud_ipd/sms.py` only looked at the old path, found an empty list, and
silently dropped the SMS fallback option. Users who would normally be offered "send code via
SMS to +•••-••81" no longer saw that option.

### 3. iOS 26.4 removed manual code generation

In older iOS versions, users could open Settings → Apple ID → Sign-In & Security and tap
**"Get Verification Code"** to generate a code themselves without needing a push notification.
iOS 26.4 removed this button from the UI. It only reappears when the device has no internet
connection (airplane mode with Wi-Fi also disabled).

---

## The Fix

Three files were changed (mirroring the approach validated in community PR #1335):

### `src/pyicloud_ipd/base.py` — new `trigger_push_notification()` method

```python
def trigger_push_notification(self) -> bool:
    """Triggers a push notification to trusted devices for 2FA code entry."""
    # PUT with no body to /verify/trusteddevice/securitycode
    # Returns True on success, False if Apple rejects the request.
```

Sends the `PUT` request Apple now requires before a code will be pushed to devices.

### `src/icloudpd/authentication.py` — call trigger before prompting

```python
def request_2fa(icloud, logger):
    if not icloud.trigger_push_notification():
        logger.debug("Failed to trigger 2FA push notification, continuing anyway")
    else:
        logger.debug("2FA push notification triggered")
    devices = icloud.get_trusted_phone_numbers()
    ...
```

The trigger call is made before the user is prompted for a code. Failure is non-fatal —
if Apple rejects the `PUT` (e.g. session state is unexpected), icloudpd continues and the
user can still type a code if one arrives by another means.

### `src/pyicloud_ipd/sms.py` — fallback to new `bridgeInitiateData` path

```python
twoSV = parser.sms_data.get("direct", {}).get("twoSV", {})
numbers = twoSV.get("phoneNumberVerification", {}).get("trustedPhoneNumbers", [])
if not numbers:
    # Apple moved trustedPhoneNumbers into bridgeInitiateData.phoneNumberVerification (2026+)
    numbers = (
        twoSV.get("bridgeInitiateData", {})
        .get("phoneNumberVerification", {})
        .get("trustedPhoneNumbers", [])
    )
```

Checks the old path first for backwards compatibility, then falls back to the new path.
This restores the SMS option for users whose account has trusted phone numbers.

---

## Workarounds (for older versions without the fix)

### Option A — Airplane mode trick

1. On the iPhone/iPad, enable **Airplane Mode** and also turn **Wi-Fi off manually**
   (Airplane Mode alone is not enough on newer iOS versions)
2. Go to **Settings → [your name] → Sign-In & Security**
3. Tap **"Get Verification Code"** — the button reappears when the device has no internet
4. Enter the displayed code in icloudpd

### Option B — Trigger via iCloud.com

1. Open a browser and start signing in at [icloud.com](https://www.icloud.com)
   (do not complete the sign-in — just get far enough to trigger 2FA)
2. Apple pushes the code to your trusted devices as part of the browser sign-in flow
3. Enter the code in icloudpd (codes are not session-specific)

### Option C — Use SMS if available

If icloudpd presents a list of trusted phone numbers, choose one to receive the code via
SMS instead of a device push. This path is unaffected by the push trigger issue.

---

## Affected Versions

- **Broken**: any version of icloudpd before this fix running against iOS 26.4+ devices
- **Fixed**: this commit and later
- **Apple-side change**: iOS 26.4 (also affects iPadOS 26.4)
