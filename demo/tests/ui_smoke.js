// Browser smoke test of the live workbench: run it while demo/server.py is up.  node demo/tests/ui_smoke.js
const { chromium } = require('playwright');
const SP = process.argv[2] || require('path').join(__dirname, '../../out');
require('fs').mkdirSync(SP, { recursive: true });
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1360, height: 1000 } });
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  await p.goto('http://127.0.0.1:8765/');
  const pills = async () => p.$$eval('.eng', els => els.map(e => e.querySelector('.name').textContent + ': ' + (e.querySelector('.stat')?.textContent || e.querySelector('.err')?.textContent || '-')));
  await p.waitForFunction(() => document.querySelectorAll('.pill.ok, .pill.bad, .err').length >= 3, null, { timeout: 30000 });
  console.log('Q1', await pills());
  await p.screenshot({ path: SP + '/live_q1.png' });
  await p.click('.node[data-id="UPS-B01-2"]');
  await p.waitForTimeout(1500);
  console.log('trip UPS-2', await pills(), 'hit nodes', await p.$$eval('.node.hit', n => n.length));
  for (const q of ['Q2','Q3','Q4','Q5','Q6']) {
    await p.click(`.tab[data-q="${q}"]`);
    await p.waitForFunction(() => document.querySelectorAll('.pill.ok, .pill.bad, .err').length >= 3, null, { timeout: 30000 });
    console.log(q, await pills());
  }
  await p.selectOption('#claimDst', 'T-B01-107'); await p.selectOption('#claimMode', 'n10s');
  await p.click('#claimAdd'); await p.waitForTimeout(2500);
  console.log('claim n10s', await pills(), await p.textContent('#claimState'));
  await p.screenshot({ path: SP + '/live_claim.png' });
  await p.selectOption('#claimMode', 'node'); await p.click('#claimAdd'); await p.waitForTimeout(2500);
  console.log('claim node', await pills());
  await p.click('#claimDel'); await p.waitForTimeout(2000);
  await p.click('.tab[data-q="console"]'); await p.selectOption('#cEx', '1'); await p.click('#cRun'); await p.waitForTimeout(800);
  console.log('console', await p.textContent('#cStat'));
  console.log('errors', errs);
  await b.close();
})();
