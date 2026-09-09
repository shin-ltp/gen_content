// Ghost Admin API publish stub.
// Usage: node publish.mjs output/2026-09-06/
// Requires: GHOST_ADMIN_API_URL, GHOST_ADMIN_API_KEY env vars.
// TODO: install @tryghost/admin-api, parse frontmatter, convert md -> html, POST to Ghost.
import fs from 'node:fs';
import path from 'node:path';

const dir = process.argv[2];
if (!dir || !fs.existsSync(dir)) {
  console.error('Usage: node publish.mjs <output-dir>');
  process.exit(1);
}

const files = fs.readdirSync(dir).filter((f) => f.endsWith('.md'));
if (files.length === 0) {
  console.log('No .md files to publish.');
  process.exit(0);
}

console.log('Found:', files.join(', '));
console.log('Publish logic not implemented yet - see phases/phase3-publish.md');