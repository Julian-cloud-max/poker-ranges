// Renders favicon.png (32x32) and apple-touch-icon.png (180x180) from an SVG.
const path = require('path');
const fs = require('fs');

const DOCS = path.resolve(__dirname, '..', 'docs');

const svg = (size) => `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="7" fill="#0d1720"/>
  <rect x="1" y="1" width="30" height="30" rx="6" fill="none" stroke="#1b2a36" stroke-width="1"/>
  <text x="16" y="23" font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="17"
        font-weight="700" fill="#7ee7c7" text-anchor="middle">A</text>
</svg>`;

(async () => {
  const { default: puppeteer } = await import('file:///C:/Users/easttech/node_modules/puppeteer/lib/puppeteer/puppeteer.js');
  const browser = await puppeteer.launch({
    headless: 'new',
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args: ['--no-sandbox'],
  });
  const page = await browser.newPage();

  for (const [size, name] of [[32, 'favicon.png'], [180, 'apple-touch-icon.png']]) {
    await page.setViewport({ width: size, height: size, deviceScaleFactor: 1 });
    const tmp = path.join(__dirname, 'fav.html');
    fs.writeFileSync(tmp, `<!doctype html><html><body style="margin:0">${svg(size)}</body></html>`, 'utf8');
    await page.goto('file:///' + tmp.split(path.sep).join('/'), { waitUntil: 'load' });
    await page.screenshot({ path: path.join(DOCS, name), omitBackground: true, type: 'png' });
    fs.unlinkSync(tmp);
    console.log('wrote', name, size + 'x' + size);
  }
  await browser.close();
})();
