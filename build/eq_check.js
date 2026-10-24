function evalScore5(cards) {
  const cnt = new Array(15).fill(0);
  const rs = [];
  let flush = true;
  const s0 = cards[0].s;
  for (const c of cards) { cnt[c.r]++; rs.push(c.r); if (c.s !== s0) flush = false; }
  rs.sort((a, b) => b - a);
  const g = [];
  for (let r = 14; r >= 2; r--) if (cnt[r]) g.push([cnt[r], r]);
  g.sort((a, b) => b[0] - a[0] || b[1] - a[1]);
  let sh = 0;
  const uniq = rs.filter((v, i) => i === 0 || v !== rs[i - 1]);
  if (uniq.length === 5) {
    if (uniq[0] - uniq[4] === 4) sh = uniq[0];
    else if (uniq[0] === 14 && uniq[1] === 5 && uniq[1] - uniq[4] === 3) sh = 5;
  }
  if (flush && sh) return [8, sh];
  if (g[0][0] === 4) return [7, g[0][1], g[1][1]];
  if (g[0][0] === 3 && g[1][0] === 2) return [6, g[0][1], g[1][1]];
  if (flush) return [5].concat(rs);
  if (sh) return [4, sh];
  if (g[0][0] === 3) return [3, g[0][1], rs.filter(r => r !== g[0][1])];
  if (g[0][0] === 2 && g[1][0] === 2) return [2, g[0][1], g[1][1], g[2][1]];
  if (g[0][0] === 2) return [1, g[0][1], rs.filter(r => r !== g[0][1])];
  return [0].concat(rs);
}
function scoreCmp(a, b) {
  const n = Math.max(a.length, b.length);
  for (let i = 0; i < n; i++) { const x = a[i] || 0, y = b[i] || 0; if (x !== y) return x - y; }
  return 0;
}
function evalBest(cards) {
  const n = cards.length; let best = null;
  for (let a = 0; a < n - 4; a++) for (let b = a + 1; b < n - 3; b++) for (let c = b + 1; c < n - 2; c++)
    for (let d = c + 1; d < n - 1; d++) for (let e = d + 1; e < n; e++) {
      const s = evalScore5([cards[a], cards[b], cards[c], cards[d], cards[e]]);
      if (!best || scoreCmp(s, best) > 0) best = s;
    }
  return best;
}
function equityMC(hero, board, nOpp, iters) {
  const used = new Set(hero.concat(board).map(c => c.r * 4 + c.s));
  const baseDeck = [];
  for (let r = 2; r <= 14; r++) for (let s = 0; s < 4; s++) if (!used.has(r * 4 + s)) baseDeck.push({ r, s });
  const needRun = 5 - board.length, need = nOpp * 2 + needRun;
  const deck = baseDeck.slice();
  let share = 0;
  for (let it = 0; it < iters; it++) {
    for (let i = 0; i < need; i++) {
      const j = i + Math.floor(Math.random() * (deck.length - i));
      const t = deck[i]; deck[i] = deck[j]; deck[j] = t;
    }
    const fullBoard = board.concat(deck.slice(0, needRun));
    const hs = evalBest(hero.concat(fullBoard));
    let beaten = false, ties = 0;
    for (let o = 0; o < nOpp; o++) {
      const os = evalBest([deck[needRun + o * 2], deck[needRun + o * 2 + 1]].concat(fullBoard));
      const c = scoreCmp(os, hs);
      if (c > 0) { beaten = true; break; }
      if (c === 0) ties++;
    }
    if (!beaten) share += 1 / (1 + ties);
  }
  return share / iters;
}
const C = (r, s) => ({ r, s });
const t0 = Date.now();
console.log('AA  K72     HU  ' + (equityMC([C(14,0),C(14,1)], [C(13,2),C(7,3),C(2,0)], 1, 30000) * 100).toFixed(1) + '%   (eval7: 88.8%)');
console.log('AA  K72     8w  ' + (equityMC([C(14,0),C(14,1)], [C(13,2),C(7,3),C(2,0)], 7, 8000) * 100).toFixed(1) + '%   (eval7: 42.7%)');
console.log('AsKs Qs7s2h HU  ' + (equityMC([C(14,0),C(13,0)], [C(12,0),C(7,0),C(2,1)], 1, 30000) * 100).toFixed(1) + '%   (eval7: 72.5%)');
console.log('AsKs Qs7s2h 8w  ' + (equityMC([C(14,0),C(13,0)], [C(12,0),C(7,0),C(2,1)], 7, 8000) * 100).toFixed(1) + '%   (eval7: 42.1%)');
console.log('elapsed', Date.now() - t0, 'ms');
