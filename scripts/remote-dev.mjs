// Local parity harness for the same Vercel handler; never starts an AI worker.
import http from 'node:http';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { createGateway } from '../deploy/gateway.mjs';
const root = path.resolve(import.meta.dirname, '..');
const gateway = createGateway();
const port = Number(process.env.BOCA_REMOTE_DEV_PORT || 8788);
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.png': 'image/png', '.jpg': 'image/jpeg' };
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1');
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/media/')) return gateway(req, res);
  const name = url.pathname === '/' ? 'index.html' : url.pathname === '/video' ? 'video.html' : url.pathname.slice(1);
  const file = path.resolve(root, 'dist', name);
  if (!file.startsWith(path.join(root, 'dist') + path.sep)) { res.writeHead(404).end(); return; }
  try {
    const content = await readFile(file);
    res.setHeader('Content-Type', types[path.extname(file)] || 'application/octet-stream');
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Content-Security-Policy', "default-src 'self'; img-src 'self'; media-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'");
    res.end(content);
  } catch { res.writeHead(404).end(); }
});
server.listen(port, '127.0.0.1', () => console.log(`Remote dashboard parity server: http://127.0.0.1:${port}`));
