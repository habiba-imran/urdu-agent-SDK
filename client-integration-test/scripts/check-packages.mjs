import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, realpathSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const manifest = JSON.parse(readFileSync(resolve(root, 'packages/voice-manifest.json'), 'utf8'));
const archive = readFileSync(resolve(root, 'packages', manifest.artifact));
assert.equal(createHash('sha256').update(archive).digest('hex'), manifest.sha256, 'SDK archive hash mismatch');
for (const [dir, name, version] of [
  ['frontend', '@awaazlabs-uva/voice', manifest.version],
  ['backend', '@awaazlabs-uva/agents', '0.1.0'],
  ['backend', '@awaazlabs-uva/telephony', '0.1.0'],
]) {
  const require = createRequire(resolve(root, dir, 'package.json'));
  const entry = realpathSync(require.resolve(name));
  assert.ok(!relative(resolve(root, dir, 'node_modules'), entry).startsWith('..'), `${name} resolves outside client node_modules`);
  const pkg = JSON.parse(readFileSync(resolve(dirname(entry), '../package.json'), 'utf8'));
  assert.equal(pkg.version, version);
  if (dir === 'frontend') {
    const source = readFileSync(entry, 'utf8');
    assert.ok(source.includes('awaaz_playback_state') && source.includes('audio_ready'), 'Missing playback readiness handshake');
  }
  console.log(`${name}@${pkg.version}: independent installed package verified`);
}
