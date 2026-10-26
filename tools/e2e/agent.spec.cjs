// Browser contract tests: real sandbox API/model/work orders, stubbed LLM replies.
// Real DeepSeek runs are separately recorded by evaluate_agent --live.
const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const webUrl = process.env.E2E_WEB_URL || 'http://127.0.0.1:5173';
const apiUrl = process.env.E2E_API_URL || 'http://127.0.0.1:8000/api';
test.skip(process.env.AGENT_E2E !== '1', 'Requires the explicit isolated Agent sandbox.');

async function login(page, role = 'operator') {
  const passwords = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../../.agent-eval/users.json'), 'utf8'));
  await page.context().addInitScript(url => localStorage.setItem('vue-api-url', url), apiUrl);
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill(`agent-eval-${role}`);
  await page.getByLabel('密码', { exact: true }).fill(passwords[role]);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await expect(page.getByRole('heading', { name: '运行，一眼掌握' })).toBeVisible();
  await page.getByRole('button', { name: '打开 AI 助手' }).click();
  await expect(page.locator('.ai-agent-context')).toContainText('模拟测试');
}

test('31路来源标记、五站与同站目标定位通过实际V17模型验证', async ({ page }) => {
  await login(page);
  await page.getByRole('button', { name: '五站31路巡检', exact: true }).click();
  await expect(page.locator('.ai-agent-inspection')).toContainText('模拟场景观测可用 31/31');
  await expect(page.locator('.ai-agent-inspection')).toContainText('所需观测可用 0/31');
  const targets = ['SMOKE-01', 'MQ4-02', 'MQ4-03', 'MQ4-04', 'MQ4-05', 'CO-05'];
  for (let index = 0; index < targets.length; index++) {
    if (index) await page.getByRole('button', { name: '打开 AI 助手' }).click();
    await page.getByText('设备与三维入口（31）', { exact: true }).click();
    await page.getByRole('button', { name: `查看 ${targets[index]}`, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`asset=${targets[index]}`));
    await expect(page.locator('.twin-inspector')).toContainText(targets[index]);
    await expect(page.locator('.twin-scene')).toHaveAttribute('data-model-state', 'loaded', { timeout: 45000 });
  }
});

test('明确设备草案、取消、确认、同键重试及返回编号复核', async ({ page }) => {
  await login(page);
  const tasks = [];
  let creationCount = 0;
  const createKeys = [];
  await page.route('**/api/assistant/chat/', async route => {
    const payload = route.request().postDataJSON(); tasks.push(payload.task);
    const proposal = { kind: 'work_order', assetCode: 'MQ4-05', title: '浏览器模拟：核查P5',
      description: '浏览器验收使用模拟模型响应，不下发硬件。', priority: 'normal', requires_confirmation: true };
    await route.fulfill({ json: { reply: '【模拟测试】等待人工审阅。', proposals: payload.task?.kind === 'draft' ? [proposal] : [],
      runtime: { layoutVersion: 'four-controller-20261026.1', dataContext: { mode: 'simulated_test', label: '模拟测试 · 浏览器响应桩' },
        providerModels: [], modelCalls: 0, tokens: null, cost: null } } });
  });
  await page.route('**/api/work-orders/', async route => {
    if (route.request().method() !== 'POST') return route.continue();
    createKeys.push(route.request().headers()['idempotency-key']);
    const response = await route.fetch();
    if (creationCount++ === 0) {
      // The server has committed; drop the browser response to simulate uncertainty.
      await route.abort('failed');
    } else await route.fulfill({ response });
  });
  await page.getByLabel('选择草案设备').selectOption('MQ4-05');
  await page.getByRole('button', { name: '生成处置草案', exact: true }).click();
  await page.getByRole('button', { name: '审阅并确认创建', exact: true }).click();
  await page.getByRole('button', { name: '取消', exact: true }).click();
  expect(creationCount).toBe(0);
  await page.getByRole('button', { name: '审阅并确认创建', exact: true }).click();
  await page.getByRole('button', { name: '确认创建', exact: true }).click();
  await expect(page.locator('.ai-agent-confirm')).toContainText('同一幂等键');
  await page.getByRole('button', { name: '确认创建', exact: true }).click();
  await expect(page.locator('.ai-agent-proposal')).toContainText('已创建：');
  expect(createKeys).toHaveLength(2); expect(createKeys[0]).toBe(createKeys[1]);
  await page.getByRole('button', { name: '复核这张工单', exact: true }).click();
  await expect.poll(() => tasks.at(-1)?.kind).toBe('review');
  expect(tasks[0]).toEqual({ kind: 'draft', asset_code: 'MQ4-05' });
  expect(tasks.at(-1).work_order_code).toMatch(/^WO-/);
});

