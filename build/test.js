const path = require('path');

const FILE = 'file:///' + path.resolve(__dirname, '..', 'docs', 'index.html').split(path.sep).join('/');
const fails = [];
function ok(cond, msg) { if (!cond) fails.push(msg); }
const wait = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const { default: puppeteer } = await import('file:///C:/Users/easttech/node_modules/puppeteer/lib/puppeteer/puppeteer.js');
  const browser = await puppeteer.launch({
    headless: 'new',
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args: ['--allow-file-access-from-files', '--no-sandbox'],
  });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.setViewport({ width: 1440, height: 1000 });
  await page.goto(FILE, { waitUntil: 'networkidle0' });
  await wait(400);

  // 1. exactly 169 unique cells
  const cells = await page.$$eval('[data-hand]', els => els.map(e => e.dataset.hand));
  ok(cells.length === 169, 'expected 169 cells, got ' + cells.length);
  ok(new Set(cells).size === 169, 'duplicate cells: ' + (cells.length - new Set(cells).size));

  // 2. default BTN RFI actions
  const aaAct = await page.$eval('[data-hand="AA"]', e => e.dataset.act);
  ok(aaAct === 'raise', 'AA should be raise on BTN RFI, got ' + aaAct);
  const foldAct = await page.$eval('[data-hand="72o"]', e => e.dataset.act);
  ok(foldAct === 'fold', '72o should fold on BTN RFI, got ' + foldAct);

  // 3. every cell label matches its own data attribute
  const mismatch = await page.$$eval('[data-hand]', els =>
    els.filter(e => e.dataset.hand !== e.querySelector('.hc-hand').textContent).map(e => e.dataset.hand));
  ok(mismatch.length === 0, 'label mismatch: ' + mismatch.slice(0, 5));

  // 4. rail = 8 positions, displayed BB → UTG
  const railN = await page.$$eval('#rail [data-pos]', e => e.length);
  ok(railN === 8, 'rail should have 8, got ' + railN);
  const railOrder = await page.$$eval('#rail [data-pos]', els => els.map(e => e.dataset.pos).join(','));
  ok(railOrder === 'BB,SB,BTN,CO,HJ,MP,UTG+1,UTG', 'rail order should run BB→UTG, got ' + railOrder);
  const sumOrder = await page.$$eval('#summaryBody [data-pos]', els => els.map(e => e.dataset.pos).join(','));
  ok(sumOrder === 'BB,SB,BTN,CO,HJ,MP,UTG+1,UTG', 'summary rows should run BB→UTG, got ' + sumOrder);

  // 5. scenario availability per seat
  const seats = ['UTG', 'UTG+1', 'MP', 'HJ', 'CO', 'BTN', 'SB', 'BB'];
  const report = {};
  for (const s of seats) {
    await page.click('#rail [data-pos="' + s + '"]');
    await wait(90);
    await page.evaluate(() => {
      const t = document.querySelector('#scenarioTabs [data-sc="vs"]');
      if (t && !t.disabled) t.click();
    });
    await wait(90);
    report[s] = await page.evaluate(() => ({
      tabs: [...document.querySelectorAll('#scenarioTabs [data-sc]')].map(t => ({
        sc: t.dataset.sc, sel: t.getAttribute('aria-selected'), dis: t.disabled })),
      chips: [...document.querySelectorAll('#bucketRow [data-bk]')].map(c => c.dataset.bk),
    }));
  }
  for (const s of seats) {
    const rfi = report[s].tabs.find(t => t.sc === 'rfi');
    const vs = report[s].tabs.find(t => t.sc === 'vs');
    if (s === 'BB') {
      ok(rfi.dis, 'BB should have RFI disabled');
      ok(!vs.dis, 'BB should have vs-open enabled');
    } else if (s === 'UTG') {
      ok(!rfi.dis, 'UTG should have RFI enabled');
      ok(vs.dis, 'UTG must have no vs-open spot (nobody acts before it)');
      ok(report[s].chips.length === 0, 'UTG should have 0 buckets, got ' + report[s].chips);
    } else {
      ok(!rfi.dis && !vs.dis, s + ' should have both scenarios');
    }
  }
  ok(report['UTG+1'].chips.join() === 'EP', 'UTG+1 chips ' + report['UTG+1'].chips);
  ok(report['HJ'].chips.join() === 'EP', 'HJ chips ' + report['HJ'].chips);
  ok(report['CO'].chips.join() === 'EP,LP', 'CO chips ' + report['CO'].chips);
  ok(report['BTN'].chips.join() === 'EP,LP', 'BTN chips ' + report['BTN'].chips);
  ok(report['SB'].chips.join() === 'EP,LP', 'SB chips ' + report['SB'].chips);
  ok(report['BB'].chips.join() === 'EP,LP,SB', 'BB chips ' + report['BB'].chips);

  // 6. displayed equity matches dataset
  await page.click('#rail [data-pos="BTN"]');
  await page.evaluate(() => document.querySelector('#scenarioTabs [data-sc="rfi"]').click());
  await wait(90);
  const eqAA = await page.$eval('[data-hand="AA"] .hc-eq', e => parseFloat(e.textContent));
  ok(Math.abs(eqAA - 85.2) < 0.11, 'AA eq shown ' + eqAA + ', expected 85.2');

  // 7. equity mode recolours
  await page.click('#viewToggle [data-view="equity"]');
  await wait(120);
  const heat = await page.$$eval('[data-act="raise"]', els => els.map(e => e.dataset.heat));
  ok(heat.length > 0 && heat.every(h => h === '1'), 'raise cells should all be heat=1 in equity mode');
  const style = await page.$eval('[data-hand="AA"]', e => e.getAttribute('style') || '');
  ok(/--heat-bg/.test(style), 'equity mode should set --heat-bg, got ' + style);
  await page.click('#viewToggle [data-view="action"]');

  // 8. deep link round trip
  await page.goto(FILE + '#SB/vs/LP/AA', { waitUntil: 'networkidle0' });
  await wait(300);
  const deep = await page.evaluate(() => {
    const chip = document.querySelector('#bucketRow [aria-pressed="true"]');
    return {
      pos: document.getElementById('dPosCode').textContent.trim(),
      scenario: [...document.querySelectorAll('#scenarioTabs [data-sc]')]
        .find(t => t.getAttribute('aria-selected') === 'true').dataset.sc,
      bucket: chip ? chip.dataset.bk : null,
      hand: document.getElementById('dHandClass').textContent.trim(),
    };
  });
  ok(deep.pos === 'SB', 'deep pos ' + deep.pos);
  ok(deep.scenario === 'vs', 'deep scenario ' + deep.scenario);
  ok(deep.bucket === 'LP', 'deep bucket ' + deep.bucket);
  ok(deep.hand === 'AA', 'deep hand ' + deep.hand);

  // 9. detail renders in every seat/scenario
  await page.goto(FILE, { waitUntil: 'networkidle0' });
  const bad = [];
  for (const s of seats) {
    for (const sc of ['rfi', 'vs']) {
      await page.evaluate((seat, scen) => {
        document.querySelector('#rail [data-pos="' + seat + '"]').click();
        const t = [...document.querySelectorAll('#scenarioTabs [data-sc]')].find(x => x.dataset.sc === scen);
        if (t && !t.disabled) t.click();
      }, s, sc);
      await wait(70);
      const n = await page.evaluate(() => {
        const el = document.querySelector('[data-hand="AKo"]');
        if (!el) return -1;
        el.click();
        return document.getElementById('dHand').querySelectorAll('.stat-bar').length;
      });
      if (n !== -1 && n < 2) bad.push(s + '/' + sc + ':' + n);
    }
  }
  ok(bad.length === 0, 'detail bars missing: ' + bad.slice(0, 6));

  // 10. no horizontal overflow at 390px
  await page.setViewport({ width: 390, height: 844 });
  await page.goto(FILE, { waitUntil: 'networkidle0' });
  await wait(350);
  const over = await page.evaluate(() => ({
    doc: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    wide: [...document.querySelectorAll('body *')]
      .filter(e => e.getBoundingClientRect().right > window.innerWidth + 1)
      .slice(0, 5).map(e => e.tagName + '.' + (e.className && e.className.baseVal !== undefined ? e.className.baseVal : e.className)),
  }));
  ok(over.doc <= 1, 'page overflows horizontally by ' + over.doc + 'px: ' + over.wide);

  // 11. deploy readiness: meta tags resolve to real URLs, og image exists
  const meta = await page.evaluate(() => {
    const get = sel => { const e = document.querySelector(sel); return e ? e.getAttribute('content') || e.getAttribute('href') : null; };
    return {
      ogImage: get('meta[property="og:image"]'),
      ogUrl: get('meta[property="og:url"]'),
      canonical: get('link[rel="canonical"]'),
      twitter: get('meta[name="twitter:card"]'),
      desc: get('meta[name="description"]'),
      icon: get('link[rel="icon"]'),
    };
  });
  ok(!/__SITE_URL__/.test(JSON.stringify(meta)), 'unreplaced placeholder in meta: ' + JSON.stringify(meta));
  ok(meta.ogImage && meta.ogImage.startsWith('https://'), 'og:image is not absolute https: ' + meta.ogImage);
  ok(meta.canonical && meta.canonical.startsWith('https://'), 'canonical is not absolute https');
  ok(meta.twitter === 'summary_large_image', 'twitter card wrong: ' + meta.twitter);
  ok(!!meta.desc, 'missing meta description');
  ok(meta.icon === 'favicon.png', 'favicon href wrong: ' + meta.icon);
  ok(require('fs').existsSync(path.resolve(__dirname, '..', 'docs', 'favicon.png')), 'favicon.png missing from docs/');
  ok(require('fs').existsSync(path.resolve(__dirname, '..', 'docs', 'apple-touch-icon.png')), 'apple-touch-icon.png missing');
  ok(meta.ogImage.endsWith('og.png') && require('fs').existsSync(path.resolve(__dirname, '..', 'docs', 'og.png')),
     'og.png referenced but not present in docs/');

  // build id resolves (no unreplaced placeholder)
  const buildId = await page.$eval('#buildId', e => e.textContent.trim());
  ok(/^[0-9a-f]{7,}$|^\d{4}-\d{2}-\d{2}$/.test(buildId), 'build id should resolve, got "' + buildId + '"');

  // 12. postflop decision tree
  await page.click('#modeToggle [data-view="post"]');
  await wait(150);
  ok(await page.$eval('#postWrap', e => !e.classList.contains('hidden')), 'post view should be visible');
  ok(await page.$eval('#preWrap', e => e.classList.contains('hidden')), 'pre view should be hidden');
  const lines = await page.$$eval('#postLines [data-line]', els => els.map(e => e.dataset.line));
  ok(lines.length === 4, 'expected 4 lines, got ' + lines.length);
  const texes = await page.$$eval('#postTextures [data-tex]', els => els.map(e => e.dataset.tex));
  ok(texes.length === 7, 'expected 7 textures, got ' + texes.length);
  ok(new Set(texes).size === 7, 'duplicate texture cards');
  const deckN = await page.$$eval('#postDeck .dk', els => els.length);
  ok(deckN === 52, 'expected 52 deck cards, got ' + deckN);

  // strategy card must be complete for every line × texture (4×7 = 28)
  let cardFail = [];
  for (const ln of lines) {
    for (const tx of texes) {
      await page.evaluate(([l, t]) => {
        document.querySelector(`#postLines [data-line="${l}"]`).click();
        document.querySelector(`#postTextures [data-tex="${t}"]`).click();
      }, [ln, tx]);
      await wait(30);
      const blocks = await page.$$eval('#postStreets .street-block .tx',
        els => els.map(e => e.textContent.trim()));
      if (blocks.length !== 3 || blocks.some(b => !b || b === '—')) cardFail.push(ln + '/' + tx);
    }
  }
  ok(cardFail.length === 0, 'incomplete strategy cards: ' + cardFail.slice(0, 5));

  // classifier: hand auto-brought (AA) then pick K♦ 7♣ 2♠ → high-dry
  await page.evaluate(() => {
    const pick = (rk, st) => document.querySelector(`#postDeck .dk[data-r="${rk}"][data-s="${st}"]`).click();
    pick(13, 2); pick(7, 3); pick(2, 0);   // K♦ 7♣ 2♠（A♠A♥ 已被自动带入的手牌占用）
  });
  await wait(120);
  const cls = await page.$eval('#postClassifyHint', e => e.textContent);
  ok(cls.includes('高张干燥'), 'K72 should classify 高张干燥, got: ' + cls);
  ok(await page.$eval('#postTextures [data-tex="high-dry"]', e => e.classList.contains('is-active')),
     'classifier should select the classified texture');

  // 12b. table size switching (2-9)
  {
    const jsClick = sel => page.evaluate(s => { document.querySelector(s).click(); }, sel);
    // 上面分类器测试结束时还停在翻后视图；人数切换在翻后模式下不动位置栏，先切回翻前
    await jsClick('#modeToggle [data-view="pre"]');
    await wait(150);
    const sizes = await page.$$eval('#sizeToggle [data-size]', els => els.map(e => e.dataset.size));
    ok(sizes.join() === '2,3,4,5,6,7,8,9', 'size buttons should list 2..9, got ' + sizes);
    ok(await page.$eval('#sizeToggle [data-size="8"]', e => e.getAttribute('aria-pressed')) === 'true',
       'size 8 should be active by default');

    // 6-max: 6 seats, BTN stays selected
    await jsClick('#sizeToggle [data-size="6"]');
    await wait(120);
    let rail = await page.$$eval('#rail [data-pos]', els => els.map(e => e.dataset.pos).join(','));
    ok(rail === 'BB,SB,BTN,CO,HJ,UTG', '6-max rail should be BB..UTG, got ' + rail);
    ok((await page.$eval('#dPosCode', e => e.textContent.trim())) === 'BTN', 'BTN should stay selected at 6-max');
    let pct = await page.$eval('#dPlayPct', e => parseFloat(e.textContent));
    ok(pct > 40 && pct < 47, '6-max BTN open% should be 40-47, got ' + pct);
    ok((await page.$eval('#viewHint', e => e.textContent)).includes('6 人桌'), 'hint should mention 6 人桌');

    // 9-max: 9 seats incl UTG+2; UTG tightest
    await jsClick('#sizeToggle [data-size="9"]');
    await wait(120);
    rail = await page.$$eval('#rail [data-pos]', els => els.map(e => e.dataset.pos).join(','));
    ok(rail === 'BB,SB,BTN,CO,HJ,MP,UTG+2,UTG+1,UTG', '9-max rail got ' + rail);
    await jsClick('#rail [data-pos="UTG"]');
    await wait(100);
    pct = await page.$eval('#dPlayPct', e => parseFloat(e.textContent));
    ok(pct > 10.5 && pct < 13, '9-max UTG open% should be ~11.9, got ' + pct);

    // fallback: UTG does not exist at 5-max -> fall back to HJ
    await jsClick('#sizeToggle [data-size="5"]');
    await wait(120);
    ok((await page.$eval('#dPosCode', e => e.textContent.trim())) === 'HJ',
       'switching 9->5 while on UTG should fall back to HJ');
    rail = await page.$$eval('#rail [data-pos]', els => els.map(e => e.dataset.pos).join(','));
    ok(rail === 'BB,SB,BTN,CO,HJ', '5-max rail got ' + rail);

    // HU: 2 seats, BTN opens very wide, detail shows no separate pot-share row
    await jsClick('#sizeToggle [data-size="2"]');
    await wait(120);
    rail = await page.$$eval('#rail [data-pos]', els => els.map(e => e.dataset.pos).join(','));
    ok(rail === 'BB,BTN', 'HU rail got ' + rail);
    await jsClick('#rail [data-pos="BTN"]');
    await wait(100);
    pct = await page.$eval('#dPlayPct', e => parseFloat(e.textContent));
    ok(pct > 75, 'HU BTN open% should be >75, got ' + pct);
    const detailTxt = await page.$eval('#dHand', e => e.textContent);
    ok(!detailTxt.includes('2 人底池'), 'HU should not duplicate the heads-up bar');

    // deep links with size segment
    await page.goto(FILE + '#6/BTN', { waitUntil: 'networkidle0' });
    await wait(400);
    ok((await page.$eval('#sizeToggle [aria-pressed="true"]', e => e.dataset.size)) === '6', '#6/BTN should select size 6');
    ok((await page.$eval('#dPosCode', e => e.textContent.trim())) === 'BTN', '#6/BTN should select BTN');
    await page.goto(FILE + '#9/UTG+2', { waitUntil: 'networkidle0' });
    await wait(400);
    ok((await page.$eval('#dPosCode', e => e.textContent.trim())) === 'UTG+2', '#9/UTG+2 should select UTG+2');
    await page.goto(FILE + '#BTN/vs/LP/A5s', { waitUntil: 'networkidle0' });
    await wait(400);
    ok((await page.$eval('#sizeToggle [aria-pressed="true"]', e => e.dataset.size)) === '8',
       'legacy link without size should default to 8');

    // postflop still works after size switching; hand bring intact
    await jsClick('#modeToggle [data-view="post"]');
    await wait(200);
    const h = await page.evaluate(() => post.hand.map(c => c.r + '.' + c.s).join(','));
    ok(h === '14.0,5.0', 'hand should still be brought (A5s) after size switches, got ' + h);
    await jsClick('#modeToggle [data-view="pre"]');
    await wait(150);

    // restore default size for any checks that follow
    await jsClick('#sizeToggle [data-size="8"]');
    await wait(120);
  }

  // 13. hand follows the preflop selection (no manual hand entry)
  // 自带初始化：刷新页面（默认手牌 AA），进翻后，点 K♦ 7♣ 2♠
  await page.goto(FILE, { waitUntil: 'networkidle0' });
  await page.evaluate(() => document.querySelector('#modeToggle [data-view="post"]').click());
  await wait(250);
  await page.evaluate(() => {
    const pick = (rk, st) => document.querySelector(`#postDeck .dk[data-r="${rk}"][data-s="${st}"]`).click();
    pick(13, 2); pick(7, 3); pick(2, 0);
  });
  await wait(300);
  // AA on K72 → 超对 (overpair), equity within eval7 tolerance, advice mentions value
  const handPanel = await page.$eval('#postHandBody', e => e.textContent);
  ok(handPanel.includes('超对'), 'AA on K72 should be 超对, got: ' + handPanel.slice(0, 120));
  ok(handPanel.includes('价值'), 'role label should appear');
  // equity resolves within 5s and matches eval7 reference (88.8% HU / 42.7% 8-way) within tolerance
  await page.waitForFunction(
    () => [...document.querySelectorAll('#postHandBody .mono')].filter(e => /%$/.test(e.textContent.trim())).length >= 2,
    { timeout: 5000 });
  const eqTxt = await page.$$eval('#postHandBody .mono', els => els.map(e => e.textContent.trim()));
  const huVal = parseFloat(eqTxt[0].replace('%', ''));
  const mwVal = parseFloat(eqTxt[1].replace('%', ''));
  ok(huVal > 85 && huVal < 92.5, 'AA overpair on K72 heads-up equity should be 85~92.5%, got ' + huVal);
  ok(mwVal > 37 && mwVal < 49, 'AA overpair on K72 8-way share should be 37~49%, got ' + mwVal);

  // core regression: picking a different hand in the preflop view must propagate
  await page.click('#modeToggle [data-view=pre]');
  await page.evaluate(() => document.querySelector('[data-hand="KQs"]').click());
  await wait(150);
  await page.click('#modeToggle [data-view=post]');
  await wait(200);
  const afterSwitch = await page.evaluate(() => post.hand.map(c => c.r + '.' + c.s).join(','));
  ok(afterSwitch === '13.0,12.0', 'preflop KQs should propagate to postflop hand, got ' + afterSwitch);

  // flush draw case: preflop AKs + board Q♠ 7♠ 2♥ → nut flush draw
  await page.click('#modeToggle [data-view=pre]');
  await page.evaluate(() => document.querySelector('[data-hand="AKs"]').click());
  await wait(150);
  await page.click('#modeToggle [data-view=post]');
  await wait(200);
  await page.click('#postClear');
  await wait(100);
  await page.evaluate(() => {
    const pick = (rk, st) => document.querySelector(`#postDeck .dk[data-r="${rk}"][data-s="${st}"]`).click();
    pick(12, 0); pick(7, 0); pick(2, 1);
  });
  await wait(200);
  const fdPanel = await page.$eval('#postHandBody', e => e.textContent);
  ok(fdPanel.includes('坚果同花听牌') || fdPanel.includes('同花听牌'),
     'AKs on Q♠7♠2♥ should show flush draw, got: ' + fdPanel.slice(0, 160));
  await page.waitForFunction(
    () => [...document.querySelectorAll('#postHandBody .mono')].filter(e => /%$/.test(e.textContent.trim())).length >= 1,
    { timeout: 5000 });

  // hand is read-only: no cycling control, deck hand cards are inert, visuals differ
  const hasCyc = await page.$eval('#postPick', el => !!el.querySelector('[data-cyc]'));
  ok(!hasCyc, 'hand slots must not offer suit cycling');
  const suitsBefore = await page.evaluate(() => post.hand.map(c => c.s).join(','));
  await page.evaluate(() => {
    const el = document.querySelector('#postDeck .dk.is-mine');
    if (el) el.click();
  });
  await wait(80);
  const suitsAfter = await page.evaluate(() => post.hand.map(c => c.s).join(','));
  ok(suitsBefore === suitsAfter, 'hand must not be changeable from postflop view: ' + suitsBefore + ' -> ' + suitsAfter);
  const styling = await page.evaluate(() => {
    const h = document.querySelector('#postPick .pcard-slot.mine');
    const b = document.querySelector('#postPick .pcard-slot.full:not(.mine)');
    return {
      handBorder: h ? getComputedStyle(h).borderColor : null,
      boardBorder: b ? getComputedStyle(b).borderColor : null,
      mineInDeck: !!document.querySelector('#postDeck .dk.is-mine'),
    };
  });
  ok(styling.handBorder && styling.boardBorder && styling.handBorder !== styling.boardBorder,
     'hand slots and board slots should be visually distinct: ' + JSON.stringify(styling));
  ok(styling.mineInDeck, 'hand cards should be marked in the deck');

  // clear clears the board but keeps the hand
  await page.click('#postClear');
  await wait(100);
  const cleared = await page.evaluate(() => ({ board: post.board.length, hand: post.hand.length }));
  ok(cleared.board === 0 && cleared.hand === 2, 'clear should empty board only, got ' + JSON.stringify(cleared));

  // top pair: preflop AKo + K♦ 7♣ 2♠ → 顶对踢脚A
  await page.click('#modeToggle [data-view=pre]');
  await page.evaluate(() => document.querySelector('[data-hand="AKo"]').click());
  await wait(150);
  await page.click('#modeToggle [data-view=post]');
  await wait(200);
  await page.evaluate(() => {
    const pick = (rk, st) => document.querySelector(`#postDeck .dk[data-r="${rk}"][data-s="${st}"]`).click();
    pick(13, 2); pick(7, 3); pick(2, 0);
  });
  await wait(200);
  const tpPanel = await page.$eval('#postHandBody', e => e.textContent);
  ok(tpPanel.includes('顶对') && tpPanel.includes('踢脚 A'), 'AKo on K72 should be 顶对踢脚A, got: ' + tpPanel.slice(0, 160));
  // advice changes with the line: switch to caller line, role advice should differ from aggressor
  const flopAgg = await page.$eval('#postHandBody .street-block .tx', e => e.textContent);
  await page.click('#postLines [data-line="caller"]');
  await wait(120);
  const flopCaller = await page.$eval('#postHandBody .street-block .tx', e => e.textContent);
  ok(flopAgg !== flopCaller, 'role advice should change between aggressor and caller lines');

  // deep link into postflop
  await page.goto(FILE + '#post/caller/low-connected', { waitUntil: 'networkidle0' });
  await wait(400);
  ok(await page.$eval('#postWrap', e => !e.classList.contains('hidden')), 'post deep link should open post view');
  const deepLine = await page.$eval('#postLines [aria-pressed="true"]', e => e.dataset.line);
  ok(deepLine === 'caller', 'post deep link line ' + deepLine);
  const deepTex = await page.$eval('#postTextures [aria-pressed="true"]', e => e.dataset.tex);
  ok(deepTex === 'low-connected', 'post deep link texture ' + deepTex);

  // back to preflop keeps working
  await page.goto(FILE + '#BTN/vs/LP/A5s', { waitUntil: 'networkidle0' });
  await wait(400);
  ok(await page.$eval('#preWrap', e => !e.classList.contains('hidden')), 'preflop deep link should open pre view');
  ok(await page.$eval('#postWrap', e => e.classList.contains('hidden')), 'preflop deep link should hide post view');

  await browser.close();
  if (errors.length) fails.push('JS errors: ' + [...new Set(errors)].join(' | '));
  if (fails.length) { console.log('FAIL\n - ' + fails.join('\n - ')); process.exit(1); }
  console.log('ALL PASS');
})();
