// Renders an Open Graph preview image (1200x630) from the live page markup.
const path = require('path');
const SITE = 'file:///' + path.resolve(__dirname, '..', 'site', 'index.html').split(path.sep).join('/');
const OUT = path.resolve(__dirname, '..', 'site', 'og.png');

(async () => {
  const { default: puppeteer } = await import('file:///C:/Users/easttech/node_modules/puppeteer/lib/puppeteer/puppeteer.js');
  const browser = await puppeteer.launch({
    headless: 'new',
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args: ['--allow-file-access-from-files', '--no-sandbox'],
  });
  const page = await browser.newPage();

  // Build a poster that reuses the real matrix so the image matches the product.
  await page.setViewport({ width: 1200, height: 630, deviceScaleFactor: 2 });
  await page.goto(SITE, { waitUntil: 'networkidle0' });
  await new Promise(r => setTimeout(r, 600));

  const html = await page.evaluate(() => {
    const cell = document.querySelector('[data-hand="AA"]');
    const styles = [...document.querySelectorAll('style')].map(s => s.textContent).join('\n');
    const cellStyle = getComputedStyle(cell).backgroundImage;
    return { styles, cellStyle };
  });

  const poster = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
  <style>${html.styles}</style>
  <style>
    html,body{margin:0;padding:0;background:#070d12;}
    .og{width:1200px;height:630px;position:relative;overflow:hidden;
      background:
        radial-gradient(760px 380px at 8% -10%, rgba(126,231,199,.16), transparent 62%),
        radial-gradient(680px 340px at 92% -6%, rgba(240,112,90,.13), transparent 60%),
        #070d12;
      font-family:"Segoe UI","PingFang SC","Microsoft YaHei","Noto Sans SC",sans-serif;
      color:#e9f2f8; display:flex; flex-direction:column; justify-content:center;
      padding:62px 68px; box-sizing:border-box;}
    .kicker{letterspacing:.24em;font-size:15px;color:#61798a;text-transform:uppercase;letter-spacing:.24em}
    h1{font-size:74px;line-height:1.08;margin:16px 0 0;font-weight:600;letter-spacing:-.02em}
    h1 em{font-style:normal;color:#7ee7c7}
    .sub{font-size:23px;line-height:1.55;color:#93a9b8;margin-top:20px;max-width:560px}
    .stats{display:flex;gap:44px;margin-top:34px}
    .stat b{display:block;font-size:33px;font-weight:600;color:#e9f2f8;line-height:1}
    .stat span{font-size:15px;color:#61798a;margin-top:6px;display:block}
    .grid{position:absolute;right:-150px;top:46%;transform:translateY(-50%) rotate(-8deg);
      display:grid;grid-template-columns:repeat(6,74px);gap:7px;opacity:.9}
    .g{aspect-ratio:1/1;border-radius:9px;display:flex;align-items:center;justify-content:center;
      font-size:15px;font-weight:600;color:#fff8f5}
    .r{background:linear-gradient(157deg,#f0705a,#bd3d29)}
    .c{background:repeating-linear-gradient(135deg,rgba(0,0,0,.16) 0 3px,transparent 3px 7px),linear-gradient(157deg,#46c393,#1d7659);color:#effff9}
    .f{background:#0f1a23;border:1px solid #16242f;color:#5d7586}
    .badge{position:absolute;left:68px;bottom:40px;font-size:15px;color:#4d6879;letter-spacing:.02em}
  </style></head><body>
  <div class="og">
    <div class="kicker">8-max · no-limit hold'em · preflop</div>
    <h1>八人桌<em>开池范围</em>表</h1>
    <div class="sub">八个位置该玩哪些牌、该加注还是跟注，<br>以及每手牌的真实胜率。</div>
    <div class="stats">
      <div class="stat"><b>169</b><span>起手牌</span></div>
      <div class="stat"><b>8</b><span>位置</span></div>
      <div class="stat"><b>1326</b><span>组合</span></div>
    </div>
    <div class="grid">
      ${[['AA','r'],['AKs','r'],['AQs','r'],['AJs','r'],['ATs','r'],['A9s','r'],
         ['AKo','r'],['KK','r'],['KQs','r'],['KJs','r'],['KTs','r'],['K9s','c'],
         ['AQo','r'],['KQo','r'],['QQ','r'],['QJs','r'],['QTs','c'],['Q9s','c'],
         ['AJo','c'],['KJo','c'],['QJo','c'],['JJ','r'],['JTs','c'],['J9s','f'],
         ['ATo','c'],['KTo','f'],['QTo','f'],['JTo','c'],['TT','r'],['T9s','c'],
         ['A9o','f'],['K9o','f'],['Q9o','f'],['J9o','f'],['T9o','c'],['99','r']]
        .map(([h,k]) => `<div class="g ${k}">${h}</div>`).join('')}
    </div>
    <div class="badge">eval7 蒙特卡洛 · 每手牌 12 万次模拟</div>
  </div></body></html>`;

  const tmp = path.resolve(__dirname, 'og.html');
  require('fs').writeFileSync(tmp, poster, 'utf8');
  await page.goto('file:///' + tmp.split(path.sep).join('/'), { waitUntil: 'networkidle0' });
  await new Promise(r => setTimeout(r, 350));
  await page.screenshot({ path: OUT, type: 'png' });
  await browser.close();
  require('fs').unlinkSync(tmp);
  console.log('wrote', OUT);
})();
