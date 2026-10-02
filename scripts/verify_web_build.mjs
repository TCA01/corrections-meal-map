import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';

const root = path.resolve('web/dist');
assert(fs.existsSync(path.join(root, 'index.html')));
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
for (const match of html.matchAll(/(?:src|href)="([^"#]+)"/g)) {
  const url = match[1];
  if (/^https?:/.test(url)) continue;
  const local = url.replace(/^.*?\/assets\//, 'assets/');
  assert(fs.existsSync(path.join(root, local)), `Missing built asset: ${url}`);
}
assert(fs.readdirSync(path.join(root, 'assets')).some(n => n.endsWith('.js')));
assert(fs.readdirSync(path.join(root, 'assets')).some(n => n.endsWith('.css')));
const source = path.resolve('web/public/web_data');
function files(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(e =>
    e.isDirectory() ? files(path.join(dir, e.name)) : [path.join(dir, e.name)]);
}
const expected = files(source);
const actual = files(path.join(root, 'web_data'));
assert.equal(actual.length, expected.length);
for (const file of expected) {
  assert(fs.readFileSync(file).equals(fs.readFileSync(path.join(root, 'web_data', path.relative(source, file)))));
}
const manifest = JSON.parse(fs.readFileSync(path.join(source, 'manifest.json'), 'utf8'));
const months = expected.filter(n => n.includes(`${path.sep}menus${path.sep}`)).length;
assert.equal(months, manifest.stats.institution_month_files);
console.log(`Built bundle verified: ${months} months; manifest/institutions byte-identical`);
