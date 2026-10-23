// End-to-end verification against the live GitHub Pages URL.
const URL_SITE = 'https://julian-cloud-max.github.io/poker-ranges/';
const fails = [];
const ok = (c, m) => { if (!c) fails.push(m); };
const wait = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const { default: puppeteer } = await import('file:///C:/Users/easttech/node_modules/puppeteer/lib/puppeteer/puppeteer.js');
  const browser = await puppeteer.launch({
    headless: 'new',
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args: ['--no-sandbox'],
  });
  const page = await browser.newPage();
  const errors = [];
  const failedReqs = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('requestfailed', r => failedReqs.push(r.url() + ' ' + r.failure()?.errorText));

  await page.setViewport({ width: 1440, height: 1000 });

  const resp = await page.goto(URL_SITE, { waitUntil: 'networkidle0', timeout: 60000 });
  ok(resp.status() === 200, 'live status ' + resp.status());
  await wait(600);

  // core render
  const cells = await page.$$eval('[data-hand]', els => els.map(e => e.dataset.hand));
  ok(cells.length === 169, 'live: expected 169 cells, got ' + cells.length);
  ok(new Set(cells).size === 169, 'live: duplicate cells');

  const aa = await page.$eval('[data-hand="AA"]', e => e.dataset.act);
  ok(aa === 'raise', 'live: AA should be raise on BTN, got ' + aa);
  const eq = await page.$eval('[data-hand="AA"] .hc-eq', e => parseFloat(e.textContent));
  ok(Math.abs(eq - 85.2) < 0.11, 'live: AA equity ' + eq);

  // every position switchable, no errors
  for (const s of ['UTG', 'UTG+1', 'MP', 'HJ', 'CO', 'BTN', 'SB', 'BB']) {
    await page.click('#rail [data-pos="' + s + '"]');
    await wait(70);
    const pct = await page.$eval('#dPlayPct', e => e.textContent.trim());
    ok(pct.length > 0, 'live: empty pct for ' + s);
  }

  // deep link against production
  await page.goto(URL_SITE + '#SB/vs/LP/A5s', { waitUntil: 'networkidle0' });
  await wait(500);
  const deep = await page.evaluate(() => ({
    pos: document.getElementById('dPosCode').textContent.trim(),
    hand: document.getElementById('dHandClass') ? document.getElementById('dHandClass').textContent.trim() : null,
    bucket: (document.querySelector('#bucketRow [aria-pressed="true"]') || {}).dataset?.bk,
  }));
  ok(deep.pos === 'SB', 'live deep pos ' + deep.pos);
  ok(deep.hand === 'A5s', 'live deep hand ' + deep.hand);
  ok(deep.bucket === 'LP', 'live deep bucket ' + deep.bucket);

  // meta tags as a crawler sees them
  const meta = await page.evaluate(() => {
    const g = s => { const e = document.querySelector(s); return e ? (e.getAttribute('content') || e.getAttribute('href')) : null; };
    return {
      ogImage: g('meta[property="og:image"]'),
      ogUrl: g('meta[property="og:url"]'),
      canonical: g('link[rel="canonical"]'),
      twitter: g('meta[name="twitter:card"]'),
      desc: g('meta[name="description"]'),
      icon: g('link[rel="icon"]'),
    };
  });
  ok(meta.ogImage === URL_SITE + 'og.png', 'live og:image ' + meta.ogImage);
  ok(meta.canonical === URL_SITE, 'live canonical ' + meta.canonical);
  ok(meta.icon === 'favicon.png', 'live favicon href ' + meta.icon);

  // the favicon must actually load from production
  const iconOk = await page.evaluate(u => new Promise(res => {
    const i = new Image();
    i.onload = () => res(i.naturalWidth + 'x' + i.naturalHeight);
    i.onerror = () => res('error');
    i.src = u;
  }), new URL(meta.icon, URL_SITE).href);
  ok(iconOk === '32x32', 'live favicon loaded as ' + iconOk);

  // the og image must actually load from production
  const imgOk = await page.evaluate(u => new Promise(res => {
    const i = new Image();
    i.onload = () => res(i.naturalWidth + 'x' + i.naturalHeight);
    i.onerror = () => res('error');
    i.src = u;
  }), meta.ogImage);
  ok(imgOk === '1200x630', 'live og.png loaded as ' + imgOk);

  // no external dependency besides the og image (page itself self-contained)
  const reqs = await page.evaluate(() => performance.getEntriesByType('resource').map(r => r.name));
  const external = reqs.filter(u => !u.startsWith('https://julian-cloud-max.github.io/poker-ranges/'));
  ok(external.length === 0, 'page pulls external resources: ' + external.slice(0, 3));

  // mobile
  await page.setViewport({ width: 390, height: 844 });
  await page.goto(URL_SITE, { waitUntil: 'networkidle0' });
  await wait(400);
  const over = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth);
  ok(over <= 1, 'live mobile overflows by ' + over + 'px');

  await page.screenshot({ path: 'C:/Users/easttech/.zcode/workspace/1792722993977-7136b953-c504-4758-a7fb-301e3a22aed2/live.png' });

  await browser.close();
  if (errors.length) fails.push('live JS errors: ' + [...new Set(errors)].join(' | '));
  if (failedReqs.length) fails.push('failed requests: ' + failedReqs.slice(0, 3));
  if (fails.length) { console.log('FAIL\n - ' + fails.join('\n - ')); process.exit(1); }
  console.log('LIVE ALL PASS');
})();
