export const meta = {
  slug: 'providers',
  title: 'Providers',
  eyebrow: 'Reference',
  description:
    'STT, LLM, and TTS providers available when AwaazLabs provisions your agents.',
};

export const markdown = `
## How providers are chosen

Agent language and providers are set when your backend creates or updates an agent with \`@awaazlabs-uva/agents\` (or when AwaazLabs provisions for you). This console is **read-only** — use **[Agents](/agents)** to inspect what is configured for your tenant. There is no Providers UI to remap vendors.

Only **enabled** providers below are available for production agents. Stacks are language-specific: English and Urdu are not interchangeable.

**Configured providers stick.** The runtime uses the STT / LLM / TTS providers stored on the agent for both browser (WebRTC) and phone (PSTN) sessions. There is no automatic vendor remap at call start.

## English (\`agent_language: en\`)

| Layer | Providers | Notes |
|-------|-----------|--------|
| **STT** (speech → text) | Gladia, Deepgram | Deepgram default model: \`nova-3\`. Optional Deepgram \`stt_options\`: \`endpointing_ms\`, \`stt_mode\` (\`nova\` \\\| \`flux\`) |
| **LLM** (dialogue) | Gemini, Groq | Gemini default: \`gemini-3.6-flash\`. Groq defaults to \`openai/gpt-oss-20b\` (also \`openai/gpt-oss-120b\`). Choose explicitly — neither is forced at runtime |
| **TTS** (text → speech) | ElevenLabs, Cartesia, Rime | Voice IDs come from the platform voice catalog. Rime is English-only |

English CREATE defaults (when you omit provider fields): Deepgram + Groq + Cartesia. Pass providers explicitly to override.

## Urdu (\`agent_language: ur\`)

| Layer | Providers | Notes |
|-------|-----------|--------|
| **STT** | Gladia | |
| **LLM** | Gemini | Default model: \`gemini-3.6-flash\` |
| **TTS** | Uplift | Urdu voices from the platform catalog |

Urdu currently has a **single provider per layer**. Plan capacity and fallback messaging accordingly if you ship always-on Urdu.

## What is not offered

| Item | Status |
|------|--------|
| Fish Audio TTS | Not offered |
| Soniox STT | Not offered |
| Groq LLM for Urdu | Not available (English only) |
| Alternate Urdu STT / TTS vendors | Not enabled |

## Where to look in the console

| Task | Where |
|------|--------|
| See an agent’s language / providers | [Agents](/agents) |
| Create or change providers | \`@awaazlabs-uva/agents\` on your backend (or ask AwaazLabs to provision) |
| Live call inspection | [Sessions](/sessions) |

Provider availability is enforced by the platform; use [Agents](/agents) to confirm what is configured for your tenant.

## Humanization and mixed language

The existing selectable providers participate in the shared runtime. Provider selection does not automatically enable new delivery or streaming policies; those are platform worker controls. Urdu-English mixed tests use the existing Urdu route, not a new language enum. Gladia's current single-language configuration remains a limitation. Follow [Humanization testing](/docs/humanization-testing) for per-provider listening and activation evidence.
`;
