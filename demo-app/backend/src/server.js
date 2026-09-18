import { createApp } from './createApp.js';
import { loadConfig } from './config.js';

const config = loadConfig();
const app = createApp(config);

app.listen(config.port, () => {
  console.log(`demo-app backend listening on http://localhost:${config.port}`);
});
