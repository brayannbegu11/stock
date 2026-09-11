// Renderiza la sección de la semana y la tabla de semanas de docs/index.html con un data.json dado, en los tres idiomas.
// Uso: node tests/site_render.cjs <ruta a data.json>   → JSON {es|en|zh: {week, table}} por stdout.
const fs = require("fs"), vm = require("vm"), path = require("path");
const html = fs.readFileSync(path.join(__dirname, "..", "docs", "index.html"), "utf8");
const data = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
let code = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].pop()[1];
code = code.replace(/state.lang\s*=\s*detectLang\(\);\s*render\(\);/, "globalThis.api={S,DATA,state,weekSection,weeksTable};");
const ctx = { document: { getElementById: () => ({ textContent: JSON.stringify(data) }) }, Intl, URLSearchParams };
vm.createContext(ctx);
vm.runInContext(code, ctx);
const a = ctx.api, out = {};
for (const lang of ["es", "en", "zh"]) {
  a.state.lang = lang;
  out[lang] = { week: a.weekSection(), table: a.weeksTable(a.DATA.scenarios[0]) };
}
process.stdout.write(JSON.stringify(out));
