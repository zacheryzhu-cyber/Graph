// UI walkthrough of the UPW demo. Run with the server up: python upw_demo/server.py, then node upw_demo/tests/ui_smoke.js
// Prints each step's engine verdicts; screenshots go to out/.
const { chromium } = require('playwright');
const URL = process.env.URL || 'http://127.0.0.1:8766/';
(async () => {
  const b = await chromium.launch(); const pg = await b.newPage({ viewport: { width: 1400, height: 1000 } });
  const errs = []; pg.on('pageerror', e => errs.push(e.message)); pg.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  await pg.goto(URL); await pg.waitForTimeout(2500);
  const pills = async () => (await pg.$$eval('.eng', els => els.map(e => e.querySelector('.name').textContent + ': ' + (e.querySelector('.pill')?.textContent || '-') + ' | ' + (e.querySelector('.summary')?.textContent || ''))));
  console.log('Q1', await pills());
  await pg.screenshot({ path: 'out/upw_1.png', fullPage: true });
  const n = (await pg.$$('.step')).length;
  for (let i = 1; i < n; i++) { await pg.click(`.step[data-i="${i}"]`); await pg.waitForTimeout(1500); console.log('step', i, await pg.$eval('#stTitle', e => e.textContent), await pills()); }
  await pg.screenshot({ path: 'out/upw_step6.png' });
  await pg.click('.step[data-i="2"]'); await pg.waitForTimeout(1200);
  await pg.selectOption('#p_asset', 'RO-2'); await pg.waitForTimeout(1500); console.log('Q2 RO-2', await pills());
  await pg.selectOption('#p_asset', 'UV-1'); await pg.waitForTimeout(1500); console.log('Q2 UV-1', await pills());
  await pg.click('.step[data-i="4"]'); await pg.waitForTimeout(1200);
  await pg.selectOption('#p_src', 'CITY'); await pg.waitForTimeout(1500); console.log('Q4 CITY', await pills());
  await pg.click('.step[data-i="5"]'); await pg.waitForTimeout(1200);
  await pg.selectOption('#p_filter', 'include reclaim pipes'); await pg.waitForTimeout(1500); console.log('Q6 reclaim', await pills());
  await pg.hover('.node[data-id="MBP-B"]'); await pg.waitForTimeout(300); console.log('tip', (await pg.$eval('#tip', e => e.textContent)).slice(0, 160));
  await pg.screenshot({ path: 'out/upw_tip.png' });
  console.log('width', await pg.evaluate(() => [document.documentElement.scrollWidth, innerWidth]));
  const ph = await b.newPage({ viewport: { width: 390, height: 844 } }); await ph.goto(URL); await ph.waitForTimeout(2500);
  console.log('phone width', await ph.evaluate(() => [document.documentElement.scrollWidth, innerWidth]));
  await ph.screenshot({ path: 'out/upw_phone.png' });
  console.log('errors', errs); await b.close();
})();