test('窄屏保持来源、任务入口和输入区域可用；查看者不可提交草案', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, 'viewer');
  await expect(page.getByRole('button', { name: '生成处置草案', exact: true })).toBeDisabled();
  await expect(page.getByLabel('输入问题', { exact: true })).toBeVisible();
  const box = await page.getByRole('dialog', { name: 'AI 助手', exact: true }).boundingBox();
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.y + box.height).toBeLessThanOrEqual(844);
  const logHeight = await page.locator('.ai-assistant-log').evaluate(el => el.clientHeight);
  expect(logHeight).toBeGreaterThan(50);
});

test('浅色助手滚动后固定，手机和平板保留任务与输入入口', async ({ page }) => {
  await login(page);
  await expect(page.locator('.data-availability')).toContainText('模拟测试');
  const launcher = page.getByRole('button', { name: '打开 AI 助手' });
  expect(await launcher.evaluate(el => el.parentElement.tagName)).toBe('BODY');
  const before = await launcher.boundingBox();
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(100);
  const after = await launcher.boundingBox();
  expect(Math.abs(after.y - before.y)).toBeLessThan(1);
  expect(Math.abs(after.x - before.x)).toBeLessThan(1);

  // Measure readable text against its actual rendered background, not CSS names.
  const colors = await page.locator('.ai-agent-context').evaluate(el => {
    const style = getComputedStyle(el);
    return { text: style.color, background: style.backgroundColor };
  });
  function luminance(rgb) {
    const channels = rgb.match(/[\d.]+/g).slice(0, 3).map(Number).map(value => {
      const x = value / 255; return x <= 0.04045 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4;
    });
    return .2126 * channels[0] + .7152 * channels[1] + .0722 * channels[2];
  }
  const a = luminance(colors.text), b = luminance(colors.background);
  expect((Math.max(a, b) + .05) / (Math.min(a, b) + .05)).toBeGreaterThanOrEqual(4.5);
  await page.screenshot({ path: test.info().outputPath('integrated-assistant-desktop.png') });
  for (const viewport of [{ width: 800, height: 600 }, { width: 390, height: 844 }, { width: 390, height: 640 }]) {
    await page.setViewportSize(viewport);
    const panel = await page.getByRole('dialog', { name: 'AI 助手', exact: true }).boundingBox();
    const input = await page.getByLabel('输入问题', { exact: true }).boundingBox();
    expect(panel.y).toBeGreaterThanOrEqual(0);
    expect(panel.y + panel.height).toBeLessThanOrEqual(viewport.height);
    expect(input.y + input.height).toBeLessThanOrEqual(panel.y + panel.height);
    await expect(page.getByRole('button', { name: '排查检测点', exact: true })).toBeVisible();
    await expect(page.getByLabel('选择草案设备')).toBeVisible();
    expect(await page.locator('.ai-assistant-log').evaluate(el => el.clientHeight)).toBeGreaterThanOrEqual(50);
    if (viewport.width === 390 && viewport.height === 844)
      await page.screenshot({ path: test.info().outputPath('integrated-assistant-mobile.png') });
  }
});

test('来源核验失败时仪表盘不把API在线记录写成现场数据', async ({ page }) => {
  await page.route('**/api/assistant/context/', route => route.fulfill({ status: 503, json: { message: 'test context unavailable' } }));
  const passwords = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../../.agent-eval/users.json'), 'utf8'));
  await page.context().addInitScript(url => localStorage.setItem('vue-api-url', url), apiUrl);
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('agent-eval-operator');
  await page.getByLabel('密码', { exact: true }).fill(passwords.operator);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await expect(page.locator('.data-availability')).toContainText('数据来源待核实');
  await expect(page.locator('.data-availability')).not.toContainText('现场设备有在线数据');
});

