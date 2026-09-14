// validate-build.mjs
// Usage:
//   node scripts/validate-build.mjs --post  (run after build — checks /api/config is called by bundle)
import { readdirSync, readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const mode = process.argv[2];

if (mode === '--post') {
  const dist = join(process.cwd(), 'dist', 'assets');
  if (!existsSync(dist)) {
    console.error('[validate] dist/assets not found — run npm run build first');
    process.exit(1);
  }
  const found = readdirSync(dist)
    .filter((f) => f.endsWith('.js'))
    .some((f) => readFileSync(join(dist, f), 'utf8').includes('/api/config'));
  if (!found) {
    console.error('[validate] /api/config not found in bundle — runtime config fetch is missing');
    process.exit(1);
  }
  console.log('[validate] bundle OK — runtime /api/config call present in dist/assets');
} else {
  console.error('Usage: node scripts/validate-build.mjs --post');
  process.exit(1);
}
