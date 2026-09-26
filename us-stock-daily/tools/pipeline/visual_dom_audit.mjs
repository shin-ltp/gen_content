// visual_dom_audit.mjs - real-browser DOM audit of issue visual.html.
// Extracted from final_qa (2026-09-25 restructure): layout/escape/preview
// defects must be caught right after render_visual, before Remotion spends
// a full render on them. Mirrors shoot_playwright.mjs bootstrapping and
// state-switching so what is audited is what Remotion will screenshot.
//
// Usage (cwd = repo root):
//   node us-stock-daily/tools/pipeline/visual_dom_audit.mjs 2026-09-25 --json
// Output: one JSON object on stdout { failures: [...], notes: [...] }.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const _require = createRequire(
  'C:/Users/RW250701/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/'
);
const { chromium } = _require('playwright');

const ROOT = path.resolve('us-stock-daily');
const ISSUE = process.argv[2];
if (!ISSUE || !/^\d{4}-\d{2}-\d{2}$/.test(ISSUE)) {
  console.log(JSON.stringify({ failures: ['usage: visual_dom_audit.mjs YYYY-MM-DD'], notes: [] }));
  process.exit(3);
}

const issueDir = path.join(ROOT, 'daily-output', ISSUE);
const prodDir = path.join(issueDir, 'production');
const htmlPath = path.join(issueDir, 'visual.html');
if (!fs.existsSync(htmlPath)) {
  console.log(JSON.stringify({ failures: [`missing ${htmlPath}`], notes: [] }));
  process.exit(3);
}

const segMap = JSON.parse(
  fs.readFileSync(path.join(prodDir, 'segment-map.json'), 'utf8').replace(/^\uFEFF/, '')
);

// Carousel/news state variants the Remotion shot stage will switch through.
const variants = new Map(); // slide -> Set of {kind, idx}
const addVariant = (slide, kind, idx) => {
  if (!variants.has(slide)) variants.set(slide, new Map());
  variants.get(slide).set(`${kind}:${idx}`, { kind, idx });
};
for (const seg of segMap.segments || []) {
  const slide = seg.slide || '';
  if (!/^s\d+$/.test(slide)) continue;
  let m = (seg.cue || '').match(/(carousel|news) idx=(\d)/);
  if (m) addVariant(slide, m[1], Number(m[2]));
  else if (slide === 's33') {
    const lm = String(seg.id || '').match(/^S37-C(\d)/);
    if (lm) addVariant(slide, 'news', Number(lm[1]) - 1);
  }
}

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
      img.complete ? Promise.resolve()
        : new Promise((res) => { img.onload = img.onerror = res; })
    )
  );
});

// Slides referenced by segment-map must render; empty placeholder swraps
// beyond the used range (template slots s47+) are skipped as unused.
const usedSlides = new Set(
  (segMap.segments || []).map((s) => s.slide).filter((s) => /^s\d+$/.test(s || ''))
);

const failures = [];
const notes = [];
const styleHandle = await page.addStyleTag({ content: '/* audit */' });

const slideIds = await page.evaluate(() =>
  [...document.querySelectorAll('[id^="s"]')].filter((el) => /^s\d+$/.test(el.id)).map((el) => el.id)
);
if (!slideIds.length) failures.push('DOM: no slides found (id="sN")');

