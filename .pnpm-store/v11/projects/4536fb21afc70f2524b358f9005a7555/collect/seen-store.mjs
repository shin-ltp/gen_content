// seen-store.mjs — 跨天跨信源的已抓取文章履历（去重用）
import fs from 'node:fs';
import path from 'node:path';
import { safeReadJson, atomicWrite } from './collect-utils.mjs';
const PROJECT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\//,'')), '..', '..');
const DB_DIR = path.join(PROJECT, 'db');
const DB_FILE = path.join(DB_DIR, 'seen-articles.json');
const SIG = 'seen-v2';
function load() {
  const { value, needWrite } = safeReadJson(DB_FILE,
    { _meta: { total: 0, updated: '' }, articles: {} }, SIG);
  if (needWrite) save(value);
  return value;
}
function save(store) {
  fs.mkdirSync(DB_DIR, { recursive: true });
  store._meta.total = Object.keys(store.articles).length;
  store._meta.updated = new Date().toISOString();
  atomicWrite(DB_FILE, JSON.stringify(store, null, 2), SIG);
}
function key(source, id) { return source + '-' + id; }
function has(store, source, id) { return Object.prototype.hasOwnProperty.call(store.articles, key(source, id)); }
function add(store, source, id, meta) { store.articles[key(source, id)] = Object.assign({ source, first_seen: new Date().toISOString().slice(0,10) }, meta || {}); }
function stats(store) { const by = {}; for (const [k, v] of Object.entries(store.articles)) { by[v.source] = (by[v.source] || 0) + 1; } return by; }
export { load, save, key, has, add, stats, DB_FILE };
