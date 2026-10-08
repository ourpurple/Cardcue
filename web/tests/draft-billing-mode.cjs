const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { chromium } = require(process.env.CARDCUE_PLAYWRIGHT_MODULE || 'playwright');

// Serve only the built frontend. Every API request is mocked, so this test
// cannot reach the user's backend or change real accounts/statements.
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


const id = index => `00000000-0000-4000-8000-${String(index).padStart(12, '0')}`;
const account = (index, mode = null) => ({
  id: id(index), bank: '广发银行', alias: null, holder: `合成用户${index}`,
  reference: null, billing_mode: mode, billing_mode_source: mode ? 'manual_override' : null,
  revision: index + 2, cards: [{ id: id(index + 100), tail: `${1000 + index}`,
    display_name: null, status: 'active' }],
});
function draft(accounts) {
  return {
    id: id(500), status: 'pending_review', revision: 2, bank: '广发银行', currency: 'CNY',
    amount_minor: 2317, minimum_minor: 2317, statement_date: '2026-10-06', due_date: '2026-10-26',
    account_reference: null, card_tails: ['1001'], evidence: [], review_reasons: [],
    matched_account_id: accounts[0].id, matched_card_id: accounts[0].cards[0].id,
    confirmed_version_id: null, rejection_reason: null, extractor_name: 'model',
    detail_status: 'none', transactions: [], candidate_accounts: accounts, candidate_cards: [],
    matched_account: accounts[0], matched_card: accounts[0].cards[0], source_email: null,
    source_manifest: null, created_at: '2026-10-07T01:00:00Z', updated_at: null,
  };
}
(async () => {
  let browser;
  try {
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const base = `http://127.0.0.1:${server.address().port}`;
    browser = await chromium.launch({ headless: true, executablePath: process.env.CARDCUE_CHROMIUM_PATH || undefined });
    let passed = 0;
    async function scenario(name, accounts, action, behavior = 'success') {
      const context = await browser.newContext({ viewport: { width: 1600, height: 1050 } });
      const page = await context.newPage();
      page.setDefaultTimeout(8000);
      const confirms = [], saves = [], errors = [];
      page.on('pageerror', error => errors.push(error.message));
      const data = draft(accounts);
      await page.addInitScript(() => {
        sessionStorage.setItem('cardcue_csrf', 'synthetic-csrf');
        sessionStorage.setItem('cardcue_user', 'synthetic-admin');
      });
      await page.route('**/v1/**', async route => {
        const req = route.request();
        const pathname = new URL(req.url()).pathname;
        const respond = (json, status = 200) => route.fulfill({ json, status });
        if (pathname === `/v1/admin/drafts/${data.id}/confirm`) {
          confirms.push(req.postDataJSON());
          assert.equal(req.method(), 'POST');
          assert.equal(req.headers()['x-csrf-token'], 'synthetic-csrf');
          if (behavior === 'network') return route.abort('failed');
          if (behavior === 'legacy-error') return respond({ detail: 'Repayment mode requires manual confirmation' }, 409);
          if (behavior === 'stale') return respond({ detail: '账户已被其他操作修改，请重新打开草稿核对还款模式' }, 409);
          data.status = 'confirmed';
          return respond({ draft_id: data.id, statement_id: id(600), status: 'confirmed' });
        }
        if (pathname === `/v1/admin/drafts/${data.id}`) {
          if (req.method() === 'PUT') {
            saves.push(req.postDataJSON());
            data.revision += 1;
            return respond({ ok: true, revision: data.revision });
          }
          return respond(data);
        }
        if (pathname === '/v1/admin/drafts') return respond({ items: data.status === 'confirmed' ? [] : [data], total: data.status === 'confirmed' ? 0 : 1 });
        return respond({ items: [], total: 0 });
      });
      try {
        await page.goto(base + '/drafts');
        await page.getByRole('button', { name: '审核入账' }).click();
        await page.getByLabel('识别银行名称').waitFor();
        await action({ page, confirms, saves });
        assert.deepEqual(errors, []);
        console.log(`PASS ${name}`);
        passed++;
      } finally {
        await context.close();
      }
    }
    const confirm = page => page.getByRole('button', { name: /确认入账/ }).click();
    const choose = async (page, mode = 'per_card') => {
      await page.getByLabel('账户还款模式', { exact: true }).click();
      await page.getByTitle(mode === 'per_card' ? '独立还款（此账户仅对应一张有效卡片）' : '合并还款（同一账户多卡共用账单）', { exact: true }).click();
    };
    await scenario('unknown mode has no default and prevents submit', [account(1)], async ({ page, confirms }) => {
      await page.getByText('账户还款模式待人工确认', { exact: true }).waitFor();
      await page.getByText('请依据银行账单人工选择', { exact: true }).waitFor();
      await confirm(page);
      await page.getByText('请选择独立还款或合并还款，不会自动推断', { exact: true }).waitFor();
      assert.equal(confirms.length, 0);
      assert.equal(await page.locator('.ant-message-notice').count(), 0);
    });
    for (const mode of ['per_card', 'consolidated']) {
      await scenario(`explicit ${mode} sent with current account revision and exact amount`, [account(1)], async ({ page, confirms }) => {
        await choose(page, mode);
        await confirm(page);
        await page.getByText('草稿已通过并生成正式账单与待还款项', { exact: true }).waitFor();
        assert.equal(confirms.length, 1);
        assert.equal(confirms[0].confirmed_billing_mode, mode);
        assert.equal(confirms[0].expected_account_revision, 3);
        assert.equal(confirms[0].account_id, id(1));
        assert.equal(confirms[0].amount_minor, 2317);
        assert.equal(confirms[0].minimum_minor, 2317);
        assert.equal(confirms[0].expected_revision, 2);
        assert.equal(confirms[0].details_complete, false);
        assert.deepEqual(confirms[0].confirm_transaction_ids, []);
      });
    }
    await scenario('known mode is shown but not changed by submission', [account(1, 'consolidated')], async ({ page, confirms }) => {
      await page.getByText('账户还款模式：合并还款', { exact: true }).waitFor();
      assert.equal(await page.getByLabel('账户还款模式', { exact: true }).count(), 0);
      await confirm(page);
      await page.getByText('草稿已通过并生成正式账单与待还款项', { exact: true }).waitFor();
      assert.equal(confirms[0].confirmed_billing_mode, null);
      assert.equal(confirms[0].expected_account_revision, 3);
    });
    await scenario('changing account clears previous manual choice', [account(1), account(2)], async ({ page, confirms }) => {
      await choose(page);
      await page.locator('.ant-select-selector').filter({ has: page.getByLabel('归属账户与卡片 (必填)') }).click();
      await page.getByText('广发 合成用户2 1002', { exact: true }).click();
      await page.getByText('请依据银行账单人工选择', { exact: true }).waitFor();
      await confirm(page);
      await page.getByText('请选择独立还款或合并还款，不会自动推断', { exact: true }).waitFor();
      assert.equal(confirms.length, 0);
      await choose(page, 'consolidated');
      await confirm(page);
      await page.getByText('草稿已通过并生成正式账单与待还款项', { exact: true }).waitFor();
      assert.equal(confirms[0].account_id, id(2));
      assert.equal(confirms[0].expected_account_revision, 4);
    });
    await scenario('saving draft does not persist account mode and reopening clears it', [account(1)], async ({ page, saves }) => {
      await choose(page);
      await page.getByRole('button', { name: /暂存修改/ }).click();
      await page.getByText('草稿内容已暂存', { exact: true }).waitFor();
      await page.getByText('请依据银行账单人工选择', { exact: true }).waitFor();
      assert.equal(saves.length, 1);
      assert.equal(Object.hasOwn(saves[0], 'confirmed_billing_mode'), false);
      assert.equal(Object.hasOwn(saves[0], 'billing_mode'), false);
    });
    for (const [behavior, text] of [
      ['stale', '账户已被其他操作修改，请重新打开草稿核对还款模式'],
      ['network', '网络通信异常，请检查网络或后端服务连接'],
      ['legacy-error', '请先人工确认账户还款模式；若页面没有选项，请更新后台并刷新页面'],
    ]) {
      await scenario(`${behavior} shows one error and preserves review`, [account(1)], async ({ page, confirms }) => {
        await choose(page);
        await confirm(page);
        await page.getByText(text, { exact: true }).waitFor();
        assert.equal(await page.locator('.ant-message-notice-error').count(), 1);
        assert.equal(confirms.length, 1);
        assert.equal(await page.getByRole('button', { name: /确认入账/ }).isVisible(), true);
        assert.equal(await page.getByLabel('账单应还总额 (元)').inputValue(), '23.17');
      }, behavior);
    }
    console.log(`${passed} browser checks passed (mock API only)`);
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
