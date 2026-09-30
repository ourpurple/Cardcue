const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { chromium } = require(process.env.CARDCUE_PLAYWRIGHT_MODULE || 'playwright');

// Serve only the built frontend. Every API request is mocked, so this test
// cannot reach the user's backend or remove real tasks.
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

function job(index) {
  return {
    id: `synthetic-task-${index}`, kind: 'sync', target_id: 'synthetic-mailbox',
    status: 'queued', attempts: 0, cancel_requested: false, result: null,
    error_code: null, created_at: '2026-09-30T00:00:00Z',
    started_at: null, finished_at: null,
  };
}

(async () => {
  let browser;
  try {
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const base = `http://127.0.0.1:${server.address().port}`;
    browser = await chromium.launch({ headless: true, executablePath: process.env.CARDCUE_CHROMIUM_PATH || undefined });
    let passed = 0;

    async function scenario(name, count, action, behavior = 'success') {
      const context = await browser.newContext();
      const page = await context.newPage();
      let rows = Array.from({ length: count }, (_, i) => job(i));
      const requests = [];
      const clears = [];
      await page.addInitScript(() => {
        sessionStorage.setItem('cardcue_csrf', 'synthetic-csrf');
        sessionStorage.setItem('cardcue_user', 'synthetic-admin');
      });
      await page.route('**/v1/**', async route => {
        const request = route.request();
        const url = new URL(request.url());
        const respond = (data, status = 200) => route.fulfill({ status, json: data });
        if (url.pathname === '/v1/admin/jobs/clear') {
          clears.push(request);
          if (behavior === 'conflict') return respond({ detail: '存在执行中的任务，请先取消并等待执行结束后再清除' }, 409);
          if (behavior === 'network') return route.abort('failed');
          if (behavior === 'delayed') await new Promise(resolve => setTimeout(resolve, 300));
          const deleted_count = rows.length;
          rows = [];
          return respond({ deleted_count });
        }
        if (url.pathname === '/v1/admin/jobs') {
          const current = Number(url.searchParams.get('page'));
          const size = Number(url.searchParams.get('size'));
          requests.push(current);
          return respond({ items: rows.slice((current - 1) * size, current * size), total: rows.length });
        }
        return respond({ items: [], total: 0 });
      });
      const state = { page, clears, requests };
      try {
        await page.goto(base + '/jobs');
        await page.getByRole('button', { name: '刷新队列' }).waitFor();
        if (count) await page.waitForFunction(expected => document.querySelectorAll('tbody tr.ant-table-row').length === expected, Math.min(count, 20));
        else await page.locator('.ant-empty-description').getByText('暂无数据', { exact: true }).waitFor();
        await action(state);
        console.log(`PASS ${name}`);
        passed++;
      } finally {
        await context.close();
      }
    }

    const openConfirm = async page => {
      await page.getByRole('button', { name: /清除所有任务/ }).click();
      await page.getByText('确定清除所有任务队列吗？', { exact: true }).waitFor();
      await page.getByText('不会删除邮件、草稿、账单或还款记录。', { exact: false }).waitFor();
    };
    const confirm = page => page.locator('.ant-popconfirm').getByRole('button', { name: /清除所有任务/ }).click();

    await scenario('empty queue disables clear', 0, async ({ page, clears }) => {
      assert.equal(await page.getByRole('button', { name: /清除所有任务/ }).isDisabled(), true);
      assert.equal(clears.length, 0);
    });
    await scenario('cancel confirmation does not clear', 3, async ({ page, clears }) => {
      await openConfirm(page);
      await page.locator('.ant-popconfirm').getByRole('button', { name: /取\s*消/ }).click();
      assert.equal(clears.length, 0);
      assert.equal(await page.locator('tbody tr.ant-table-row').count(), 3);
    });
    await scenario('clear removes all pages and returns to page one', 25, async ({ page, clears, requests }) => {
      await page.locator('.ant-pagination-item-2').click();
      await page.waitForFunction(() => document.querySelectorAll('tbody tr.ant-table-row').length === 5);
      await openConfirm(page);
      await confirm(page);
      await page.getByText('已清除 25 个任务', { exact: true }).waitFor();
      await page.locator('.ant-empty-description').getByText('暂无数据', { exact: true }).waitFor();
      assert.equal(clears.length, 1);
      assert.equal(clears[0].headers()['x-csrf-token'], 'synthetic-csrf');
      assert.equal(requests.at(-1), 1);
      assert.equal(await page.locator('tbody tr.ant-table-row').count(), 0);
    });
    await scenario('running conflict preserves visible queue', 3, async ({ page, clears }) => {
      await openConfirm(page);
      await confirm(page);
      await page.getByText('存在执行中的任务，请先取消并等待执行结束后再清除', { exact: true }).waitFor();
      assert.equal(clears.length, 1);
      assert.equal(await page.locator('tbody tr.ant-table-row').count(), 3);
    }, 'conflict');
    await scenario('network failure preserves visible queue', 3, async ({ page, clears }) => {
      await openConfirm(page);
      await confirm(page);
      await page.getByText('网络通信异常，请检查网络或后端服务连接', { exact: true }).waitFor();
      assert.equal(clears.length, 1);
      assert.equal(await page.locator('tbody tr.ant-table-row').count(), 3);
    }, 'network');
    await scenario('clear in progress prevents conflicting refresh', 3, async ({ page, clears }) => {
      await openConfirm(page);
      await confirm(page);
      assert.equal(await page.getByRole('button', { name: '刷新队列' }).isDisabled(), true);
      await page.getByText('已清除 3 个任务', { exact: true }).waitFor();
      assert.equal(clears.length, 1);
    }, 'delayed');
    console.log(`${passed} browser checks passed (mock API only)`);
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