test('合并后的11个业务页面保留浅色布局与导航', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route(/https?:\/\/(?:[^/]+\.)?tile\.openstreetmap\.org\/.*/i, route => route.fulfill({
    status: 200, contentType: 'image/png',
    body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64'),
  }));
  await login(page, 'administrator');
  await page.getByRole('button', { name: '关闭 AI 助手', exact: true }).click();
  for (const [route, heading, navigation] of [['/dashboard', '运行，一眼掌握', '运行总览'], ['/alerts', '告警中心', '告警中心'], ['/work-orders', '工单中心', '工单中心'],
    ['/assets', '设备台账', '设备台账'], ['/twin-3d', '三维孪生中心', '三维孪生'], ['/gis', 'GIS 空间运维总览', 'GIS 总览'], ['/telemetry', '数据洞察', '数据洞察'],
    ['/asset-admin', '资产主数据', '资产配置'], ['/gis-admin', '空间数据管理', '空间配置'], ['/settings', '系统配置', '系统配置'], ['/audit', '审计追踪', '审计追踪']]) {
    await page.locator('.command-nav').getByRole('button', { name: navigation, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`${route}$`));
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1441);
    expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).toBe('rgb(242, 246, 251)');
    if (route === '/twin-3d') await expect(page.locator('.twin-scene')).toHaveAttribute('data-model-state', 'loaded', { timeout: 45000 });
  }
  expect(errors).toEqual([]);
});

test('真实模型网页闭环（显式付费开关，需先重置独立验收库）', async ({ page }) => {
  test.skip(process.env.AGENT_LIVE_E2E !== '1', 'Paid calls require AGENT_LIVE_E2E=1; ordinary CI skips this case.');
  test.setTimeout(180000);
  const records = [];
  let writes = 0;
  page.on('request', request => {
    if (request.url().endsWith('/api/work-orders/') && request.method() === 'POST') writes++;
  });
  async function chat(click) {
    const pending = page.waitForResponse(response => response.url().endsWith('/api/assistant/chat/')
      && response.request().method() === 'POST', { timeout: 65000 });
    await click();
    const response = await pending;
    const body = await response.json();
    records.push({ task: response.request().postDataJSON().task, httpStatus: response.status(), response: body });
    expect(response.status()).toBe(200);
    expect(body.runtime.providerModels.length).toBeGreaterThan(0);
    expect(body.reply).toContain('模拟测试');
    return body;
  }
  try {
    await login(page);
    await page.getByRole('button', { name: '五站31路巡检', exact: true }).click();
    await expect(page.locator('.ai-agent-inspection')).toContainText('模拟场景观测可用 31/31');
    await page.getByLabel('选择排障检测点').selectOption('P5');
    await chat(() => page.getByRole('button', { name: '排查检测点', exact: true }).click());
    await page.getByLabel('选择草案设备').selectOption('MQ4-05');
    const draft = await chat(() => page.getByRole('button', { name: '生成处置草案', exact: true }).click());
    expect(draft.proposals).toHaveLength(1);
    expect(draft.proposals[0].assetCode).toBe('MQ4-05');
    expect(writes).toBe(0);
    await page.getByRole('button', { name: '审阅并确认创建', exact: true }).click();
    await page.getByRole('button', { name: '取消', exact: true }).click();
    expect(writes).toBe(0);
    await page.getByRole('button', { name: '审阅并确认创建', exact: true }).click();
    await page.getByRole('button', { name: '确认创建', exact: true }).click();
    await expect(page.locator('.ai-agent-proposal')).toContainText('已创建：');
    expect(writes).toBe(1);
    await chat(() => page.getByRole('button', { name: '复核这张工单', exact: true }).click());
    expect(records.at(-1).task.work_order_code).toMatch(/^WO-/);
  } finally {
    fs.writeFileSync(path.resolve(__dirname, `../../.agent-eval/browser-live-${Date.now()}.json`),
      JSON.stringify({ confirmation: 'TEST_PROGRAM_CLICK_NOT_HUMAN', naturalLanguageFactReview: 'PENDING', records }, null, 2));
  }
});