for (const slide of slideIds) {
  const placeholder = await page.evaluate(
    (slide) => !document.querySelector(`#${slide} .slide`), slide);
  if (placeholder) {
    if (usedSlides.has(slide)) failures.push(`${slide}: referenced by segment-map but empty`);
    else notes.push(`${slide}: unused template placeholder (skipped)`);
    continue;
  }
  // Same isolation CSS shoot_playwright uses.
  await styleHandle.evaluate((el, content) => { el.textContent = content; },
    '*{transition:none!important;animation:none!important}' +
    '.nav-bar,.slabel{display:none!important}' +
    '.slide-container{margin-top:0!important;padding:0!important;gap:0!important}' +
    `.swrap{display:none!important}#${slide}{display:block!important}` +
    '.slide{border-radius:0!important;box-shadow:none!important}');

  const report = await page.evaluate((slide) => {
    const out = { failures: [], notes: [] };
    const root = document.querySelector(`#${slide} .slide`);
    if (!root) { out.failures.push(`${slide}: .slide element missing`); return out; }
    const slideRect = root.getBoundingClientRect();
    if (Math.abs(slideRect.width - 1920) > 1 || Math.abs(slideRect.height - 1080) > 1)
      out.failures.push(`${slide}: slide rect ${slideRect.width}x${slideRect.height} != 1920x1080`);
    if (root.scrollHeight > 1080 + 10)
      out.notes.push(`${slide}: scrollHeight ${root.scrollHeight} > 1090 (vertical overflow)`);
    for (const img of root.querySelectorAll('img')) {
      const frame = img.closest('.photo-frame');
      const opacity = (el) => {
        let cur = el;
        let v = 1;
        while (cur && cur !== root) {
          v *= Number(getComputedStyle(cur).opacity || 1);
          cur = cur.parentElement;
        }
        return v;
      };
      const visible = opacity(img) > 0.05;
      if (img.naturalWidth === 0) {
        out.failures.push(`${slide}: broken image ${img.getAttribute('src')}`);
        continue;
      }
      if (!visible) continue;
      const r = img.getBoundingClientRect();
      if (r.right > slideRect.right + 2 || r.left < slideRect.left - 2)
        out.failures.push(
          `${slide}: image escapes slide horizontally ` +
          `(left=${Math.round(r.left - slideRect.left)} right=${Math.round(r.right - slideRect.left)} of 1920)`);
      if (frame) {
        const radius = getComputedStyle(frame).borderRadius;
        const isPortrait = frame.classList.contains('portrait');
        if (isPortrait && radius !== '50%')
          out.failures.push(`${slide}: portrait frame not circular (border-radius=${radius})`);
        if (!isPortrait && radius === '50%')
          out.failures.push(`${slide}: non-portrait frame rendered as circle`);
      }
    }
    return out;
  }, slide);
  failures.push(...report.failures);
  notes.push(...report.notes);

  // Carousel/news highlight switching must be one-of-N, exactly as the shot
  // stage toggles it (9/24 s1 layout bug class).
  for (const v of (variants.get(slide) || new Map()).values()) {
    const vReport = await page.evaluate(({ slide, kind, idx }) => {
      const out = { failures: [], notes: [] };
      if (kind === 'carousel') {
        document.querySelectorAll(`#${slide} .topic-item`).forEach((el, i) => {
          el.classList.toggle('active', i === idx);
          el.classList.toggle('dimmed', i !== idx);
        });
        document.querySelectorAll(`#${slide} .photo-frame`)
          .forEach((el, i) => el.classList.toggle('active', i === idx));
      } else if (kind === 'news') {
        document.querySelectorAll(`#${slide} .n-item`).forEach((el, i) => {
          el.classList.toggle('active', i === idx);
          el.classList.toggle('dim', i !== idx);
        });
      }
      if (kind === 'carousel') {
        const active = [...document.querySelectorAll(`#${slide} .topic-item.active`)];
        if (active.length !== 1)
          out.failures.push(`${slide} ${kind} idx=${idx}: expected 1 active topic item, got ${active.length}`);
        else if (active[0].dataset.idx !== undefined && Number(active[0].dataset.idx) !== idx)
          out.failures.push(`${slide} ${kind} idx=${idx}: active topic data-idx=${active[0].dataset.idx}`);
        const photos = [...document.querySelectorAll(`#${slide} .photo-frame.active`)];
        if (photos.length !== 1)
          out.failures.push(`${slide} ${kind} idx=${idx}: expected 1 active photo, got ${photos.length}`);
        else if (photos[0].dataset.idx !== undefined && Number(photos[0].dataset.idx) !== idx)
          out.failures.push(`${slide} ${kind} idx=${idx}: active photo data-idx=${photos[0].dataset.idx}`);
        const shown = photos.filter((el) => {
          let cur = el, v = 1;
          while (cur) { v *= Number(getComputedStyle(cur).opacity || 1); if (cur.id === slide) break; cur = cur.parentElement; }
          return v > 0.05;
        });
        if (photos.length === 1 && shown.length === 0)
          out.failures.push(`${slide} ${kind} idx=${idx}: active photo not visible`);
      } else if (kind === 'news') {
        const active = [...document.querySelectorAll(`#${slide} .n-item.active`)];
        if (active.length !== 1)
          out.failures.push(`${slide} ${kind} idx=${idx}: expected 1 active news item, got ${active.length}`);
      }
      return out;
    }, { slide, kind: v.kind, idx: v.idx });
    failures.push(...vReport.failures.map((f) => `[state] ${f}`));
    notes.push(...vReport.notes);
  }
}

await browser.close();
console.log(JSON.stringify({ failures, notes }));
process.exit(failures.length ? 2 : 0);
