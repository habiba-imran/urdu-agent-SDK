import { loadConfig } from './config.js';
import { createApp } from './createApp.js';

const config = loadConfig();
const app = createApp(config);

app.listen(config.port, () => {
  console.log(`AwaazLabs UVA host backend listening on :${config.port}`);
  console.log(`  POST /api/voice/session`);
  console.log(`  POST /api/voice/session/refresh`);
});
