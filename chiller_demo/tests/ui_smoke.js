// UI walkthrough of the chiller demo. Run with the server up (python chiller_demo/server.py), then:
//   node chiller_demo/tests/ui_smoke.js          (URL=file:///…/page.html to test a recorded edition)
// Prints each step's engine verdicts; screenshots go to out/.
const { chromium } = require('playwright');
const URL = process.env.URL || 'http://127.0.0.1:8766/';
(async () => {
  const b = await chromium.launch(); const pg = await b.newPage({ viewport: { width: 1400, height: 1000 } });
  const errs = []; pg.on('pageerror', e => errs.push(e.message)); pg.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  await pg.goto(URL); await pg.waitForTimeout(2500);
  const pills = async () => (await pg.$$eval('.eng', els => els.map(e => e.querySelector('.name').textContent + ': ' + (e.querySelector('.pill')?.textContent || '-') + ' | ' + (e.querySelector('.summary')?.textContent || ''))));
  await pg.screenshot({ path: 'out/chiller_1.png', fullPage: true });
  const n = (await pg.$$('.step')).length;
  for (let i = 1; i < n; i++) { await pg.click(`.step[data-i="${i}"]`); await pg.waitForTimeout(1800); console.log('step', i, await pg.$eval('#stTitle', e => e.textContent), await pills()); }
  await pg.screenshot({ path: 'out/chiller_step6.png' });
  await pg.click('.step[data-i="2"]'); await pg.waitForTimeout(1500);
  for (const u of ['CHW-HDR', 'CH-1']) { await pg.selectOption('#p_unit', u); await pg.waitForTimeout(1500); console.log('Q2', u, await pills()); }
  await pg.click('.step[data-i="3"]'); await pg.waitForTimeout(1200);
  await pg.selectOption('#p_chiller', 'CH-1'); await pg.waitForTimeout(1200); console.log('Q3 CH-1', await pills());
  await pg.click('.step[data-i="4"]'); await pg.waitForTimeout(1500);
  for (const v of ['normal', 'hx2-isolated']) { await pg.selectOption('#valveSel', v); await pg.waitForTimeout(1800); console.log('Q4', v, await pills(), (await pg.$eval('#valveState', e => e.textContent)).slice(0, 220)); }
  await pg.hover('.node[data-id="P-B1"]'); await pg.waitForTimeout(300); console.log('tip', (await pg.$eval('#tip', e => e.textContent)).slice(0, 160));
  console.log('score', (await pg.$eval('#score', e => e.innerText)).replace(/\s+/g, ' ').slice(0, 900));
  await pg.screenshot({ path: 'out/chiller_full.png', fullPage: true });
  console.log('width', await pg.evaluate(() => [document.documentElement.scrollWidth, innerWidth]));
  const ph = await b.newPage({ viewport: { width: 390, height: 844 } }); await ph.goto(URL); await ph.waitForTimeout(2500);
  console.log('phone width', await ph.evaluate(() => [document.documentElement.scrollWidth, innerWidth]));
  console.log('errors', errs); await b.close();
})();
