# SDK Packages

This folder contains three installable npm tarballs and their TypeScript source for review.

## Package boundaries

| Package | Import | Where to use it | Secret handling |
| --- | --- | --- | --- |
| Voice SDK | `@awaazlabs-uva/voice` | Browser frontend | Uses only a publishable key and your own session endpoint. |
| Agents SDK | `@awaazlabs-uva/agents` | Backend services only | Signs requests with `UVA_TENANT_ID` and `UVA_HMAC_SECRET`. |
| Telephony SDK | `@awaazlabs-uva/telephony` | Backend services only | Signs requests with `UVA_TENANT_ID` and `UVA_HMAC_SECRET`; Telnyx API keys are accepted only as transient method parameters for connect/rotate calls. |

## Tarballs

```text
@awaazlabs-uva/voice/awaazlabs-uva-voice-1.0.0.tgz
@awaazlabs-uva/agents/awaazlabs-uva-agents-0.1.0.tgz
@awaazlabs-uva/telephony/awaazlabs-uva-telephony-0.1.0.tgz
```

Install the tarballs into your frontend/backend applications. The `src/` folders are included for review; application code should import the packages by package name.

`@awaazlabs-uva/agents` includes `greeting`, `firstSpeaker`, and English `ttsProvider` values `cartesia` and `rime`. Spoken humanization runs on the hosted worker, not in these packages.

For the full callable SDK surface, see `../docs/SDK_CAPABILITIES_REFERENCE.md`.

## Runtime requirements

- Node.js 20 or newer is recommended for all backend SDK usage.
- Modern browser support is required for the voice SDK because it uses WebRTC through LiveKit.
- Backend secrets must never be included in browser bundles, mobile apps, client-side logs, or analytics payloads.

## Validation after install

After installing a package, verify imports from your application build:

```ts
import { AwaazLabsUvaVoice } from '@awaazlabs-uva/voice';
import { AwaazLabsUvaAgentsClient } from '@awaazlabs-uva/agents';
import { TelephonyClient } from '@awaazlabs-uva/telephony';
```
