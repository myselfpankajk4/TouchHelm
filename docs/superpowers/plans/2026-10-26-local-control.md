# Local encrypted browser control implementation plan

**Goal:** Keep every PC control, PIN, text snapshot, setting and artwork transfer
off the public relay; require a directly connected local peer and end the public
tunnel after pairing. User already accepts internet during initial pairing.

**Architecture / design:** The temporary HTTPS origin serves static phone assets
and bounded SDP pairing only. PC creates a host-only WebRTC offer; its certificate
fingerprint and a 256-bit secret travel in the desktop QR fragment. HMAC proofs
bind the nonce and exact answer SDP without transmitting the QR secret. The phone
checks the PC fingerprint before accepting the offer. No STUN, TURN or automatic
relay fallback. Validate the nominated remote address against local adapter
subnets before accepting any channel messages, and monitor it thereafter.

An ordered DTLS DataChannel carries the existing validated PIN/input protocol.
A bounded socket adapter preserves existing revocation/input cleanup; narrow RPC
on the same authenticated channel replaces HTTP settings/artwork. The temporary
helper stops once the direct channel opens; local peer lifetime is independent.
Stop, expiry, failed peer checks and loss of local connectivity close the peer
and release held input. A new scan is needed after reloading a closed origin.
Cached theme text/blob URLs keep the already loaded UI usable after shutdown.

**Trust limits:** This removes ongoing public control reachability and readable
relay traffic. Browser/PC and initially delivered page code still need to be
trusted; it does not claim immunity to a compromised device or hosting provider.

**Tech stack:** Existing aiohttp, aiortc 1.15.0/aioice, browser WebRTC/WebCrypto.
The small version-bound selected-ICE-pair adapter must fail closed if unavailable.

- [ ] RED: deny all former public control/API routes; authenticate bound SDP,
  reject tampered proofs/fingerprints/nonlocal peers and cap buffers.
- [ ] Implement server/local_link.py and bounded data-channel socket adapter;
  share the existing client command loop without bypassing its PIN/capability gates.
- [ ] Replace public gateway with static/challenge/offer/answer only; automatically
  stop the helper after local connection, preserving direct session cleanup.
- [ ] Implement phone handshake/socket/RPC, preload theme assets, remove HTTP/API
  and public WebSocket fallback. Update desktop local/paired/recovery status.
- [ ] Verify real Chrome/direct aiortc with a synthetic native host: kill the
  public helper, prove PIN/ping/settings/artwork/typed packets remain local;
  negative tests must reject remote routes, wrong proofs and nonlocal pairs.
- [ ] Run affected/full regressions; review, build once from final sources,
  update installed copy preserving settings, publish the private test build.
