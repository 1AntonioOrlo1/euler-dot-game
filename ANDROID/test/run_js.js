// run_js.js — прогоняет cases.json через JS-ядро (core.js), пишет ref_js.json.
const fs = require("fs");
const path = require("path");
const core = require(path.join(__dirname, "..", "www", "js", "core.js"));

const cases = JSON.parse(fs.readFileSync(path.join(__dirname, "cases.json"), "utf8"));
const out = [];
let rayErrors = 0;
for (const c of cases) {
  // строим структуру из активных точек (все точки активны в тесте)
  const pts = c.pts.map(([x, y]) => ({ x, y }));
  const st = new core.ColorStructure();
  st.rebuild(pts, c.R);
  const row = [];
  for (const X of c.qs) {
    let fast;
    try {
      fast = st.query(X);
    } catch (e) {
      fast = null;
      rayErrors++;
    }
    row.push(fast);
  }
  out.push(row);
}
fs.writeFileSync(path.join(__dirname, "ref_js.json"), JSON.stringify(out));
console.log("cases=" + cases.length + " rayErrors=" + rayErrors);
