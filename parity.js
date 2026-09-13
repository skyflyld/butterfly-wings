// 一致性探针：直接用 enhanced 模板里的 mdToHTML/smartBreak 渲染 md，
// 输出「块级标签序列」供 build.py 比对 —— 保证两版渲染规则同一套。
const fs = require('fs');
const path = require('path');
const D = __dirname;
const tpl = fs.readFileSync(path.join(D, 'templates/enhanced.html'), 'utf8');

function extract(name) {
  const i = tpl.indexOf('function ' + name + '(');
  if (i < 0) throw new Error('找不到函数 ' + name);
  let depth = 0;
  for (let k = tpl.indexOf('{', i); k < tpl.length; k++) {
    if (tpl[k] === '{') depth++;
    else if (tpl[k] === '}') { depth--; if (depth === 0) return tpl.slice(i, k + 1); }
  }
  throw new Error('括号不匹配 ' + name);
}
eval(extract('mdToHTML') + '\n' + extract('smartBreak') + '\nglobalThis.mdToHTML = mdToHTML;');

// 与浏览器一致：md 以 JS 模板字符串形式进入运行时（\n 解义、\` 解义）
const raw = fs.readFileSync(path.join(D, 'butterfly-wings-r16.md'), 'utf8');
const md = eval('`' + raw.replace(/`/g, '\\`') + '`');

const html = mdToHTML(md);
const seq = [...html.matchAll(/<(h[1-5]|p|hr|blockquote)(\s|>)/g)].map(m => m[1]);
const counts = seq.reduce((a, t) => (a[t] = (a[t] || 0) + 1, a), {});
console.log(JSON.stringify({ seq, counts, len: html.length }));
