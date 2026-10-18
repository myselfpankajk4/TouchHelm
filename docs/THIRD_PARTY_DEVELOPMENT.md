# Development-only accessibility tooling

The AirControl browser audit uses these pinned development dependencies:

| Package | Version | License | Source |
| --- | --- | --- | --- |
| `@axe-core/playwright` | 4.14.0 | MPL-2.0 | https://github.com/dequelabs/axe-core-npm/tree/develop/packages/playwright |
| `axe-core` (transitive, locked) | 4.14.0 | MPL-2.0 | https://github.com/dequelabs/axe-core |

License texts are included in each installed package's LICENSE file. The lockfile
records the exact packages and integrity hashes. These tools run against the
local synthetic browser preview; they are not loaded by the product frontend,
served from the desktop asset server, or installed in the isolated camera
runtime. No upstream source was modified.

Automated accessibility scanning is supplemented by keyboard, focus, reflow,
target-size, reduced-motion, and screenshot checks. A passing scan does not
establish usability for every person or assistive technology.

MediaPipe/OpenCV model and runtime notices remain in the existing AirControl
assets and documentation. Project Gameface, eViacam, and OpenSeeFace were
researched as design/comparison references; no code or models from those
repositories were added by this release.
