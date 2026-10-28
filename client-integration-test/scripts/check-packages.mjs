import assert from 'node:assert/strict';
import { readFileSync, realpathSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const snapshots = JSON.parse(readFileSync(resolve(root, 'packages/lifecycle-manifest.json'), 'utf8'));
for (const [dir, name, version] of [
  ['frontend', '@awaazlabs-uva/voice', '1.1.1'],
  ['backend', '@awaazlabs-uva/agents', '0.1.2-humanization.0'],
  ['backend', '@awaazlabs-uva/telephony', '0.1.1'],
]) {
  const require = createRequire(resolve(root, dir, 'package.json'));
  const entry = realpathSync(require.resolve(name));
  assert.ok(!relative(resolve(root, dir, 'node_modules'), entry).startsWith('..'), `${name} resolves outside client node_modules`);
  const pkg = JSON.parse(readFileSync(resolve(dirname(entry), '../package.json'), 'utf8'));
  assert.equal(pkg.version, version);
  const lock = JSON.parse(readFileSync(resolve(root, dir, 'package-lock.json'), 'utf8'));
  const locked = lock.packages[`node_modules/${name}`];
  assert.equal(locked.version, version);
  const snapshot = snapshots.packages.find(pkg => pkg.name === name);
  assert.equal(snapshot.version, version);
  assert.equal(locked.resolved, 'file:../packages/' + snapshot.artifact);
  const archive = readFileSync(resolve(root, 'packages', snapshot.artifact));
  assert.equal(createHash('sha256').update(archive).digest('hex'), snapshot.sha256);
  assert.equal(locked.integrity, 'sha512-' + createHash('sha512').update(archive).digest('base64'), 'Reviewed SDK archive changed; reinstall the snapshot');
  if (name === '@awaazlabs-uva/agents') {
    assert.ok(readFileSync(entry, 'utf8').includes('validateHumanization'), 'Installed Agents SDK lacks persona controls');
  }
  assert.ok(locked.integrity, `${name} must have artifact integrity metadata`);
  if (dir === 'frontend') {
    const source = readFileSync(entry, 'utf8');
    assert.ok(source.includes('awaaz_playback_state') && source.includes('audio_ready'), 'Missing playback readiness handshake');
    assert.ok(source.includes('awaaz_agent_ready') && source.includes('reconnecting'), 'Missing lifecycle protocol');
  }
  console.log(`${name}@${pkg.version}: independent installed package verified`);
}
