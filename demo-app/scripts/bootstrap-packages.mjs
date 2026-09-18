#!/usr/bin/env node
/**
 * Install @awaazlabs-uva/voice + @awaazlabs-uva/agents the same way a host would:
 * prefer the public npm registry; if unpublished, pack the monorepo packages and
 * `npm install` the tarballs (still goes through npm's package install path).
 */
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, rmSync, copyFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const demoRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(demoRoot, '..');
const packsDir = path.join(demoRoot, '.packs');

function npmCmd() {
  return process.platform === 'win32' ? 'npm.cmd' : 'npm';
}

function run(command, args, opts = {}) {
  // Windows must use shell so npm.cmd / .bat shims resolve; shell:false exits 1 with no output.
  const result = spawnSync(command, args, {
    stdio: 'inherit',
    shell: process.platform === 'win32',
    ...opts,
  });
  if (result.error) {
    console.error(result.error.message);
    process.exit(1);
  }
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
  return result;
}

function runCapture(command, args, opts = {}) {
  return spawnSync(command, args, {
    encoding: 'utf8',
    shell: process.platform === 'win32',
    ...opts,
  });
}

function npmViewVersion(packageName) {
  const result = runCapture(npmCmd(), ['view', packageName, 'version'], {
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  if (result.status !== 0) return null;
  const version = String(result.stdout || '').trim();
  return version || null;
}

function buildPackage(dir) {
  console.log(`\n→ Building ${path.relative(repoRoot, dir)}`);
  if (!existsSync(path.join(dir, 'node_modules'))) {
    run(npmCmd(), ['install'], { cwd: dir });
  }
  run(npmCmd(), ['run', 'build'], { cwd: dir });
}

function packPackage(dir) {
  mkdirSync(packsDir, { recursive: true });
  const before = new Set(readdirSync(packsDir));
  run(npmCmd(), ['pack', '--pack-destination', packsDir], { cwd: dir });
  const after = readdirSync(packsDir).filter((name) => name.endsWith('.tgz'));
  const created = after.filter((name) => !before.has(name));
  if (created.length === 0) {
    // pack may have overwritten an existing tarball with the same name
    const newest = after
      .map((name) => ({ name, mtime: path.join(packsDir, name) }))
      .sort((a, b) => a.name.localeCompare(b.name));
    if (newest.length === 0) {
      throw new Error(`npm pack produced no tarball for ${dir}`);
    }
    return path.join(packsDir, newest[newest.length - 1].name);
  }
  return path.join(packsDir, created[0]);
}

function installDep(prefixDir, packageName, spec) {
  console.log(`\n→ npm install ${packageName}@${spec} → ${path.relative(demoRoot, prefixDir)}`);
  run(npmCmd(), ['install', `${packageName}@${spec}`], { cwd: prefixDir });
}

function installTarball(prefixDir, packageName, tarballPath) {
  console.log(
    `\n→ npm install ${packageName} from ${path.relative(demoRoot, tarballPath)} → ${path.relative(demoRoot, prefixDir)}`,
  );
  run(npmCmd(), ['install', tarballPath], { cwd: prefixDir });
}

const voiceDir = path.join(repoRoot, 'sdk');
const agentsDir = path.join(repoRoot, 'sdk-server');
const frontendDir = path.join(demoRoot, 'frontend');
const backendDir = path.join(demoRoot, 'backend');

const voiceRegistry = npmViewVersion('@awaazlabs-uva/voice');
const agentsRegistry = npmViewVersion('@awaazlabs-uva/agents');

console.log('UVA demo-app package bootstrap');
console.log(
  voiceRegistry
    ? `  registry @awaazlabs-uva/voice@${voiceRegistry}`
    : '  registry @awaazlabs-uva/voice — not published yet',
);
console.log(
  agentsRegistry
    ? `  registry @awaazlabs-uva/agents@${agentsRegistry}`
    : '  registry @awaazlabs-uva/agents — not published yet',
);

if (voiceRegistry && agentsRegistry) {
  installDep(frontendDir, '@awaazlabs-uva/voice', `^${voiceRegistry}`);
  installDep(backendDir, '@awaazlabs-uva/agents', `^${agentsRegistry}`);
  console.log('\n✓ Installed both packages from the npm registry.');
  process.exit(0);
}

console.log('\nPackages not on npm yet — building + packing monorepo packages, then npm-installing tarballs.');
buildPackage(voiceDir);
buildPackage(agentsDir);

if (existsSync(packsDir)) {
  for (const name of readdirSync(packsDir)) {
    if (name.endsWith('.tgz')) rmSync(path.join(packsDir, name));
  }
} else {
  mkdirSync(packsDir, { recursive: true });
}

const voiceTgz = packPackage(voiceDir);
const agentsTgz = packPackage(agentsDir);

// Keep stable names for docs/lockfile readability.
const voiceStable = path.join(packsDir, 'awaazlabs-uva-voice.tgz');
const agentsStable = path.join(packsDir, 'awaazlabs-uva-agents.tgz');
copyFileSync(voiceTgz, voiceStable);
copyFileSync(agentsTgz, agentsStable);
if (voiceTgz !== voiceStable) rmSync(voiceTgz, { force: true });
if (agentsTgz !== agentsStable) rmSync(agentsTgz, { force: true });

installTarball(frontendDir, '@awaazlabs-uva/voice', voiceStable);
installTarball(backendDir, '@awaazlabs-uva/agents', agentsStable);

console.log('\n✓ Installed packed packages via npm (local tarballs).');
console.log('  After release tags publish to npm, re-run: npm run bootstrap');
