# TouchHelm living controls — approved implementation plan

Approved 12 October 2026. Preserve five tabs, branding, seven themes, desktop composition, drafts/favorites and latest-source launcher. Android Chrome is primary. This is the user's approved plan, recorded for implementation and review.

## Task 1 — Control repairs

- Presenter: resolve 64px navigation/88px child conflict; reachable controls cannot cover monitor/disclosures. Title/status, full-width monitor selector, four 44px colors, dominant framed laser pad with guides, precise contact indicator and Pointing status. Compact Windows click-through/non-activating per-pixel-alpha cached glow overlay; monitor/DPI correctness; existing cancellation/timer independence.
- Media: shared sampled playback clock drives seek thumb/fill/elapsed/accessibility. Normalize raw Windows Position as of LastUpdatedTime; use monotonic client clock only while Playing; effective 1x when rate absent but metadata unknown. Identical snapshots do not reset; session/item/seek/pause/resume/rate changes re-anchor; clamp bounds. Scrub target, commit once, actual confirmation vs Seeking, five-second failure recovery.
- Artwork: diagnose Windows availability, stream read, normalization, authenticated assets, decoding. Explicit not_provided/available/read_error, cache valid art on identical snapshots, clear changed item. Intentional unavailable placeholder and player identity; no scraped/fabricated thumbnail.
- Apps: Close window only for verified running windows; chooser for multiple. Revalidate app/process/window identity; asynchronous normal close preserving save prompts; requested differs from confirmed disappearance; bounded refresh; no terminate/elevation.
- Live typing defaults true unless explicit device opt-out. Persist; no draft replay on restore/reconnect; preserve IME, multiline Return, dismissal and PC Enter.

## Task 2 — Living themes and desktop finish

- Shared SVG/CSS/Web Animations runtime independent of input.
- Bloom: randomized edge branches/vines/control wraps, varied flowers/leaves; touch bends foliage and attracts petals; press blooms and botanical native-key caps.
- Companion: blink/look/peripheral roam; eyes follow touch; truthful connection/command expressions and robotic native-key/control reactions.
- Resonance: randomized edge notes/instrument motifs; decorative plucked strings and native-key note caps; record moves only with actual playback.
- Clay: sculpted edge forms; control compression/rebound, temporary impressions and clay key caps. Glass/Soft/Ink unchanged.
- Rich/Calm/Off device preference, default Rich, system reduced motion wins. Random scene timing/positions; <=2 idle actors, <=6 touch actors, recycled elements, <=30fps work. Pointer-events none/aria-hidden, never cover labels/focus/QR/PIN/textarea. Suspend idle during pointer/drag/laser/scroll, preserve local lightweight feedback; pause hidden. No textarea content in popups or rapid-key queues.
- Shared desktop pairing/navigation/settings/outcome effects; spacing/disclosure/selected-state/copy-save/long-copy finishing. Expand real-interface simulated preview board for scenes/touch/held/seek/artwork/close/pairing.

## Task 3 — Optional private Tailscale HTTPS

- Desktop setup links Windows/Android installation and sign-in, then private Serve HTTPS and QR; no manual CA for this mode. Loopback backend 127.0.0.1:8767, owned Serve HTTPS8443. Inspect existing config; conflicts cannot overwrite unrelated services. No Funnel. Enable/create existing host PIN before activation.
- Setup privileges only owned native desktop bridge. No phone installer/config or desktop privilege HTTP endpoints. Proxy transport trust only dedicated loopback port + configured host; LAN spoofed headers fail. Origin-derived HTTP/WSS, honest setup/ready/unavailable/permission/reconnect; explicit modes, retain HTTP/local-CA options. Disable only owned endpoint.
- Cross-origin handoff single-use60s, exact target origin and fresh PIN; carry device effects/live preference and synchronization baseline without retransmitting draft.
- Interface additions: app_action close/window_id; media sampled_at/artwork_status; local effects/live preferences; desktop mode/readiness/trustedURL/QR/errors.

## Task 4 — Verification/release

- RED/GREEN original overlap/frozen-clock regressions plus missing rates/repeated timestamps/external seeks/pause/rate/stale sessions/cancelled scrub.
- Thumbnail supplied/missing/read/decode/auth/cache/item-change tests; close single/multi/stale/refusal/save-prompt fixtures with no force kill; live fresh/opt-out/IME/reconnect/handoff no duplicate.
- Effects limits/interruption/reduced/accessibility/no altered native packets.
- Existing viewport matrix/all seven light+dark themes/desktop: one batched inspection, one fix batch, one confirmation.
- Real Android trustedHTTPS/typing/performance; supported live-player clock/artwork and scratch-window close; 30-minute Tailscale WSS stability incl background/source restart. Unperformed device checks must be reported explicitly.
- Update documentation, screenshots/previews and private GitHub; integrate verified source and validate actual latest shortcut.
