# Changelog — @awaazlabs-uva/telephony

All notable changes to the backend telephony SDK. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

Releases are cut by pushing a `telephony-v<version>` tag that matches `version` in
`package.json` (see `.github/workflows/release-sdk.yml`). Add an entry here in the same PR that
bumps the version.

## [Unreleased]

### Fixed
- `getSessionByRoom()` now works. Every call threw `telephony_invalid_response` without sending a
  request, because the internal path guard still required a `/machine/telephony/` prefix while
  this operation targets `/machine/sessions/get`. The guard now requires the `/machine/` surface,
  which is what it was protecting.

### Added
- Contract coverage for `getSessionByRoom`, a check that every exported operation has a frozen
  contract case, and a regression test that a path parameter cannot escape the `/machine/`
  surface.
- `CHANGELOG.md` is shipped in the npm package.
- A release path: `telephony-v*` tags publish this package with npm provenance (audit F-M21 —
  previously only `@awaazlabs-uva/voice` had any release workflow).

### Changed
- Package metadata now points at `Finova-Solutions/urdu-voice-agent-SDK` instead of a personal
  repository (audit F-M23).

## [0.1.0]

- Initial package: Telnyx connection management, number search/reservation/purchase/import,
  routing and SIP/outbound-trunk configuration, outbound calls, and call records — all over the
  HMAC-signed `/machine/` API. Delivered as a tarball; not yet published to npm.
