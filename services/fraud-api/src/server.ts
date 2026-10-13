import { createApp } from './app';

const port = Number(process.env['PORT'] ?? 3100);
createApp().listen(port, () => {
  console.log(`TrustBank fraud API (simulated) listening on http://localhost:${port}`);
});
