// shoot_playwright.mjs - capture visual.html slides with Playwright (Chromium).
// Mirrors the state variants from prepare_remotion.py but uses a single
// browser page instead of per-shot headless Chrome launches.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const _require = createRequire(
  'C:/Users/RW250701/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/'
);
const { chromium } = _require('playwright');

const ROOT = path.resolve('us-stock-daily');
const ISSUE = process.argv[2] || '2026-09-08';
const ONLY = (() => {
  const i = process.argv.indexOf('--only');
  return i >= 0 ? process.argv[i + 1].split(',') : null;
})();

const issueDir = path.join(ROOT, 'daily-output', ISSUE);
const prodDir = path.join(issueDir, 'production');
const htmlPath = path.join(issueDir, 'visual.html');
const outDir = path.join(ROOT, 'remotion', 'public', 'assets', 'slides');

const slideState = (slide, cue, segId) => {
  let m = cue.match(/carousel idx=(\d)/);
  if (m) return [`i${m[1]}`, 'carousel'];
  m = cue.match(/news idx=(\d)/);
  if (m) return [`i${m[1]}`, 'news'];
  if (slide === 's2') {
    m = cue.match(/idx=(\d)/);
    if (m) return [`i${m[1]}`, 'carousel'];
    return [segId.includes('close') || cue.includes('stays') ? 'i3' : 'i0', 'carousel'];
  }
  if (slide === 's33') {
    m = segId.match(/^S37-C(\d)/);
    return m ? [`i${Number(m[1]) - 1}`, 'news'] : ['i0', 'news'];
  }
  return [null, null];
};

const sortKey = (name) => {
  const m = name.match(/^s(\d+)(?:_i(\d+))?\.png$/);
  if (!m) return [1e9, 0, 0];
  return [Number(m[1]), m[2] === undefined ? 0 : 1, Number(m[2] || 0)];
};

const html = fs.readFileSync(htmlPath, 'utf8');
const segMap = JSON.parse(
  fs
    .readFileSync(path.join(prodDir, 'segment-map.json'), 'utf8')
    .replace(/^\uFEFF/, '')
);

const want = new Map();
for (const m of html.matchAll(/id="(s\d+)"/g)) {
  want.set(`${m[1]}.png`, { target: m[1], state: null, kind: null, idx: -1 });
}
for (const seg of segMap.segments || []) {
  const slide = seg.slide || '';
  if (!/^s\d+$/.test(slide)) continue;
  const [state, kind] = slideState(slide, seg.cue || '', seg.id || '');
  if (!state) continue;
  want.set(`${slide}_${state}.png`, {
    target: slide,
    state,
    kind,
    idx: Number(state.slice(1)),
  });
}

const shots = [...want.entries()]
  .filter(([name]) => !ONLY || ONLY.some((id) => name === `${id}.png` || name.startsWith(`${id}_i`)))
  .sort((a, b) => {
    const [a1, a2, a3] = sortKey(a[0]);
    const [b1, b2, b3] = sortKey(b[0]);
    return a1 - b1 || a2 - b2 || a3 - b3;
  });

fs.mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--no-sandbox', '--disable-gpu'],
});
const page = await browser.newPage({
  viewport: { width: 1920, height: 1080 },
  deviceScaleFactor: 1,
});
await page.goto(`file:///${htmlPath.replace(/\\/g, '/')}`, { waitUntil: 'load' });
await page.evaluate(async () => {
  await document.fonts.ready;
  await Promise.all(
    [...document.images].map((img) =>
      img.complete
        ? Promise.resolve()
        : new Promise((res) => {
            img.onload = img.onerror = res;
          })
    )
  );
});

let failed = 0;
const styleHandle = await page.addStyleTag({ content: '/* slide state */' });
for (const [name, { target, state, kind, idx }] of shots) {
  const css =
    '*{transition:none!important;animation:none!important}' +
    '.nav-bar,.slabel{display:none!important}' +
    '.slide-container{margin-top:0!important;padding:0!important;gap:0!important}' +
    `.swrap{display:none!important}#${target}{display:block!important}` +
    '.slide{border-radius:0!important;box-shadow:none!important}';
  await styleHandle.evaluate((el, content) => {
    el.textContent = content;
  }, css);
  if (kind) {
    await page.evaluate(
      ({ slide, variantKind, variantIdx }) => {
        if (variantKind === 'carousel') {
          document
            .querySelectorAll(`#${slide} .topic-item`)
            .forEach((el, i) => {
              el.classList.toggle('active', i === variantIdx);
              el.classList.toggle('dimmed', i !== variantIdx);
            });
          document
            .querySelectorAll(`#${slide} .photo-frame`)
            .forEach((el, i) => el.classList.toggle('active', i === variantIdx));
        }
        if (variantKind === 'news') {
          document.querySelectorAll(`#${slide} .n-item`).forEach((el, i) => {
            el.classList.toggle('active', i === variantIdx);
            el.classList.toggle('dim', i !== variantIdx);
          });
        }
      },
      { slide: target, variantKind: kind, variantIdx: idx }
    );
  }
  const out = path.join(outDir, name);
  try {
    await page.locator(`#${target} .slide`).screenshot({ path: out });
    console.log(`[shot] ${name}`);
  } catch (err) {
    failed++;
    console.error(`[error] ${name}: ${err.message}`);
  }
}

await browser.close();
if (failed) {
  console.error(`[error] ${failed} shot(s) failed`);
  process.exit(1);
}
