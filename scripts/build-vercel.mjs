import { cp, mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
const root = path.resolve(import.meta.dirname, '..');
const out = path.join(root, 'dist');
await rm(out, { recursive: true, force: true });
await mkdir(out, { recursive: true });
// Explicit allowlist: operational DB, media, config and credentials are never bundled.
for (const name of ['index.html', 'app.js', 'production-guides.js', 'style.css', 'favicon.svg', 'video.html', 'video.js', 'video.css', 'assets']) {
  await cp(path.join(root, 'apps/dashboard', name), path.join(out, name), { recursive: true });
}
for (const name of await readdir(path.join(root, 'deploy/vercel'))) {
  await cp(path.join(root, 'deploy/vercel', name), path.join(out, name));
}
for (const name of ['index.html', 'video.html']) {
  const file = path.join(out, name);
  const source = await readFile(file, 'utf8');
  await writeFile(file, source.replace(/<head>/, '<head>\n<link rel="stylesheet" href="/remote.css">\n<script src="/remote.js" defer></script>'));
}
console.log('Built Vercel dashboard in dist/; local worker and runtime data remain on the Mac.');
