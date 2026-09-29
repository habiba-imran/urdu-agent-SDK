# First npm publish — click-by-click guide (all 3 packages)

**Who this is for:** you, with **zero** npm experience.  
**Goal:** put these three packages on public npm so anyone can run:

```powershell
npm install @awaazlabs-uva/voice
npm install @awaazlabs-uva/agents
npm install @awaazlabs-uva/telephony
```

**How to use this file**

1. Do **one step at a time**, top to bottom.
2. Every step has: **where to click**, **exact link**, **what to type**, **what success looks like**.
3. At each **CHECKPOINT**, copy the PowerShell output (or take a screenshot) and **paste it into Cursor chat**. Wait for **PASS** before continuing.
4. Do **not** skip ahead to tagging until Checkpoints A–D pass.

**Already done for you (as of this rewrite)**

- Finova `staging` and `main` already contain Wave 1 + telephony packaging code.  
  → You can treat **Checkpoint C as DONE** unless someone rewrites Finova history. Re-check with the commands in §4 if unsure.

---

## 0. What you are doing (read once)

| Thing | Meaning |
|--------|---------|
| Code on GitHub | Engineers can see it. Clients **cannot** `npm install` it. |
| Package on npm | Clients **can** `npm install @awaazlabs-uva/...`. **This is the real delivery bar.** |
| Local `.tgz` files | Hand delivery / demo only. **Not** npm. |

You will:

1. Create an npm **organisation** named `awaazlabs-uva` (like a company folder on npm).
2. Create an npm **token** (a password for machines).
3. Put that token in **Finova GitHub** so Actions can publish.
4. Bump versions + CHANGELOG in a PR (small code change).
5. Push **git tags** on Finova → GitHub Actions publishes for you.

You will **not** run `npm publish` from your laptop for the real release.

---

## Before you start — accounts you need

Open these and stay signed in:

| Account | Link | Why |
|---------|------|-----|
| npm | https://www.npmjs.com/login | Create org + token |
| GitHub (your user) | https://github.com/login | Push tags / open PRs |
| Finova repo | https://github.com/Finova-Solutions/urdu-voice-agent-SDK | Where publish runs |

**Also install Node/npm on your PC** (if you don’t have it):

1. Open https://nodejs.org/
2. Download the **LTS** Windows installer.
3. Install with default options.
4. Close and reopen PowerShell, then run:

```powershell
node -v
npm -v
```

You should see version numbers (e.g. `v22.x.x` and `10.x.x`). If not, Node is not installed correctly — fix that before anything else.

---

## STEP 1 — Create an npm account (skip if you already have one)

### 1.1 Open signup

**Link:** https://www.npmjs.com/signup

### 1.2 Fill the form

- Username (pick one; remember it)
- Email
- Password

Click **Create an Account** (or **Sign up**).

### 1.3 Verify email

1. Open your email inbox.
2. Find the npm verification email.
3. Click the verify link.

### 1.4 Sign in

**Link:** https://www.npmjs.com/login

Sign in with that username/password.

### 1.5 Log npm into your PC (PowerShell)

Open **PowerShell** (Windows key → type `PowerShell` → Enter).

Run:

```powershell
npm login
```

What happens:

1. It may open a browser, **or** ask you to press Enter and visit a URL.
2. Follow the on-screen prompts until it says you are logged in.

Then run:

```powershell
npm whoami
```

**Success:** prints your npm username (one word).  
**Fail:** `ENEEDAUTH` / not logged in → repeat `npm login`.

---

## STEP 2 — Create the organisation `awaazlabs-uva`

This is required. Package names start with `@awaazlabs-uva/…`. That only works if this org exists.

### 2.1 Open the create-org page

**Exact link:** https://www.npmjs.com/org/create

If that redirects weirdly:

1. Go to https://www.npmjs.com/
2. Click your **avatar / profile icon** (top-right).
3. Look for **Add Organization** or **Organizations** → create.

### 2.2 Fill the form

