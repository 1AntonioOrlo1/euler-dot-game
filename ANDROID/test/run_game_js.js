// run_game_js.js — проигрывает moves.json в JS-ядре, пишет game_js.json.
const fs = require("fs");
const path = require("path");
const core = require(path.join(__dirname, "..", "www", "js", "core.js"));

const allMoves = JSON.parse(fs.readFileSync(path.join(__dirname, "moves.json"), "utf8"));
const out = [];
for (const moves of allMoves) {
  const game = new core.Game();
  for (const [x, y] of moves) game.place(x, y);
  out.push({
    score: game.score,
    current: game.current,
    points: game.points.map(p => [p.x, p.y, p.color, p.active]),
  });
}
fs.writeFileSync(path.join(__dirname, "game_js.json"), JSON.stringify(out));
console.log("games=" + allMoves.length);
