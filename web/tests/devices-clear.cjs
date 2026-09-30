const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { chromium } = require(process.env.CARDCUE_PLAYWRIGHT_MODULE || 'playwright');

// Serve only the built frontend. Every API request is mocked, so this test
// cannot reach the user's backend or remove real devices.
const dist = path.resolve(__dirname, '../dist');
const server = http.createServer((req, res) => {
  const pathname = new URL(req.url, 'http://localhost').pathname;
  if (pathname.startsWith('/v1/')) {
    res.writeHead(500).end('Unexpected unmocked API request');
    return;
  }
  const file = pathname.startsWith('/assets/')
    ? path.resolve(dist, '.' + pathname) : path.join(dist, 'index.html');
  if (!file.startsWith(dist + path.sep)) {
    res.writeHead(403).end();
    return;
  }
  const type = file.endsWith('.js') ? 'text/javascript'
    : file.endsWith('.css') ? 'text/css' : 'text/html';
  fs.readFile(file, (err, bytes) => {
    if (err) res.writeHead(404).end();
    else res.writeHead(200, { 'content-type': type }).end(bytes);
  });
});

function device(index, status = 'revoked') {
  return {
    id: `synthetic-device-${index}`, name: `测试设备 ${index}`, status,
    paired_at: '2026-09-30T00:00:00Z', last_seen_at: null,
    revoked_at: status === 'revoked' ? '2026-09-30T01:00:00Z' : null,
  };
}

