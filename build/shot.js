const path = require('path');
const FILE = 'file:///' + path.resolve(__dirname, '..', 'docs', 'index.html').split(path.sep).join('/');
(async () => {
  const { default: puppeteer } = await import('file:///C:/Users/easttech/node_modules/puppeteer/lib/puppeteer/puppeteer.js');
  const browser = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  for (const spec of process.argv.slice(2)) {
    const [hash, w, h, out] = spec.split('|');
    await page.setViewport({ width: +w, height: +h, deviceScaleFactor: 2 });
    await page.goto(FILE + (hash || ''), { waitUntil: 'networkidle0' });
    await new Promise(r => setTimeout(r, 500));
    await page.screenshot({ path: path.resolve(__dirname, '..', 'shots', out) });
    console.log('shot', out);
  }
  await browser.close();
})();