| Field | What to enter |
|-------|----------------|
| Organization name | `awaazlabs-uva` **exactly** (lowercase, with hyphens) |
| Plan | Choose the **free** plan for **public** packages (wording may be “Unlimited public packages” / “Free”) |

Click the primary button: **Create Organization** / **Create** / **Continue**.

### 2.3 Confirm you landed on the org page

After create, you should land on something like:

**https://www.npmjs.com/settings/awaazlabs-uva/packages**  
or  
**https://www.npmjs.com/org/awaazlabs-uva**

You should see the org name **awaazlabs-uva** in the page header.

### 2.4 (Optional but good) Invite Ehsan later

You can invite teammates from:

**https://www.npmjs.com/settings/awaazlabs-uva/members**

Not required to publish today if **you** are the owner and will create the token.

---

### CHECKPOINT A — paste into Cursor

In PowerShell (use **these** commands — the old `/-/org/...` URL often false-fails):

```powershell
npm whoami
npm org ls awaazlabs-uva
```

**PASS looks like:**

```text
habibaimran
habibaimran - owner
```

(Your username on both lines; second line must say `owner` or `admin` / member for org `awaazlabs-uva`.)

Also fine in the browser: https://www.npmjs.com/settings/awaazlabs-uva/packages shows **0 packages** and org name `awaazlabs-uva` — that means the org exists and is empty (expected before publish).

**FAIL looks like:**

| Output | Meaning | Fix |
|--------|---------|-----|
| `ENEEDAUTH` | Not logged in on PC | `npm login` again |
| `npm error` / not found / not a member | Org missing or wrong name | Redo Step 2; name must be exactly `awaazlabs-uva` |
| Name already taken | Someone else owns it | Stop and message the team — do not invent a different org name |

**Ignore** this false alarm (unauthenticated registry URL):

```text
ResourceNotFound ... /-/org/awaazlabs-uva does not exist
```

If `npm org ls awaazlabs-uva` shows you as owner, the org is fine.

**Stop here until Cursor says PASS.**

---

## STEP 3 — Create an npm access token (password for GitHub Actions)

Do **not** put your npm login password into GitHub. Use a **token**.

### 3.1 Open Access Tokens

**Exact link:** https://www.npmjs.com/settings/~/tokens

Alternate path if the link fails:

1. https://www.npmjs.com/
2. Click **avatar** (top-right)
3. Click **Access Tokens**

### 3.2 Start creating a token

Click the button:

**Generate New Token**

If it asks Classic vs Granular, prefer **Granular Access Token**.

### 3.3 Fill Granular token settings (recommended)

Use these settings (npm UI labels change slightly; match the meaning):

| Setting | Choose |
|---------|--------|
| Token name | `finova-github-actions-publish` (any clear name) |
| Expiration | `90 days` or `No expiration` (team preference; 90 days is safer) |
| Packages | **Read and write** |
| Organizations / Packages allowed | Include org **`awaazlabs-uva`** / allow publishing packages under that scope |
| Bypass 2FA / Automation | If you see a toggle for **Automation** or bypassing 2FA for CI, **enable it** (GitHub Actions cannot click your 2FA phone) |

Then click **Generate Token** / **Generate**.

### 3.4 If you only see Classic tokens

1. Choose **Automation** (not “Publish” publish+2FA, not “Read-only”).
2. Generate.
3. Copy the token.

### 3.5 Copy the token immediately

npm shows the token **once** (starts with `npm_`…).

1. Click **Copy**.
2. Paste it into a password manager or a temporary Notepad window.
3. Do **not** commit it to git. Do **not** paste it into a public chat / PR.

If you lose it, delete the old token and generate a new one.

---

## STEP 4 — Put the token on Finova GitHub as `NPM_TOKEN`

Publish runs on **Finova**, not on your personal fork. The secret must live on Finova.

### 4.1 Open Finova Actions secrets

**Exact link:**  
https://github.com/Finova-Solutions/urdu-voice-agent-SDK/settings/secrets/actions

What you should see:

- Page title like **Actions secrets and variables**
- A button **New repository secret**

### 4.2 If GitHub says “404” or “You don’t have access”

You can read the repo but cannot open Settings.

