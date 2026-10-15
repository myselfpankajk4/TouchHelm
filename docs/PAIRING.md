# Pairing a phone with TouchHelm

Select local HTTP, local certificate HTTPS or private Tailscale HTTPS in the
desktop connection dropdown. Its setup guide appears beside the QR. Keep the PC
app running. New TouchHelm PINs have four digits; the phone's screen-lock PIN is a
different credential.

## Android: local certificate HTTPS

1. Connect both devices to the same Wi-Fi. On the PC choose **Local Wi-Fi · manual
   certificate HTTPS**, then **Enable HTTPS**. Leave its fingerprint visible.
2. Open the **HTTP phone address** on Android and enter the TouchHelm PIN. In
   **Settings → Secure pairing**, select **Download local public certificate**.
   Find `touchhelm-ca.crt` in Downloads.
3. Compare the phone guide's SHA-256 fingerprint with the PC's. Only trust a CA for
   a PC you own and trust. This download contains a public certificate; TouchHelm
   does not ask you to download private keys.
4. In Android Settings search **Install a certificate**. Pixel commonly uses
   **Security & privacy → More security settings → Encryption & credentials**.
   Some Galaxy versions call the entry **Install from device storage**. Names
   vary by Android version.
5. Choose **CA certificate**, rather than Wi-Fi or VPN/app certificate. Read the
   warning and confirm installation. Unlock with the **phone screen-lock PIN** if
   asked, then choose Downloads → `touchhelm-ca.crt`.
6. Return to the phone guide and select **Continue with local HTTPS**, or scan
   the PC's local HTTPS QR. Enter the **TouchHelm PIN**. Chrome must report a
   secure connection without bypassing a certificate warning.
7. When you stop using this PC, remove only its TouchHelm CA under credential
   settings → **Trusted credentials → User**, or **User credentials**. Do not
   clear all credentials, which can affect unrelated services.

[Google's credential settings](https://support.google.com/pixelphone/answer/2844832)
cover settings and removal. Its Wi-Fi example serves a different purpose;
Android has a separate [CA installation entry](https://android.googlesource.com/platform/packages/apps/Settings/+/07026fd881/res/xml/install_certificate_from_storage.xml).

### iPhone / iPad

Download and open the public certificate in Safari, allow the profile download,
then install the TouchHelm profile in **Settings → General → VPN & Device
Management** (or **Profile Downloaded**). Next enable the matching root in
**Settings → General → About → Certificate Trust Settings**. Compare the PC
fingerprint first. Profile installation alone does not enable SSL trust. Remove
the profile when no longer needed. [Apple's instructions](https://support.apple.com/102390)
explain the separate full-trust step. Physical iOS installation is unverified.

### Troubleshooting

- **File missing:** choose Downloads and the `.crt` file. Never choose a private
  key or unrelated certificate.
- **Installation blocked:** a managed phone may prohibit user CAs. Contact its
  administrator; TouchHelm cannot override device policy.
- **Browser still warns:** check CA installation type, phone date/time and the
  exact current QR address. Restart Chrome after installation. “Proceed anyway”
  does not establish trusted setup.
- **PC address changed:** disable and re-enable local HTTPS to renew the server
  certificate. Use the new QR. If the CA fingerprint changed, remove the old
  TouchHelm CA and install the replacement.

## Private Tailscale HTTPS: no phone CA installation

1. Select **Private Tailscale · trusted HTTPS** on the PC.
2. Click **Set up trusted pairing**. TouchHelm installs missing PC requirements;
   approve the Windows installer if requested.
3. Open Tailscale in the Windows tray, choose **Log in** and finish browser login.
   Leave it connected.
4. Install Tailscale on Android. Sign in with the same account, or an authorised
   account on the same tailnet. Turn its connection on and approve Android's VPN
   prompt.
5. After login click **Set up trusted pairing** again, or use **Check connection →
   Enable private HTTPS**. Follow any HTTPS permission link; a tailnet
   administrator may need to enable HTTPS certificates in the admin console.
6. Scan the new `.ts.net:8443` QR and enter TouchHelm's PIN. Keep Tailscale
   connected on both devices, including when using mobile data.

TouchHelm uses private Serve only: no Funnel, public sharing or port forwarding.
It reports conflicts instead of replacing unrelated Serve endpoints. Tailscale
must run on both devices. HTTPS signaling alone does not guarantee WebRTC media
connectivity.

Official guides: [Windows](https://tailscale.com/docs/install/windows),
[Android](https://tailscale.com/docs/install/android),
[Serve HTTPS](https://tailscale.com/docs/features/tailscale-serve).

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
Disable Two-way PC text to stop reading PC fields. This preference follows secure
origin handoff, while reconnection does not replay drafts.

Return stays multiline and **PC Enter** is explicit. Clear clears the local draft,
not the PC document. IME composition stays local until committed. Field contents
go only to the requesting paired phone; they are not logged or broadcast. No
clipboard polling or global keystroke hook is used.
[Microsoft's UI Automation guidance](https://learn.microsoft.com/en-us/dotnet/framework/ui-automation/add-content-to-a-text-box-using-ui-automation)
describes ValuePattern editing and native input for multiline controls.
