const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const context = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../Ui.js'), 'utf8').replace('.pragma library', ''), context);

const notes = '/home/notes';
assert.equal(context.allowedPath(notes + '/hyprland.md', [notes]), true);
assert.equal(context.allowedPath(notes, [notes]), true);
assert.equal(context.allowedPath(notes + 'extra/file.md', [notes]), false);
assert.equal(context.allowedPath(notes + '/../secret.md', [notes]), false);
assert.equal(context.allowedPath('/etc/passwd', [notes]), false);
assert.equal(context.allowedPath(notes + '/./file.md', [notes]), false);
assert.equal(context.allowedPath('notes/file.md', [notes]), false);
assert.equal(context.allowedPath(notes + '/file.md', []), false);

const row = {path: notes + '/hyprland.md', excerpt: 'the blur shader', kind: 'text', score: 0.5};
const doc = {
    ok: true,
    op: 'search',
    error: '',
    answer: '',
    results: [row],
    roots: [notes],
    files: 1,
    chunks: 1,
    embedModel: false,
    gemmaModel: false,
    stopped: ''
};
assert.equal(context.parse(JSON.stringify(doc)).results[0].path, row.path);
assert.equal(context.parse(JSON.stringify({...doc, error: 'Missing model'})).error, 'Missing model');
assert.throws(() => context.parse(JSON.stringify({...doc, results: Array(9).fill(row)})));
assert.throws(() => context.parse(JSON.stringify({...doc, roots: Array(17).fill(notes)})));
assert.throws(() => context.parse(JSON.stringify({...doc, results: [{...row, path: '/etc/passwd'}]})));
assert.throws(() => context.parse(JSON.stringify({...doc, results: [{...row, kind: 'audio'}]})));
assert.throws(() => context.parse(JSON.stringify({...doc, results: [{...row, score: Infinity}]})));
assert.throws(() => context.parse(JSON.stringify({...doc, results: [{...row, excerpt: 'a'.repeat(401)}]})));
assert.throws(() => context.parse('x'.repeat(65537)));
assert.throws(() => context.parse('null'));
assert.throws(() => context.parse('{"ok":true}'));

function textBlocks(src) {
    const blocks = [];
    const re = /\b(?:Text|Label|TextEdit|StyledText)\s*\{/g;
    let match;
    while ((match = re.exec(src))) {
        let i = re.lastIndex;
        let depth = 1;
        while (i < src.length && depth) {
            if (src[i] === '{') depth++;
            else if (src[i] === '}') depth--;
            i++;
        }
        blocks.push(src.slice(match.index, i));
    }
    return blocks;
}

for (const file of ['Overlay.qml', 'ActionButton.qml', 'BarWidget.qml']) {
    const src = fs.readFileSync(path.join(__dirname, '..', file), 'utf8');
    const blocks = textBlocks(src);
    if (file !== 'BarWidget.qml') assert.ok(blocks.length, file);
    for (const block of blocks) assert.ok(block.includes('textFormat: Text.PlainText'), file);
}

const overlay = fs.readFileSync(path.join(__dirname, '../Overlay.qml'), 'utf8');
assert.match(overlay, /function close\(\) \{[^}]*opened = false/);
assert.doesNotMatch(overlay, /function close\(\) \{[^}]*results\s*=/);
assert.doesNotMatch(overlay, /StdioCollector/);
assert.doesNotMatch(overlay, /IpcHandler/);
assert.doesNotMatch(overlay, /OMA_GEMMA_FIND_RUNTIME/);
assert.doesNotMatch(overlay, /bash|sh",\s*"-c"|shell\s*-c/);
assert.doesNotMatch(overlay, /source:\s*["']https?:/);
assert.match(overlay, /\/usr\/bin\/python3", "-I", "-S", "-B"/);
assert.match(overlay, /splitMarker:\s*""/);
assert.match(overlay, /\/usr\/bin\/xdg-open", "--"/);
assert.match(overlay, /worker\.signal\(15\)/);
assert.match(overlay, /worker\.signal\(9\)/);
assert.match(overlay, /clearEnvironment:\s*true/);

const bar = fs.readFileSync(path.join(__dirname, '../BarWidget.qml'), 'utf8');
assert.match(bar, /tooltipText:\s*"Gemma Find"/);
assert.doesNotMatch(bar, /source:\s*["']https?:/);
assert.doesNotMatch(bar, /bash|sh",\s*"-c"/);
assert.match(bar, /io\.github\.cfaulkingham\.oma-gemma-find/);

const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, '../manifest.json'), 'utf8'));
assert.equal(manifest.keepLoaded, true);
assert.equal(manifest.name, 'Gemma Find');
assert.equal(manifest.id, 'io.github.cfaulkingham.oma-gemma-find');
assert.equal(manifest.entryPoints.overlay, 'Overlay.qml');
assert.equal(manifest.entryPoints.barWidget, 'BarWidget.qml');

console.log('UI validation tests passed');
