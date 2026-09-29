import 'dotenv/config';
import { createApp } from './createApp.js';

const port = Number(process.env.PORT || 3010);
const toolGatewaySecret = (process.env.TOOL_GATEWAY_SECRET || '').trim();

if (!toolGatewaySecret) {
  console.error('TOOL_GATEWAY_SECRET is required (see .env.example)');
  process.exit(1);
}

const app = createApp({ toolGatewaySecret });
app.listen(port, () => {
  console.log(`uva-host-tools listening on http://127.0.0.1:${port}`);
  console.log('Worker tools_base_url example: http://127.0.0.1:' + port);
});
