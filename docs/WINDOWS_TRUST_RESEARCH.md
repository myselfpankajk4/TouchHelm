# TouchHelm Windows distribution and trust

Research checked against Microsoft documentation on 22 October 2026.
Goal: let testers install TouchHelm without the SmartScreen unrecognized-app
download warning, extra certificate installation, or a separate Python setup.

## Finding

Changing the current EXE installer into an MSI does not establish a trusted
publisher or guarantee removal of SmartScreen warnings. The current Test 3 EXE
was checked with Get-AuthenticodeSignature and reports NotSigned. Its bundled
runtime and installer registration do not provide signing identity.

For this goal, the recommended distribution is an MSIX package submitted to the
Microsoft Store and installed through the Store. Microsoft signs Store MSIX
packages; a locally generated or self-signed MSIX is not an equivalent result.
Submitting a traditional MSI/EXE to the Store follows a different path and still
requires publisher signing.

Sources: [SmartScreen reputation](https://learn.microsoft.com/windows/apps/package-and-deploy/smartscreen-reputation),
[distribution paths](https://learn.microsoft.com/windows/apps/package-and-deploy/choose-distribution-path).

## Alternatives

| Distribution | Effect on the reported warning | Remaining dependency |
| --- | --- | --- |
| Unsigned EXE or MSI from GitHub | Does not establish publisher trust | Each new unsigned version needs its own reputation |
| Publicly signed EXE or MSI | Identifies the publisher; new publishers can still warn | Verified signing identity and reputation |
| Self-signed MSIX | Requires trusting a certificate on each test PC | Conflicts with the requested low-friction setup |
| Store-distributed MSIX | Microsoft signing avoids the SmartScreen download warning | Developer identity, package certification and Store installation |

OV and EV signing do not guarantee immediate SmartScreen reputation. Microsoft's
Artifact Signing service also does not promise immediate reputation. Its current
individual-developer eligibility is limited to the USA and Canada, so it should
not be assumed available to an individual based in India.

Sources: [signing guide and eligibility](https://learn.microsoft.com/windows/msix/package/sign-msix-package-guide),
[signing options](https://learn.microsoft.com/windows/apps/package-and-deploy/code-signing-options).

## TouchHelm compatibility assessment

This is a source review, not a verified Store build or a certification result.

- Keep the existing bundled Python, native libraries and camera models. A
  full-trust packaged desktop application is the candidate; an AppContainer
  conversion would change the assumptions of the input and capture code.
- The installed launcher uses paths relative to its installation directory and
  clears external Python environment variables. The Python bootstrap uses -B,
  which avoids writing bytecode inside a read-only package.
- Configuration and preparation status already live under LocalAppData rather
  than the app directory. Packaged storage redirection, settings migration from
  Test 3, single-instance behavior and removal must be verified explicitly.
- Replace Inno-owned installation preparation and shortcuts with the appropriate
  MSIX lifecycle and Start entry. Review missing-WebView2 handling against Store
  requirements; an existing browser on the build PC does not prove that path.
- Verify LAN listeners/discovery, WebView2, two-way typing, input injection,
  screen/audio streaming, camera subprocesses and tray behavior in the actual
  package. Input to elevated applications remains a separate Windows constraint.
- Measure the resulting download size instead of assuming MSIX is smaller than
  the existing solid-LZMA installer. No feature removals are implied.

Sources: [desktop packaging requirements](https://learn.microsoft.com/windows/msix/desktop/desktop-to-uwp-prepare),
[packaged desktop process behavior](https://learn.microsoft.com/windows/msix/desktop/desktop-to-uwp-behind-the-scenes).

## Account and testing requirements

The owner confirmed that no Store developer account exists yet. Individual
registration is free under Microsoft's current onboarding flow, but the owner
must sign in and complete Microsoft's identity verification directly. No ID
documents, credentials or private signing keys should be added to this repo.

After registration, reserve the app as an MSIX product and obtain these exact
non-secret values from Product management > Product identity:

- Package/Identity/Name
- Package/Identity/Publisher
- Package/Properties/PublisherDisplayName

Sources: [free individual registration](https://blogs.windows.com/windowsdeveloper/2025/09/10/free-developer-registration-for-individual-developers-on-microsoft-store/),
[Store app identity](https://learn.microsoft.com/windows/apps/publish/view-app-identity-details).

The initial Store submission can use a private audience for selected testers.
After a published submission, package flights can deliver later test builds to
known groups. Store certification still applies. Account creation alone does not
make an arbitrary file shared on GitHub Microsoft-signed.

Sources: [private audience](https://blogs.windows.com/windowsdeveloper/2018/03/28/private-audience-a-new-way-to-test-your-apps-and-games-in-production/),
[package flights](https://learn.microsoft.com/windows/apps/publish/package-flights).

Acceptance must use the actual Store-delivered package on a separate Windows
installation with security protections unchanged. Check install, Start entry,
launch, feature behavior, update and uninstall. Store distribution addresses the
reported SmartScreen download warning; unrelated firewall, camera, enterprise
policy or security detections are separate checks.

No new MSI/MSIX was generated or installed during this research. No Windows
protection, trust store, file download-zone metadata or app behavior was changed.
The current Test 3 installer remains unsigned.
