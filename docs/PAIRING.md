# Pairing and text sync

## Pairing

TouchHelm pairs over the local Wi-Fi with plain HTTP and a host PIN. Open TouchHelm on the
PC, choose **Pair your phone**, scan the QR code and enter the four-digit PIN. There is no
certificate to install, no VPN and no internet service. Wrong PINs back off; changing or
enabling the PIN revokes every paired phone and releases held input. If the phone cannot reach
the PC, check the private-network Windows Firewall prompt and that the Wi-Fi is not a guest
network with client isolation. See [Local Wi-Fi and Files](LOCAL_WIFI.md).

## Trackpad text in both directions

Enable a host PIN, then keep **Live typing** and **Two-way PC text** checked.
Focus an editable field on the PC. While Trackpad is visible, supported fields
update the phone about once a second. Phone edits check the field identity and
revision. Concurrent PC edits preserve the phone draft; **Use PC text** explicitly
replaces that draft and relinks the current field.

Windows accessibility must expose editable content. Password, read-only,
unsupported and fields longer than 10,000 characters are excluded. Some apps and
elevated windows cannot be controlled. Native typing remains available when no
field was linked. Losing a linked field pauses edits to protect other apps.
Disable Two-way PC text to stop reading PC fields. Reconnection does not replay drafts.

Return stays multiline and **PC Enter** is explicit. Clear clears the local draft,
not the PC document. IME composition stays local until committed. Field contents
go only to the requesting paired phone; they are not logged or broadcast. No
clipboard polling or global keystroke hook is used.
[Microsoft's UI Automation guidance](https://learn.microsoft.com/en-us/dotnet/framework/ui-automation/add-content-to-a-text-box-using-ui-automation)
describes ValuePattern editing and native input for multiline controls.