**What to do:**

1. Send Ehsan (or a Finova admin) this message:

> Please add a repository secret on  
> `Finova-Solutions/urdu-voice-agent-SDK` → Settings → Secrets and variables → Actions  
> Name: `NPM_TOKEN`  
> Value: *(paste the npm token privately, e.g. 1:1 / password manager)*

2. Do **not** put the token on `habiba-imran/urdu-agent-SDK` for the real publish — wrong repo for provenance.

3. Still complete Checkpoint B once they confirm the secret exists.

### 4.3 Create the secret (if you have access)

1. Click **New repository secret**.
2. **Name** field — type exactly:

```text
NPM_TOKEN
```

(all caps, underscore, no spaces)

3. **Secret** field — paste the npm token you copied.
4. Click **Add secret**.

### 4.4 Confirm it appears in the list

On the same page you should see a row:

| Name | Updated |
|------|---------|
| `NPM_TOKEN` | just now |

You will **not** be able to view the value again. That is normal.

---

### CHECKPOINT B — paste into Cursor

You cannot print the GitHub secret (good). Paste **one** of these:

**Option 1 — screenshot** of Finova secrets list showing `NPM_TOKEN` (blur nothing critical; the name alone is fine).

**Option 2 — text confirmation**

```text
I opened:
https://github.com/Finova-Solutions/urdu-voice-agent-SDK/settings/secrets/actions
I see a secret named exactly: NPM_TOKEN
```

Also run locally (proves your npm login still works; does **not** prove the GitHub secret):

```powershell
npm whoami
```

**PASS:** secret name exact + you can open Finova secrets page (or admin confirmed).  
**FAIL:** secret on fork only / wrong name (`npm_token`, `NPM_TOKENS`, etc.) / no access and no admin help yet.

**Stop here until Cursor says PASS.**

---

## STEP 5 — Confirm Finova `main` has the code (Checkpoint C)

This was already pushed for you. Still **verify** once so you know tags will hit the right commit.

### 5.1 Optional: look in the browser

- Staging commits: https://github.com/Finova-Solutions/urdu-voice-agent-SDK/commits/staging  
- Main commits: https://github.com/Finova-Solutions/urdu-voice-agent-SDK/commits/main  

Near the top of **main** you should see a merge that includes recent Habiba / Ehsan work (latency, demo-app, telephony packaging), not only old Hamza merges.

### 5.2 Verify in PowerShell (from this repo folder)

```powershell
cd C:\Users\habiba\Desktop\SDK\sdk-agent
git fetch org
git log org/main --oneline -8
git log org/staging --oneline -5
```

---

### CHECKPOINT C — paste into Cursor

Paste the output of the commands above.

