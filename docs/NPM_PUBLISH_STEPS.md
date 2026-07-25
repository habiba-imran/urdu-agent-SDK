# NPM Publish Steps

> Internal Finova reference — how to publish `@awaazlabs-uva/voice` and `@awaazlabs-uva/agents` to the npm registry.

---

## The Big Picture

npm is a central server where you upload a folder of code. Anyone who knows the package name can then `npm install` it. You need **one account**, **one command to build**, and **one command to publish**.

---

## Step 1 — Create an npm Account

Go to [npmjs.com](https://www.npmjs.com) → Sign Up.

Pick an **organisation name** (called a "scope" in npm). Since the packages are named `@awaazlabs-uva/voice` and `@awaazlabs-uva/agents`, the scope is `@awaazlabs-uva`. Create an organisation called `awaazlabs-uva` on npm.

```
npmjs.com/org/awaazlabs-uva   ← this needs to exist before publishing
```

Then on your machine, log in once:

```bash
npm login
# Opens a browser — sign in, done.
```

---

## Step 2 - Verify `package.json` publishing fields

Both packages must have the correct AwaazLabs-UVA package names and public publish configuration before publishing.

```json
// Browser SDK
{
  "name": "@awaazlabs-uva/voice",
  "publishConfig": {
    "access": "public"
  }
}

// Server SDK
{
  "name": "@awaazlabs-uva/agents",
  "publishConfig": {
    "access": "public"
  }
}
```

Neither package should include `"private": true` in the publishable repository package.

---

## Step 3 — Control What Gets Uploaded (`"files"` field)

Only files listed in the `"files"` field of `package.json` are uploaded to npm. Both packages should keep this narrow:

```json
"files": [
  "dist",
  "README.md"
]
```

Keep this in both publishable package manifests. This ensures npm uploads only the compiled `dist/` output and the README - **not** `src/`, `node_modules/`, or anything else.

---

## Step 4 — Build the Package

The `dist/` folder must be up-to-date before publishing. Run the TypeScript compiler inside each package folder:

```bash
# Browser SDK
cd sdk
npm run build        # runs tsc → outputs compiled JS to dist/

# Server SDK
cd ../sdk-server
npm run build
```

npm ships whatever is currently in the folder — always build first.

---

## Step 5 — Publish

Run from inside each package folder:

```bash
# Browser SDK
cd sdk
npm publish

# Server SDK
cd ../sdk-server
npm publish
```

npm will:
1. Read `package.json` to get the name and version
2. Bundle only the files listed in `"files"`
3. Upload to the registry
4. Make it available instantly at `npmjs.com/package/@awaazlabs-uva/voice`

---

## Step 6 — What the Client Does After Publishing

Once published, the client no longer needs the `sdk/` folder in the delivery package. They simply run:

```bash
# In their frontend project
npm install @awaazlabs-uva/voice livekit-client@^2.0.0

# In their backend project (server-side only)
npm install @awaazlabs-uva/agents
```

The `docs/` folder (INTEGRATION_GUIDE, ai-integration-guide, credentials-template) is still delivered — just without the `sdk/` folder alongside it.

---

## Step 7 — Releasing Updates (Versioning)

Every time the SDK changes and an update needs to go out, bump the version number first:

```bash
# Inside the package folder
npm version patch   # 1.0.0 → 1.0.1  (bug fix)
npm version minor   # 1.0.0 → 1.1.0  (new feature, backward compatible)
npm version major   # 1.0.0 → 2.0.0  (breaking change)

npm publish
```

Clients who run `npm update` will receive the new version automatically within their pinned semver range.

---

## Public vs Private Registry Options

| Option | Who Can Install | Cost |
|---|---|---|
| **Public npm** (`npmjs.com`) | Anyone with npm | Free |
| **Private npm** (npm paid tier) | Only authorised users | ~$7/mo per user |
| **GitHub Packages** | GitHub users you authorise | Free for public repos |
| **Self-hosted** (Verdaccio, JFrog) | Internal network only | Hosting cost only |

For `@awaazlabs-uva/voice` (zero secrets) — **public npm is perfectly fine.**
For `@awaazlabs-uva/agents` — also safe to publish publicly. The package holds no hardcoded Finova secrets; clients supply their own credentials via `.env` at runtime.

---

## Full Command Sequence at a Glance

```bash
# One-time setup
npm login

# Every release (run inside each package folder)
npm run build
npm version patch        # or minor / major
npm publish

# Client installs (after publishing)
npm install @awaazlabs-uva/voice
npm install @awaazlabs-uva/agents
```

---

## Current State of These Packages

| Package | `private` flag | `publishConfig` | Status |
|---|---|---|---|
| `@awaazlabs-uva/voice` | Not set | `"access": "public"` | Ready to publish after build |
| `@awaazlabs-uva/agents` | Not set | `"access": "public"` | Ready to publish after build |
