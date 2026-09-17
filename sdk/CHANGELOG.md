# Changelog — @awaazlabs-uva/voice

All notable changes to the browser SDK. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/).

Releases are cut by pushing a `voice-v<version>` tag that matches `version` in `package.json`
(see `.github/workflows/release-sdk.yml`). Add an entry here in the same PR that bumps the version.

## [Unreleased]

### Fixed
- A single failed token refresh no longer ends the call: refresh retries with backoff
  (single-flight) and applies the refreshed LiveKit token to the live connection (audit F-H12).
- Session and refresh `fetch` calls now time out instead of leaving `connect()` pending forever
  (audit F-M14).
- Importing the SDK at module scope no longer throws during server-side rendering (e.g. Next.js)
  (audit F-L7).
- A listener that throws no longer prevents later listeners from receiving the event (audit F-L8).

### Changed
- Error codes are more specific: rate limits, plan caps and upstream failures are no longer all
  reported as `quota_exceeded` (audit F-M16). See the README's error taxonomy.

### Added
- Unit tests (`npm test`, vitest).
- `CHANGELOG.md` is shipped in the npm package.
- Package metadata now points at `Finova-Solutions/urdu-voice-agent-SDK`.

## Pre-registry builds

- `1.0.1` — hand-delivered tarball in `client-submission_v2/` (commit `68e1643`). Never published
  to npm. `package.json` in this directory still reads `0.1.0`; pick the first registry version
  so it does not go backwards for anyone holding the `1.0.1` tarball.