**PASS:** `org/main` includes recent tips like telephony packaging / Wave 1 merges (e.g. PR #24 era commits).  
**FAIL:** `org/main` looks years/months behind your fork `staging` → stop; ask Cursor to re-sync before tagging.

---

## STEP 6 — Version bump + CHANGELOG (small PR)

GitHub Actions refuses to publish unless:

1. `package.json` `"version"` matches the tag, **and**
2. That package’s `CHANGELOG.md` has a heading exactly like `## [1.1.0]`

### 6.1 Decide versions (write them down)

| Package | Folder | Recommended first npm version |
|---------|--------|-------------------------------|
| `@awaazlabs-uva/voice` | `sdk/` | **1.1.0** |
| `@awaazlabs-uva/agents` | `sdk-server/` | **0.1.0** (already set) |
| `@awaazlabs-uva/telephony` | `telephony/` | **0.1.0** (already set) |

Why voice `1.1.0`: a `1.0.1` tarball was already hand-delivered. Publishing `0.1.0` as the first public release confuses clients.

### 6.2 Create a branch on your machine

PowerShell:

```powershell
cd C:\Users\habiba\Desktop\SDK\sdk-agent
git fetch org
git checkout -B release/first-npm-publish org/main
```

### 6.3 Edit `sdk/package.json` (voice version)

1. Open file: `sdk/package.json` in Cursor.
2. Find the line near the top:

```json
"version": "0.1.0",
```

3. Change it to:

```json
"version": "1.1.0",
```

4. Save.

Leave `sdk-server/package.json` and `telephony/package.json` at `0.1.0` unless the team chose different numbers.

### 6.4 Edit CHANGELOGs (exact heading format)

Open each file and make sure there is a section heading with **square brackets**.

#### Voice — `sdk/CHANGELOG.md`

Top of file should look like:

```markdown
## [Unreleased]

## [1.1.0]

- First public npm release of @awaazlabs-uva/voice (Wave 1 browser SDK).
- Includes latency / humanization / demo-app packaging work merged to Finova main.
```

If you already have bullet notes under `## [Unreleased]`, move those bullets under `## [1.1.0]`, and leave `## [Unreleased]` empty above it.

#### Agents — `sdk-server/CHANGELOG.md`

```markdown
## [Unreleased]

## [0.1.0]

- First public npm release of @awaazlabs-uva/agents.
```

#### Telephony — `telephony/CHANGELOG.md`

```markdown
## [Unreleased]

## [0.1.0]

- First public npm release of @awaazlabs-uva/telephony.
```

**Wrong headings (will fail Actions):**

```markdown
## Unreleased
## 1.1.0
## v1.1.0
### 1.1.0
```

**Right:**

```markdown
## [1.1.0]
```

### 6.5 Commit on the branch

```powershell
git add sdk/package.json sdk/CHANGELOG.md sdk-server/CHANGELOG.md telephony/CHANGELOG.md
git status
git commit -m "Prepare first npm publish versions for voice, agents, telephony."
```

(If agents/telephony CHANGELOGs already have `## [0.1.0]`, you may only need the voice files — that’s fine.)

### 6.6 Push the branch to Finova

```powershell
git push -u org HEAD:release/first-npm-publish
```

### 6.7 Open a Pull Request on Finova (browser)

**Easiest link (pre-filled compare):**  
https://github.com/Finova-Solutions/urdu-voice-agent-SDK/compare/main...release/first-npm-publish?expand=1

If that 404s because the branch is only on your fork, push to your fork instead and open a PR into Finova `main` — or ask Cursor to help push.

On the compare page:

1. **Base** branch: `main`
2. **Compare** branch: `release/first-npm-publish`
3. Click **Create pull request**
4. Title example: `Prepare first npm publish (voice 1.1.0, agents/telephony 0.1.0)`
5. Click **Create pull request** again
6. Wait for CI checks to go green
7. Click **Merge pull request** → **Confirm merge**

### 6.8 Pull the merged main locally

```powershell
git fetch org
git checkout main
git pull org main
```

---

### CHECKPOINT D — paste into Cursor

```powershell
cd C:\Users\habiba\Desktop\SDK\sdk-agent
git fetch org
git checkout main
git pull org main
Select-String -Path sdk/package.json -Pattern '"version"'
Select-String -Path sdk-server/package.json -Pattern '"version"'
Select-String -Path telephony/package.json -Pattern '"version"'
Select-String -Path sdk/CHANGELOG.md -Pattern '^## \['
Select-String -Path sdk-server/CHANGELOG.md -Pattern '^## \['
Select-String -Path telephony/CHANGELOG.md -Pattern '^## \['
```

**PASS example:**

- voice version `1.1.0`
- agents version `0.1.0`
- telephony version `0.1.0`
- CHANGELOG lines include `## [1.1.0]` and `## [0.1.0]` as expected

**Stop here until Cursor says PASS.**

---

## STEP 7 — Optional dry-run (recommended, safe)

This runs the same checks as a real publish but **does not upload** to npm.

### 7.1 Open Actions on Finova

**Exact link:**  
https://github.com/Finova-Solutions/urdu-voice-agent-SDK/actions/workflows/release-sdk.yml

### 7.2 Run the workflow

1. On the right side, click **Run workflow**
2. Branch dropdown: choose **`main`**
3. Package dropdown: choose **`voice`**
4. Click green **Run workflow**

### 7.3 Watch the run

1. Refresh the page after a few seconds.
2. Click the newest run.
3. Wait until the job is **green** (success) or **red** (failure).
4. If red, open the failed step log, copy the error, paste into Cursor.

### 7.4 Repeat for the other packages

Do the same **Run workflow** twice more:

- Package: **`agents`**
- Package: **`telephony`**

All three should be green.

---

### CHECKPOINT E — paste into Cursor

Paste links to the three successful runs, for example:

```text
voice dry-run: https://github.com/Finova-Solutions/urdu-voice-agent-SDK/actions/runs/XXXXXXXX
agents dry-run: https://github.com/Finova-Solutions/urdu-voice-agent-SDK/actions/runs/YYYYYYYY
telephony dry-run: https://github.com/Finova-Solutions/urdu-voice-agent-SDK/actions/runs/ZZZZZZZZ
```

**PASS:** all three green.  
**FAIL:** any red → fix the error before tagging (Cursor can help from the log).

---

## STEP 8 — Real publish (push tags on Finova)

Do **one package at a time**. Wait for Actions to finish before the next tag.

### 8.1 Make sure you are on the release commit

```powershell
cd C:\Users\habiba\Desktop\SDK\sdk-agent
git fetch org
git checkout main
git pull org main
Select-String -Path sdk/package.json -Pattern '"version"'
Select-String -Path sdk-server/package.json -Pattern '"version"'
Select-String -Path telephony/package.json -Pattern '"version"'
```

Confirm versions still match what you decided (e.g. voice `1.1.0`, others `0.1.0`).

### 8.2 Publish voice

```powershell
git tag voice-v1.1.0
git push org voice-v1.1.0
```

Then open:

https://github.com/Finova-Solutions/urdu-voice-agent-SDK/actions

Click the new **Release SDK** run for tag `voice-v1.1.0`. Wait until green.

In the log you should see a step like **Publish to npm (with provenance)** succeed.

### 8.3 Verify voice on npm (before next tag)

```powershell
npm view @awaazlabs-uva/voice version
```

**PASS:** prints `1.1.0`  
**FAIL:** 404 → open the Actions log; do not continue.

Also open in browser:  
https://www.npmjs.com/package/@awaazlabs-uva/voice

### 8.4 Publish agents

```powershell
git tag agents-v0.1.0
git push org agents-v0.1.0
```

Watch Actions until green, then:

```powershell
npm view @awaazlabs-uva/agents version
```

Browser: https://www.npmjs.com/package/@awaazlabs-uva/agents

### 8.5 Publish telephony

```powershell
git tag telephony-v0.1.0
git push org telephony-v0.1.0
```

Watch Actions until green, then:

```powershell
npm view @awaazlabs-uva/telephony version
```

Browser: https://www.npmjs.com/package/@awaazlabs-uva/telephony

### Tag rules (do not break these)

| Rule | Example |
|------|---------|
| Tag version = package.json version | `voice-v1.1.0` ↔ `"version": "1.1.0"` |
| Prefix selects package | `voice-v…` / `agents-v…` / `telephony-v…` |
| Never reuse a version already on npm | If you typo’d, bump version + new CHANGELOG section + new tag |
| Tag on Finova (`org`), not only your fork | `git push org …` |

---

### CHECKPOINT F — paste into Cursor (after all three)

```powershell
npm view @awaazlabs-uva/voice name version time
npm view @awaazlabs-uva/agents name version time
npm view @awaazlabs-uva/telephony name version time
```

**PASS:** all three print name + version + publish time (not 404).

---

## STEP 9 — Final install proof (this is the real “done”)

### 9.1 Install into a clean temp folder

```powershell
mkdir $env:TEMP\uva-npm-smoke
cd $env:TEMP\uva-npm-smoke
npm init -y
npm install @awaazlabs-uva/voice @awaazlabs-uva/agents @awaazlabs-uva/telephony
```

### 9.2 Prove what got installed

```powershell
npm ls @awaazlabs-uva/voice @awaazlabs-uva/agents @awaazlabs-uva/telephony
Select-String -Path node_modules\@awaazlabs-uva\voice\package.json -Pattern '"version"'
Select-String -Path node_modules\@awaazlabs-uva\agents\package.json -Pattern '"version"'
Select-String -Path node_modules\@awaazlabs-uva\telephony\package.json -Pattern '"version"'
```

---

### CHECKPOINT G — paste into Cursor

Paste the full output of Step 9.2.

**PASS:** all three installed at the versions you published.  
**That** is when Wave 1 “client can npm install …” is actually met.

---

## Common failures (read before panic)

| What you see | Likely cause | What to do |
|--------------|--------------|------------|
| Org `ResourceNotFound` | Org not created / typo in name | Step 2 — name must be `awaazlabs-uva` |
| `ENEEDAUTH` | Not logged into npm on PC | `npm login` |
| GitHub secrets page 404 | No admin on Finova | Ask Ehsan to add `NPM_TOKEN` |
| Actions: `NPM_TOKEN secret is not set` | Secret missing/wrong repo | Step 4 |
| Actions: `repository.url … would be rejected` | Tagged on wrong GitHub repo | Tag/push on Finova only |
| Actions: `CHANGELOG.md has no '## [x.y.z]'` | Wrong heading format | Step 6.4 |
| Actions: tag version ≠ package.json | Typo in tag | Fix version or retag carefully |
| Actions: version already on npm | Re-publish same version | Bump version + CHANGELOG + new tag |
| `npm view` still 404 after green? | Rare CDN delay / wrong package name | Wait 1–2 min; check Actions “Publish” step; check exact name |
| 403 on publish | Token lacks write / not in org | New granular token with write to `awaazlabs-uva` |

---

## What to paste to Cursor for a full “are we done?” check

```powershell
npm whoami
npm org ls awaazlabs-uva
npm view @awaazlabs-uva/voice name version time
npm view @awaazlabs-uva/agents name version time
npm view @awaazlabs-uva/telephony name version time
```

---

## Do **not** do these

| Don’t | Why |
|-------|-----|
| `npm publish` from laptop for the real release | Skips provenance gates; easy to publish from wrong account |
| Put `NPM_TOKEN` only on `habiba-imran/...` | Wrong repo for Finova provenance publish |
| Rename the org to something else | Package names are hard-coded as `@awaazlabs-uva/...` |
| Tag before CHANGELOG headings exist | Workflow will fail |
| Push all three tags at once without watching | Harder to debug; do one-at-a-time |

Older notes in `docs/NPM_PUBLISH_STEPS.md` are outdated for first publish — **prefer this file**.

---

## One-page cheat sheet (links only)

1. npm signup/login → https://www.npmjs.com/login  
2. Create org → https://www.npmjs.com/org/create (`awaazlabs-uva`) → **Checkpoint A**  
3. Create token → https://www.npmjs.com/settings/~/tokens  
4. Add Finova secret → https://github.com/Finova-Solutions/urdu-voice-agent-SDK/settings/secrets/actions (`NPM_TOKEN`) → **Checkpoint B**  
5. Confirm Finova main → https://github.com/Finova-Solutions/urdu-voice-agent-SDK/commits/main → **Checkpoint C**  
6. Version + CHANGELOG PR → merge to Finova `main` → **Checkpoint D**  
7. Dry-run → https://github.com/Finova-Solutions/urdu-voice-agent-SDK/actions/workflows/release-sdk.yml → **Checkpoint E**  
8. Tags: `voice-v1.1.0`, `agents-v0.1.0`, `telephony-v0.1.0` → **Checkpoint F**  
9. Clean `npm install` of all three → **Checkpoint G**  

**Done = Checkpoint G passes.**

---

## Related files in this repo

| File | Role |
|------|------|
| `.github/workflows/release-sdk.yml` | The publisher |
| `sdk/` | `@awaazlabs-uva/voice` |
| `sdk-server/` | `@awaazlabs-uva/agents` |
| `telephony/` | `@awaazlabs-uva/telephony` |
| `docs/NPM_PUBLISH_STEPS.md` | Older short notes — use **this** guide instead |
