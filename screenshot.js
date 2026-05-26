const { chromium } = require('playwright');
const path = require('path');

const files = [
  { html: 'package-upgrade.html', png: 'package-upgrade.png' },
  { html: 'package-basic.html',   png: 'package-basic.png'   },
  { html: 'package-compare.html', png: 'package-compare.png' },
];

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  // iPhone 14 Pro logical resolution, 3x device pixel ratio = 1170×2532 physical
  await page.setViewportSize({ width: 390, height: 844 });

  for (const { html, png } of files) {
    const url = 'file://' + path.resolve(__dirname, html);
    await page.goto(url, { waitUntil: 'networkidle' });

    // Measure actual rendered height
    const height = await page.evaluate(() => document.body.scrollHeight);

    // If content fits in one screen keep 844, else use actual height
    const viewH = Math.max(height, 844);
    await page.setViewportSize({ width: 390, height: viewH });
    await page.goto(url, { waitUntil: 'networkidle' });

    await page.screenshot({
      path: path.resolve(__dirname, png),
      fullPage: false,
      scale: 3,   // 3x → 1170px wide, iPhone physical resolution
    });
    const finalH = await page.evaluate(() => document.body.scrollHeight);
    console.log(`Done: ${png}  (logical ${390}×${viewH}, rendered height ${finalH})`);
  }

  await browser.close();
})();
