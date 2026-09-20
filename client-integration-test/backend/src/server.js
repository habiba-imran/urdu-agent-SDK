import { loadConfig } from './config.js';
import { createApp } from './createApp.js';

const config = loadConfig();
const app = createApp(config);

app.listen(config.port, () => {
  console.log(`[client-integration-test] host backend on :${config.port}`);
  console.log('  voice:   /api/voice/session[+refresh]');
  console.log('  agents:  /api/agents , /api/provider-capabilities');
  console.log('  phone:   /api/telephony/* (Telnyx key from backend .env)');
  console.log(`  telnyx key configured: ${Boolean(config.telnyxApiKey)}`);
});