(async () => {
  let browser;
  try {
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const base = `http://127.0.0.1:${server.address().port}`;
    browser = await chromium.launch({ headless: true, executablePath: process.env.CARDCUE_CHROMIUM_PATH || undefined });
    let passed = 0;
    async function scenario(name, initialRows, action, behavior = 'success') {
      const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      const page = await context.newPage();
      let rows = initialRows;
      const clears = [];
      let reads = 0;
      let release;
      const pending = new Promise(resolve => { release = resolve; });
      await page.addInitScript(() => {
        sessionStorage.setItem('cardcue_csrf', 'synthetic-csrf');
        sessionStorage.setItem('cardcue_user', 'synthetic-admin');
      });
      await page.route('**/v1/**', async route => {
        const request = route.request();
        const pathname = new URL(request.url()).pathname;
        const respond = (data, status = 200) => route.fulfill({ status, json: data });
        if (pathname === '/v1/admin/devices/clear-revoked') {
          clears.push(request);
          assert.equal(request.method(), 'POST');
          if (behavior === 'network') return route.abort('failed');
          if (behavior === 'server-error') return respond({ detail: '合成清理失败' }, 500);
          if (behavior === 'delayed') await pending;
          if (behavior === 'already-cleared') rows = rows.filter(d => d.status !== 'revoked');
          const deleted = rows.filter(d => d.status === 'revoked' || d.revoked_at != null);
          rows = rows.filter(d => !deleted.includes(d));
          return respond({ deleted_count: deleted.length });
        }
        if (pathname === '/v1/admin/devices') {
          reads++;
          if (behavior === 'load-error' || (behavior === 'reload-error' && reads > 1)) return route.abort('failed');
          return respond(rows);
        }
        return respond({ items: [], total: 0 });
      });
      try {
        await page.goto(base + '/devices');
        await page.getByRole('button', { name: '刷新设备' }).waitFor();
        if (behavior === 'load-error') await page.getByText('设备列表加载失败，请刷新后再清理').waitFor();
        else if (rows.length) await page.getByText(rows[0].name, { exact: true }).waitFor();
        else await page.locator('.ant-empty-description').getByText('暂无数据', { exact: true }).waitFor();
        await action({ page, clears, release, reads: () => reads });
        console.log(`PASS ${name}`);
        passed++;
      } finally {
        release();
        await context.close();
      }
    }
    const clearButton = page => page.getByRole('button', { name: /清除已吊销设备/ }).first();
    const openConfirm = async page => {
      await clearButton(page).click();
      await page.getByText('确定清除所有已吊销设备吗？', { exact: true }).waitFor();
      await page.getByText('仅删除已吊销设备记录，不影响已授权设备、账单和还款记录；已有审计记录保留。此操作不可撤销。').waitFor();
    };
    const confirm = page => page.locator('.ant-popconfirm').getByRole('button', { name: /清除已吊销设备/ }).click();

    await scenario('empty list disables cleanup', [], async ({ page, clears }) => {
      assert.equal(await clearButton(page).isDisabled(), true);
      assert.equal(clears.length, 0);
    });
    await scenario('active-only devices are not treated as revoked', [device(1, 'active')], async ({ page }) => {
      assert.equal(await clearButton(page).isDisabled(), true);
      await page.getByText('已授权', { exact: true }).waitFor();
      assert.equal(await page.getByRole('button', { name: /吊销授权/ }).count(), 1);
      assert.equal(await page.getByText('Invalid Date', { exact: true }).count(), 0);
    });
    await scenario('cancel never sends deletion', [device(1)], async ({ page, clears }) => {
      await openConfirm(page);
      await page.locator('.ant-popconfirm').getByRole('button', { name: /取\s*消/ }).click();
      assert.equal(clears.length, 0);
      assert.equal(await page.locator('tbody tr.ant-table-row').count(), 1);
    });
    await scenario('cleanup preserves active devices and sends CSRF', [device(1), device(2, 'active'), device(3)], async ({ page, clears, reads }) => {
      assert.match(await clearButton(page).innerText(), /（2）/);
      await openConfirm(page);
      await confirm(page);
      await page.getByText('已清除 2 台已吊销设备', { exact: true }).waitFor();
      await page.waitForFunction(() => document.querySelectorAll('tbody tr.ant-table-row').length === 1);
      await page.getByText('测试设备 2', { exact: true }).waitFor();
      assert.equal(clears.length, 1);
      assert.equal(clears[0].headers()['x-csrf-token'], 'synthetic-csrf');
      assert.equal(reads(), 2);
      assert.equal(await clearButton(page).isDisabled(), true);
    });
    await scenario('unknown status is not cleanup eligible and invalid date is guarded', [{ ...device(1, 'pending'), paired_at: 'invalid' }], async ({ page }) => {
      assert.equal(await clearButton(page).isDisabled(), true);
      await page.getByText('未知状态', { exact: true }).waitFor();
      await page.getByText('未知', { exact: true }).waitFor();
      assert.equal(await page.getByText('Invalid Date', { exact: true }).count(), 0);
    });
    await scenario('revocation timestamp overrides active status', [{ ...device(1, 'active'), revoked_at: '2026-09-30T01:00:00Z' }], async ({ page }) => {
      assert.equal(await clearButton(page).isDisabled(), false);
      await page.getByText('已吊销', { exact: true }).waitFor();
      assert.equal(await page.getByRole('button', { name: /吊销授权/ }).count(), 0);
    });
    for (const behavior of ['network', 'server-error']) {
      await scenario(`${behavior} preserves devices`, [device(1)], async ({ page, clears }) => {
        await openConfirm(page);
        await confirm(page);
        await page.getByText(behavior === 'network' ? '网络通信异常，请检查网络或后端服务连接' : '合成清理失败', { exact: true }).waitFor();
        assert.equal(clears.length, 1);
        assert.equal(await page.locator('tbody tr.ant-table-row').count(), 1);
      }, behavior);
    }
    await scenario('pending request disables duplicate cleanup and refresh', [device(1), device(2, 'active')], async ({ page, clears, release }) => {
      await openConfirm(page);
      await confirm(page);
      await page.waitForFunction(() => !!document.querySelector('.ant-btn-loading'));
      assert.equal(await clearButton(page).isDisabled(), true);
      assert.equal(await page.getByRole('button', { name: '刷新设备' }).isDisabled(), true);
      assert.equal(await page.getByRole('button', { name: /吊销授权/ }).isDisabled(), true);
      assert.equal(clears.length, 1);
      release();
      await page.getByText('已清除 1 台已吊销设备', { exact: true }).waitFor();
    }, 'delayed');
    await scenario('stale list handles already-cleared devices', [device(1), device(2, 'active')], async ({ page, clears }) => {
      await openConfirm(page);
      await confirm(page);
      await page.getByText('没有需要清除的已吊销设备', { exact: true }).waitFor();
      await page.waitForFunction(() => document.querySelectorAll('tbody tr.ant-table-row').length === 1);
      assert.equal(clears.length, 1);
    }, 'already-cleared');
    await scenario('initial load error prevents cleanup', [device(1)], async ({ page, clears }) => {
      assert.equal(await clearButton(page).isDisabled(), true);
      assert.equal(clears.length, 0);
    }, 'load-error');
    await scenario('failed reload blocks stale-list cleanup', [device(1)], async ({ page }) => {
      await openConfirm(page);
      await confirm(page);
      await page.getByText('已清除 1 台已吊销设备', { exact: true }).waitFor();
      await page.getByText('设备列表加载失败，请刷新后再清理').waitFor();
      assert.equal(await clearButton(page).isDisabled(), true);
    }, 'reload-error');
    console.log(`${passed} browser checks passed (mock API only)`);
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
