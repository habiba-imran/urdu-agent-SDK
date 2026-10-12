import assert from 'node:assert/strict';
import { readFileSync, realpathSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
for (const [dir, name, version] of [
  ['frontend', '@awaazlabs-uva/voice', '1.1.1'],
  ['backend', '@awaazlabs-uva/agents', '0.1.1'],
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
  assert.ok(locked.resolved.startsWith(`https://registry.npmjs.org/${name}/-/`), `${name} must come from npm`);
  assert.ok(locked.integrity, `${name} must have registry integrity metadata`);
  if (dir === 'frontend') {
    const source = readFileSync(entry, 'utf8');
    assert.ok(source.includes('awaaz_playback_state') && source.includes('audio_ready'), 'Missing playback readiness handshake');
  }
  console.log(`${name}@${pkg.version}: independent installed package verified`);
}
