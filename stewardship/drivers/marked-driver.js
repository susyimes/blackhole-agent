// Node driver prelude for the marked markdown renderer (npm frontier target).
// TARGET_DIR is bound by the frontier plane to the extracted package root;
// require(TARGET_DIR) resolves through marked's own package.json main field.
function render(text, plugins) {
    const { marked } = require(TARGET_DIR);
    return marked.parse(text);
}
