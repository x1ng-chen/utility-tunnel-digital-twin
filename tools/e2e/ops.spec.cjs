const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');

const webUrl = process.env.E2E_WEB_URL || 'http://127.0.0.1:5173';
// Local regression can target the disposable API without changing frontend .env.
test.beforeEach(async ({ page }) => {
  if (process.env.E2E_API_URL) {
    await page.context().addInitScript((url) => localStorage.setItem('vue-api-url', url), process.env.E2E_API_URL);
  }
});
const adminPassword = '123';

test('历史分析跨页查询与完整 CSV 下载', async ({ page, request }) => {
  const base = process.env.E2E_API_URL || 'http://127.0.0.1:8000/api';
  const login = await request.post(`${base}/auth/login/`, { data: { email: 'admin', password: adminPassword } });
  expect(login.ok()).toBe(true);
  const token = (await login.json()).accessToken;
  const headers = { Authorization: `Bearer ${token}` };
  const run = Date.now();
  const readings = Array.from({ length: 125 }, (_, index) => ({
    eventId: `history-browser-${run}-${index}`, assetCode: 'ENV-01', metricKey: 'temperature',
    metric: '环境温度', value: 20 + index / 100, unit: '°C', quality: 'good',
    recordedAt: new Date(run - (124 - index) * 60000).toISOString(),
  }));
  for (let index = 0; index < readings.length; index += 100) {
    const result = await request.post(`${base}/telemetry/`, { headers, data: { readings: readings.slice(index, index + 100) } });
    expect(result.ok(), await result.text()).toBe(true);
  }
  const otherReading = await request.post(`${base}/telemetry/`, { headers, data: { readings: [{
    // Keep the exclusion proof within the seeded asset. Creating an extra
    // active asset here would correctly make the later GLB-contract test
    // reject the official model, but would turn this export test into hidden
    // shared state for every following workflow.
    eventId: `history-other-${run}`, assetCode: 'ENV-01', metricKey: 'export_excluded', metric: '导出排除验证指标',
    // Keep it outside the live-summary horizon. The test proves CSV filtering,
    // not a newer operational reading, so it must not replace ENV-01's current
    // temperature in subsequent operator workflows.
    value: 99, unit: 'count', quality: 'good', recordedAt: new Date(run - 24 * 60 * 60 * 1000).toISOString(),
  }] } });
  expect(otherReading.ok(), await otherReading.text()).toBe(true);
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码', { exact: true }).fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await expect(page).toHaveURL(/dashboard/);
  await page.goto(`${webUrl}/telemetry?assetCode=ENV-01&metricKey=temperature`);
  const paging = page.getByRole('navigation', { name: '历史采集记录分页' });
  await expect(paging).toContainText('第 1 / 2 页');
  await expect(page.locator('.telemetry-table .table-row')).toHaveCount(100);
  await paging.getByRole('button', { name: '下一页' }).click();
  await expect(paging).toContainText('第 2 / 2 页');
  const count = await page.locator('.telemetry-table .table-row').count();
  expect(count).toBeGreaterThanOrEqual(25);
  expect(count).toBeLessThan(100);
  await expect(paging.getByRole('button', { name: '下一页' })).toBeDisabled();
  await paging.getByRole('button', { name: '上一页' }).click();
  await expect(paging).toContainText('第 1 / 2 页');
  await expect(page.locator('.telemetry-history-chart canvas')).toBeVisible();
  await expect(page.getByRole('region', { name: '趋势时段告警事件' })).not.toContainText('加载失败');
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('button', { name: '导出全部历史记录', exact: true }).click();
  const download = await downloadEvent;
  expect(await download.failure()).toBeNull();
  expect(download.suggestedFilename()).toContain('utility-tunnel-telemetry-');
  const csv = fs.readFileSync(await download.path(), 'utf8');
  expect(csv).toContain('recorded_at');
  for (const reading of readings) expect(csv).toContain(reading.eventId);
  const filteredDownloadEvent = page.waitForEvent('download');
  await page.getByRole('button', { name: '导出当前筛选快照', exact: true }).click();
  const filteredDownload = await filteredDownloadEvent;
  expect(await filteredDownload.failure()).toBeNull();
  expect(filteredDownload.suggestedFilename()).toContain('utility-tunnel-telemetry-filtered-');
  const filteredCsv = fs.readFileSync(await filteredDownload.path(), 'utf8');
  for (const reading of readings) expect(filteredCsv).toContain(reading.eventId);
  expect(filteredCsv).not.toContain(`history-other-${run}`);
});
const mapTilePattern = /https?:\/\/(?:[^/]+\.)?tile\.openstreetmap\.org\/.*/i;
const transparentMapTile = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
  'base64',
);

async function isolateMapTiles(page) {
  await page.route(mapTilePattern, (route) => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: transparentMapTile,
  }));
}

function trackConsoleErrors(page) {
  const errors = [];
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', (error) => errors.push(error.message));
  return errors;
}

function modelUploadFor(version) {
  const original = fs.readFileSync(path.resolve(__dirname, '../../frontend/public/models/utility-tunnel.glb'));
  const jsonLength = original.readUInt32LE(12);
  const document = JSON.parse(original.subarray(20, 20 + jsonLength).toString('utf8').trimEnd());
  document.extras = { ...(document.extras || {}), regressionVersion: version };
  const encoded = Buffer.from(JSON.stringify(document), 'utf8');
  const padded = Buffer.concat([encoded, Buffer.alloc((4 - encoded.length % 4) % 4, 0x20)]);
  const jsonHeader = Buffer.alloc(8);
  jsonHeader.writeUInt32LE(padded.length, 0);
  jsonHeader.write('JSON', 4, 4, 'ascii');
  const remainingChunks = original.subarray(20 + jsonLength);
  const header = Buffer.from(original.subarray(0, 12));
  header.writeUInt32LE(12 + jsonHeader.length + padded.length + remainingChunks.length, 8);
  return { name: 'utility-tunnel.glb', mimeType: 'model/gltf-binary', buffer: Buffer.concat([header, jsonHeader, padded, remainingChunks]) };
}

test('正式账号登录后可浏览孪生资产与数据洞察', async ({ page }) => {
  const consoleErrors = trackConsoleErrors(page);
  await isolateMapTiles(page);
  await page.goto(webUrl);
  await expect(page.getByRole('heading', { name: '进入运维中枢' })).toBeVisible();
  await expect(page.getByRole('button', { name: '演示工作区' })).toHaveCount(0);
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码').fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await expect(page.getByRole('heading', { name: '运行，一眼掌握' })).toBeVisible();

  const alarmNode = page.locator('.map-node.alarm').filter({ hasText: 'FAN-01' });
  await expect(alarmNode).toHaveCount(1);
  await alarmNode.click();
  await expect(page).toHaveURL(/\/twin-3d\?asset=FAN-01/);
  await expect(page.getByRole('heading', { name: '三维孪生中心' })).toBeVisible();

  await page.getByRole('button', { name: '设备台账' }).click({ force: true });
  await expect(page.getByRole('heading', { name: '设备台账' })).toBeVisible();
  expect(await page.getByLabel('设备空间定位图').getByRole('button').count()).toBeGreaterThan(0);
  await page.getByRole('textbox', { name: '搜索设备', exact: true }).fill('SEEP-W01');
  await expect(page.getByRole('complementary').getByRole('heading', { name: '水位传感器', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '定位 水位传感器' }).click({ force: true });
  await expect(page.getByText('PC0 / ADC1_IN10', { exact: true })).toBeVisible();
  await page.getByRole('textbox', { name: '搜索设备', exact: true }).fill('NO-SUCH-ASSET');
  await expect(page.getByText('没有匹配的设备节点，请调整搜索条件。')).toBeVisible();

  await page.getByRole('button', { name: '数据洞察' }).click();
  await expect(page.getByRole('heading', { name: '数据洞察' })).toBeVisible();
  await expect(page.getByText('样本总量', { exact: true })).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test('未知页面不会空白且可以恢复到有效页面', async ({ page }) => {
  await page.goto(`${webUrl}/missing-page`);
  await expect(page.getByLabel('账号或邮箱')).toBeVisible();
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码').fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await expect(page.getByRole('heading', { name: '运行，一眼掌握' })).toBeVisible();
  for (const viewport of [{ width: 1440, height: 960 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await page.goto(`${webUrl}/missing-page/nested`);
    await expect(page.getByRole('heading', { name: '页面未找到' })).toBeVisible();
    await expect(page.locator('.page-identity strong')).toHaveText('页面未找到');
    await page.getByRole('link', { name: '返回运行总览', exact: true }).click();
    await expect(page.getByRole('heading', { name: '运行，一眼掌握' })).toBeVisible();
  }
});

test('阈值版本冲突保留草稿并允许显式载入最新值后保存', async ({ page }) => {
  let current = { key: 'temperature', label: '测试温度', unit: '℃', warning: 30, alarm: 40, version: 1 };
  const writes = [];
  await page.route('**/thresholds/', (route) => route.fulfill({ json: { items: [current] } }));
  await page.route('**/thresholds/temperature/', (route) => {
    const payload = route.request().postDataJSON();
    writes.push(payload);
    if (writes.length === 1) {
      current = { ...current, warning: 32, version: 2 };
      return route.fulfill({ status: 409, json: { detail: '配置版本已变化' } });
    }
    current = { ...current, ...payload, version: 3 };
    return route.fulfill({ json: current });
  });
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码').fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await page.getByRole('button', { name: '系统配置', exact: true }).click();
  const row = page.locator('.threshold-row').filter({ hasText: '测试温度' });
  await row.getByLabel('测试温度预警值').fill('31');
  await row.getByRole('button', { name: '保存设置', exact: true }).click();
  await expect(row.getByText('配置已更新，请核对最新值后再修改。')).toBeVisible();
  await expect(row.getByLabel('测试温度预警值')).toHaveValue('31');
  await expect(row.getByRole('button', { name: '保存设置', exact: true })).toBeDisabled();
  expect(writes).toEqual([{ warning: 31, alarm: 40, version: 1 }]);
  await row.getByRole('button', { name: '放弃草稿，载入最新值', exact: true }).click();
  await expect(row.getByLabel('测试温度预警值')).toHaveValue('32');
  await row.getByLabel('测试温度预警值').fill('33');
  await row.getByRole('button', { name: '保存设置', exact: true }).click();
  await expect(page.getByText('测试温度 已保存', { exact: true })).toBeVisible();
  expect(writes).toEqual([{ warning: 31, alarm: 40, version: 1 }, { warning: 33, alarm: 40, version: 2 }]);
});

test('滚轮到达页面边界不会跳页，导航点击仍可正常切换', async ({ page }) => {
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码').fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await expect(page.getByRole('heading', { name: '运行，一眼掌握' })).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  const viewport = page.viewportSize();
  await page.mouse.move(viewport.width / 2, viewport.height / 2);
  await page.mouse.wheel(0, 220);
  // Allow any legacy wheel debounce to fire before checking the route.
  await page.waitForTimeout(1200);
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.mouse.wheel(0, -220);
  await page.waitForTimeout(1200);
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.getByRole('navigation').getByRole('button', { name: '告警中心', exact: true }).click();
  await expect(page).toHaveURL(/\/alerts$/);
  await expect(page.getByRole('heading', { name: '告警中心' })).toBeVisible();
  await expect(page.getByRole('navigation').getByRole('button', { name: '告警中心' })).toHaveAttribute('aria-current', 'page');
});

test('三维孪生加载正式环形 V07 模型后可完整定位设备并展示告警状态', async ({ page }) => {
  // The complete model + camera + GIS + asset-ledger journey is intentionally
  // broader than the other cases. Linux CI uses software WebGL, so reserve a
  // realistic budget without weakening any of the business assertions.
  test.setTimeout(240_000);
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码').fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await page.getByRole('button', { name: '三维孪生' }).click();
  await expect(page.getByRole('heading', { name: '三维孪生中心' })).toBeVisible();
  await expect(page.getByRole('application', { name: '综合管廊三维数字孪生场景' })).toBeVisible();
  await expect(page.getByText('已加载实体三维模型')).toBeVisible();
  const canvas = page.locator('.twin-canvas canvas');
  const cameraControls = page.locator('.twin-camera-controls');
  const presetHud = page.getByRole('navigation', { name: '三维视角预设' });
  await expect(presetHud.getByText('视角预设', { exact: true })).toBeVisible();
  const presetFits = await presetHud.locator('span, button').evaluateAll((items) => items.every((item) => (
    item.scrollWidth <= item.clientWidth + 1 && item.scrollHeight <= item.clientHeight + 1
  )));
  expect(presetFits).toBe(true);
  const [presetBox, focusBox] = await Promise.all([
    presetHud.boundingBox(),
    page.locator('.twin-focus-status').boundingBox(),
  ]);
  expect(presetBox).not.toBeNull();
  expect(focusBox).not.toBeNull();
  expect(focusBox.y).toBeGreaterThanOrEqual(presetBox.y + presetBox.height + 12);
  const iconOffsets = await cameraControls.locator('button').evaluateAll((buttons) => buttons.map((button) => {
    const buttonBox = button.getBoundingClientRect();
    const iconBox = button.querySelector('svg').getBoundingClientRect();
    return {
      x: Math.abs((buttonBox.left + buttonBox.width / 2) - (iconBox.left + iconBox.width / 2)),
      y: Math.abs((buttonBox.top + buttonBox.height / 2) - (iconBox.top + iconBox.height / 2)),
    };
  }));
  expect(iconOffsets.every(({ x, y }) => x <= 1 && y <= 1)).toBe(true);
  const panMode = page.getByRole('button', { name: '启用自由平移' });
  await expect(panMode).toHaveClass(/active/);
  // Re-apply the mode through the same control an operator uses. This also
  // verifies that the active visual state and OrbitControls mapping agree.
  await panMode.click();
  const targetBeforePan = await page.locator('.twin-canvas').getAttribute('data-camera-target');
  const canvasBox = await canvas.boundingBox();
  expect(canvasBox).not.toBeNull();
  await page.mouse.move(canvasBox.x + canvasBox.width * .55, canvasBox.y + canvasBox.height * .48);
  await page.mouse.down({ button: 'left' });
  await page.mouse.move(canvasBox.x + canvasBox.width * .72, canvasBox.y + canvasBox.height * .58, { steps: 2 });
  await page.mouse.up({ button: 'left' });
  await expect.poll(() => page.locator('.twin-canvas').getAttribute('data-camera-target')).not.toBe(targetBeforePan);
  await page.getByRole('button', { name: '启用自由旋转' }).click();
  await expect(page.getByRole('button', { name: '启用自由旋转' })).toHaveClass(/active/);
  // A rotation drag can begin over a bound mesh. It must move the camera
  // without selecting that mesh and pulling the operator away from the asset
  // they were already investigating.
  const selectedBeforeRotateDrag = await page.locator('.twin-focus-status small').textContent();
  await page.mouse.move(canvasBox.x + canvasBox.width * .5, canvasBox.y + canvasBox.height * .52);
  await page.mouse.down({ button: 'left' });
  await page.mouse.move(canvasBox.x + canvasBox.width * .62, canvasBox.y + canvasBox.height * .43, { steps: 4 });
  await page.mouse.up({ button: 'left' });
  await expect(page.locator('.twin-focus-status small')).toHaveText(selectedBeforeRotateDrag || '');
  const switcher = page.locator('.twin-quick-switch');
  await expect(page.locator('.twin-model-readiness').getByText('模型已加载', { exact: true })).toBeVisible();
  const modelReadiness = page.locator('.twin-model-readiness.loaded');
  await expect(modelReadiness.getByText(/\d+ \/ \d+ 个设备已定位/, { exact: true })).toBeVisible();
  const readinessText = await modelReadiness.innerText();
  const readinessMatch = readinessText.match(/(\d+) \/ (\d+) 个设备已定位/);
  expect(readinessMatch).toBeTruthy();
  expect(readinessMatch?.[1]).toBe(readinessMatch?.[2]);
  await expect(modelReadiness.getByText('模型已加载', { exact: true })).toBeVisible();
  await expect(page.locator('.twin-model-contract').getByText(/\d+ \/ \d+ 个设备已具备标准节点名称/, { exact: true })).toBeVisible();
  await page.getByText('查看实体模型映射', { exact: true }).click();
  await expect(page.locator('.twin-model-binding-list').getByText('ENV-01', { exact: true })).toBeVisible();
  await switcher.getByRole('button', { name: '告警', exact: true }).click();
  expect(await switcher.getByRole('button', { name: /选择 / }).count()).toBeGreaterThan(0);
  await switcher.getByRole('button', { name: '全部', exact: true }).click();
  await page.getByRole('button', { name: 'ENV-01' }).click();
  const inspector = page.locator('.twin-inspector');
  await expect(inspector.locator('header code')).toContainText('ENV-01');
  await expect(inspector.getByText('运行正常', { exact: true })).toBeVisible();
  await inspector.getByRole('button', { name: '在 GIS 地图中查看' }).click();
  await expect(page).toHaveURL(/\/gis\?asset=ENV-01/);
  await expect(page.getByRole('heading', { name: 'GIS 空间运维总览' })).toBeVisible();
  await expect(page.locator('.gis-inspector').getByText('ENV-01 ·', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: '在三维中查看此设备 →' }).click();
  await expect(page).toHaveURL(/\/twin-3d\?asset=ENV-01/);
  await expect(page.locator('.twin-inspector').getByText('已从 GIS 地图定位到当前设备。', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'NET-01' }).click();
  await expect(page.locator('.twin-focus-status').getByText('ESP8266-01S 通信模块', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '设备台账' }).click({ force: true });
  await page.getByRole('button', { name: '定位 水位传感器' }).click({ force: true });
  await page.getByRole('button', { name: '在三维中查看 →' }).click();
  await expect(page).toHaveURL(/\/twin-3d\?asset=SEEP-W01/);
  await expect(page.locator('.twin-inspector').getByText('MESH_SEEP_W01', { exact: true })).toBeVisible();
});

test('告警可携带处置上下文直达三维实体模型', async ({ page }) => {
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码').fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await page.getByRole('button', { name: '告警中心' }).click();
  const firstAlert = page.locator('.table-row').filter({ hasText: 'ALM-260826-001' }).first();
  await expect(firstAlert).toBeVisible();
  await firstAlert.getByRole('button', { name: '三维定位' }).click();
  await expect(page).toHaveURL(/\/twin-3d\?asset=CTRL-01/);
  const inspector = page.locator('.twin-inspector');
  await expect(inspector.getByText('已从告警 ALM-260826-001 定位到当前设备。', { exact: true })).toBeVisible();
  await expect(inspector.locator('header code')).toContainText('CTRL-01');
  await inspector.getByRole('button', { name: '进入告警中心处置' }).click();
  await expect(page).toHaveURL(/\/alerts\?focus=ALM-260826-001/);
  await expect(page.locator('.table-row.focused').getByText('ALM-260826-001', { exact: true })).toBeVisible();
  await page.locator('.table-row.focused').getByRole('button', { name: '地图定位' }).click();
  await expect(page).toHaveURL(/\/gis\?asset=CTRL-01/);
  const gisInspector = page.locator('.gis-inspector');
  await expect(gisInspector.getByText('已从告警中心定位到当前设备。', { exact: true })).toBeVisible();
  await expect(gisInspector.getByText('控制器通信质量波动', { exact: true })).toBeVisible();
  await gisInspector.getByRole('button', { name: '在三维中查看此设备 →' }).click();
  await expect(page).toHaveURL(/\/twin-3d\?asset=CTRL-01/);
});

test('三维全屏设备栏拖动期间仍保持高级指针反馈并可继续选择设备', async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码').fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await page.getByRole('button', { name: '三维孪生' }).click();
  await expect(page.getByRole('heading', { name: '三维孪生中心' })).toBeVisible();

  const patrolCode = page.locator('.twin-focus-status small');
  const beforePatrol = await patrolCode.textContent();
  await page.getByRole('button', { name: '巡检下一异常设备' }).click();
  await expect.poll(() => patrolCode.textContent()).not.toBe(beforePatrol);

  await page.getByRole('button', { name: '全屏查看' }).click();
  await expect.poll(() => page.evaluate(() => Boolean(document.fullscreenElement))).toBe(true);
  const zoomIn = page.getByRole('button', { name: '放大三维模型' });
  const zoomOut = page.getByRole('button', { name: '缩小三维模型' });
  const resetCamera = page.getByRole('button', { name: '显示完整三维模型' });
  await expect(zoomIn).toBeVisible();
  await expect(zoomOut).toBeVisible();
  await expect(resetCamera).toBeVisible();
  await resetCamera.dispatchEvent('click');

  const switcher = page.locator('.twin-quick-switch');
  const box = await switcher.boundingBox();
  expect(box).not.toBeNull();
  await page.mouse.move(box.x + 36, box.y + 18);
  await expect(page.locator('.twin-fullscreen-fx.active')).toHaveCount(1);
  await page.mouse.down();
  await page.mouse.move(box.x + 220, box.y + 18, { steps: 5 });
  // Headless Chromium does not expose `(hover: hover) and (pointer: fine)`, so
  // it intentionally keeps the visual cursor hidden. The drag-state class is
  // the browser-independent contract that keeps the real desktop cursor alive.
  await expect(page.locator('.twin-fullscreen-fx.dragging')).toHaveCount(1);
  await page.mouse.up();
  await expect(page.locator('.twin-fullscreen-fx.dragging')).toHaveCount(0);
  await page.getByRole('button', { name: 'ENV-01' }).dispatchEvent('click');
  await expect(page.locator('.twin-focus-status').getByText('DHT11 温湿度传感器', { exact: true })).toBeVisible();
  await page.evaluate(() => document.exitFullscreen());
  await expect.poll(() => page.evaluate(() => Boolean(document.fullscreenElement))).toBe(false);
});

test('账号密码登录后可读取运行数据并写入审计', async ({ page }) => {
  const consoleErrors = trackConsoleErrors(page);
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('operator@example.com');
  await page.getByLabel('密码').fill('demo-password-2026');
  await page.getByRole('button', { name: /安全登录/ }).click();
  await expect(page.getByRole('heading', { name: '运行，一眼掌握' })).toBeVisible();
  // The shell intentionally exposes both the data-service and realtime-feed
  // states. Scope this assertion to the data-service indicator rather than
  // relying on their incidental DOM count/order.
  await expect(page.locator('.status-pill[title^="数据服务最近同步"]')).toHaveText('数据服务已连接');

  await page.getByRole('button', { name: '数据洞察' }).click();
  await expect(page.getByRole('heading', { name: '数据洞察' })).toBeVisible();
  await expect(page.getByText('样本总量', { exact: true })).toBeVisible();
  await expect(page.locator('.governance-nav')).toBeVisible();
  await page.getByRole('button', { name: '审计追踪' }).click();
  await expect(page.getByText('用户登录系统', { exact: true }).first()).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test('操作反馈在页面上方显示并在三秒后自动关闭', async ({ page }) => {
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码').fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await page.getByRole('button', { name: '导出运行快照' }).click();
  const notice = page.getByRole('status').filter({ hasText: '报表已生成' });
  await expect(notice).toBeVisible();
  await expect(notice.getByText('操作已完成', { exact: true })).toBeVisible();
  const box = await notice.boundingBox();
  expect(box.y).toBeLessThan(page.viewportSize().height / 3);
  await page.waitForTimeout(1500);
  await expect(notice).toBeVisible();
  // Three-second display plus the exit transition and runner scheduling.
  await expect(notice).toHaveCount(0, { timeout: 3000 });
});

test('设备控制必须经二次确认并按一次性凭据顺序下发', async ({ page }) => {
  let confirmationRequests = 0;
  let commandRequests = 0;
  await page.route('**/controllers/CTRL-01/commands/confirmations/', async (route) => {
    confirmationRequests += 1;
    expect(route.request().postDataJSON()).toEqual({ action: 'relay_on' });
    await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({
      confirmationToken: 'e2e-confirmation-token-which-is-long-enough', expiresAt: new Date(Date.now() + 120000).toISOString(),
    }) });
  });
  await page.route('**/controllers/CTRL-01/commands/', async (route) => {
    commandRequests += 1;
    expect(route.request().postDataJSON()).toEqual({ action: 'relay_on', confirmationToken: 'e2e-confirmation-token-which-is-long-enough' });
    await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({
      cmdId: 'platform-e2e-command', action: 'relay_on', delivery: 'acknowledged', ack: { status: 'accepted', reason: 'relay_active' },
    }) });
  });
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码').fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await expect(page.getByRole('heading', { name: '运行，一眼掌握' })).toBeVisible();
  await page.getByRole('button', { name: '启动风扇（10秒）' }).click();
  const dialog = page.getByRole('dialog', { name: '确认下发设备命令' });
  await expect(dialog).toContainText('启动风扇（10 秒）');
  expect(confirmationRequests).toBe(0);
  expect(commandRequests).toBe(0);
  await dialog.getByRole('button', { name: '取消' }).click();
  await expect(dialog).toHaveCount(0);
  expect(confirmationRequests).toBe(0);
  await page.getByRole('button', { name: '启动风扇（10秒）' }).click();
  await page.getByRole('dialog', { name: '确认下发设备命令' }).getByRole('button', { name: '确认并下发' }).click();
  await expect(page.getByText('已收到设备回执：relay_active。请以随后上报的设备状态核对实际效果。')).toBeVisible();
  await expect(page.getByText(/本页最近回执：启动风扇（10 秒）/)).toBeVisible();
  expect(confirmationRequests).toBe(1);
  expect(commandRequests).toBe(1);
});

test('运维员可确认告警、生成工单并推进处置流程', async ({ page }) => {
  const consoleErrors = trackConsoleErrors(page);
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('operator@example.com');
  await page.getByLabel('密码').fill('demo-password-2026');
  await page.getByRole('button', { name: /安全登录/ }).click();

  await page.getByRole('button', { name: '告警中心' }).click();
  const alertRow = page.locator('.table-row').filter({ hasText: 'ALM-260826-001' });
  await expect(alertRow).toBeVisible();
  const alertStatus = alertRow.getByTestId('alert-status-ALM-260826-001');
  const acknowledgeButton = alertRow.getByRole('button', { name: '确认' });
  if ((await alertStatus.textContent())?.trim() === '待确认') {
    await expect(acknowledgeButton).toBeVisible();
    await acknowledgeButton.click();
  }
  await expect(alertStatus).toHaveText('已确认');
  const openOrderButton = alertRow.getByRole('button', { name: /转工单|查看工单/ });
  await expect(openOrderButton).toBeVisible();
  await openOrderButton.click();
  await expect(page).toHaveURL(/\/work-orders\?focus=/);
  await expect(page.getByText(/已打开告警 ALM-260826-001 生成的处置工单/)).toBeVisible();
  const linkedOrder = page.locator('.order-card').filter({ hasText: 'ALM-260826-001' });
  await expect(linkedOrder).toBeVisible();
  await expect(linkedOrder).toHaveClass(/focused/);
  await linkedOrder.getByRole('button', { name: '三维定位' }).click();
  await expect(page).toHaveURL(/\/twin-3d\?asset=CTRL-01&source=work-order/);
  await expect(page.locator('.twin-inspector header code')).toContainText('CTRL-01');
  await page.goBack();
  await expect(linkedOrder).toBeVisible();
  const assignButton = linkedOrder.getByRole('button', { name: '接单并分派' });
  if (await assignButton.count()) await assignButton.click();
  const startButton = linkedOrder.getByRole('button', { name: '开始现场处理' });
  if (await startButton.count()) await startButton.click();
  const reviewButton = linkedOrder.getByRole('button', { name: '提交复核' });
  if (await reviewButton.count()) {
    await reviewButton.click();
    await linkedOrder.getByLabel('处理结果').fill('已完成现场检查，设备反馈恢复正常。');
    await linkedOrder.getByRole('button', { name: '确认提交' }).click();
  }
  await expect(linkedOrder.getByRole('button', { name: '复核并完成' })).toHaveCount(0);
  await expect(linkedOrder.getByText('处理记录')).toBeVisible();

  await page.getByRole('button', { name: '数据洞察' }).click();
  await page.getByLabel('资产').selectOption('ENV-01');
  await page.getByRole('button', { name: '查询数据' }).click();
  await expect(page.getByRole('heading', { name: '环境温度', exact: true }).first()).toBeVisible();
  await page.getByRole('button', { name: '重置' }).click();
  await expect(page.getByRole('button', { name: '查询数据' })).toBeVisible();

  await expect(page.locator('.governance-nav')).toBeVisible();
  await page.getByRole('button', { name: '审计追踪' }).click();
  // Use the control's accessible name: its wrapping label also contains all
  // option text, so an exact label-text query is not a stable selector.
  await page.getByRole('combobox', { name: '操作类型', exact: true }).selectOption('alert');
  await expect(page.getByText('确认告警', { exact: true }).first()).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test('查看者只能查看，不会出现写入、审批或管理入口', async ({ page }) => {
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('viewer@example.com');
  await page.getByLabel('密码').fill('demo-password-2026');
  await page.getByRole('button', { name: /安全登录/ }).click();
  await page.getByRole('button', { name: '告警中心' }).click();
  await expect(page.getByText('只读角色', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('button', { name: '资产配置' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '空间配置' })).toHaveCount(0);
  await page.getByRole('button', { name: '工单中心' }).click();
  await expect(page.getByText('查看者无权新建或流转工单。')).toBeVisible();
  await expect(page.getByRole('button', { name: /新建工单/ })).toHaveCount(0);
});

test('注册申请须经管理员批准后才能登录使用', async ({ page }) => {
  const suffix = `${Date.now()}`.slice(-8);
  const account = `e2e-operator-${suffix}`;
  const password = 'Operator-pass-2026!';
  await page.goto(webUrl);
  await page.getByRole('button', { name: /提交注册申请/ }).click();
  await page.getByLabel('姓名或称呼').fill('值班运维员');
  await page.getByLabel('申请账号').fill(account);
  await page.getByRole('button', { name: '提交注册申请' }).click();
  await expect(page.getByText('申请已提交。管理员批准后会向你提供一次性密码设置链接。')).toBeVisible();
  await page.getByRole('button', { name: /返回登录/ }).click();

  const adminPage = await page.context().newPage();
  await adminPage.goto(webUrl);
  await adminPage.getByLabel('账号或邮箱').fill('admin');
  await adminPage.getByLabel('密码').fill(adminPassword);
  await adminPage.getByRole('button', { name: /安全登录/ }).click();
  await expect(adminPage.getByRole('heading', { name: '运行，一眼掌握' })).toBeVisible({ timeout: 15_000 });
  await expect(adminPage.locator('.governance-nav')).toBeVisible();
  await adminPage.getByRole('button', { name: '系统配置' }).click();
  const applicationRow = adminPage.locator('.registration-request-row').filter({ hasText: account });
  await expect(applicationRow).toBeVisible();
  let releaseApproval;
  const approvalGate = new Promise((resolve) => { releaseApproval = resolve; });
  let approvalRequests = 0;
  await adminPage.route('**/admin/registration-requests/*/', async (route) => {
    if (route.request().method() === 'PATCH') {
      approvalRequests += 1;
      await approvalGate;
    }
    await route.continue();
  });
  try {
    await applicationRow.getByRole('button', { name: '批准并创建账号' }).click();
    await expect.poll(() => approvalRequests).toBe(1);
    await expect(applicationRow.getByRole('button', { name: '批准并创建账号' })).toBeDisabled();
    await expect(applicationRow.getByRole('button', { name: '不予批准', exact: true })).toBeDisabled();
    await expect(adminPage.getByText('正在处理账号申请，请稍候…')).toBeVisible();
  } finally {
    releaseApproval();
  }
  await expect(applicationRow).toHaveCount(0);
  expect(approvalRequests).toBe(1);
  const setupLink = await adminPage.locator('.inline-message[role="status"] a').getAttribute('href');
  expect(setupLink).toBeTruthy();
  await adminPage.close();

  await page.goto(setupLink);
  await page.getByLabel('新密码').fill(password);
  await page.getByLabel('确认密码').fill(password);
  await page.getByRole('button', { name: '设置密码' }).click();
  await expect(page.getByText('密码设置成功，请返回登录。')).toBeVisible();
  await page.getByRole('button', { name: '返回登录' }).click();
  await page.getByLabel('账号或邮箱').fill(account);
  await page.getByLabel('密码').fill(password);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await expect(page.getByRole('heading', { name: '运行，一眼掌握' })).toBeVisible();
});

test('管理员可创建并版本化维护资产与 GIS 坐标', async ({ page }) => {
  const consoleErrors = trackConsoleErrors(page);
  const suffix = `${Date.now()}`.slice(-8);
  const assetCode = `ENV-E2E-${suffix}`;
  const featureCode = `SEG-E2E-${suffix}`;
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码').fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await expect(page.locator('.governance-nav')).toBeVisible();
  await page.getByRole('button', { name: '资产配置' }).click();
  await expect(page.getByRole('heading', { name: '资产主数据' })).toBeVisible();
  await page.getByRole('button', { name: '新建资产' }).click();
  await page.getByLabel('资产编码').fill(assetCode);
  await page.getByLabel('资产名称').fill('端到端环境节点');
  await page.getByLabel('所属区域').fill('UT-ZA');
  await page.getByLabel('资产类型').fill('环境测点');
  // Keep the asset-governance scenario compatible with the production GLB
  // contract so the following model-release scenario can validate the full
  // suite as one continuous operator journey.
  await page.getByLabel('模型设备节点').fill('MESH_TEMP_A01');
  await page.getByLabel('位置来源').selectOption('configured');
  await page.getByLabel('纬度').fill('31.230800');
  await page.getByLabel('经度').fill('121.474500');
  await page.getByRole('button', { name: '创建资产' }).click();
  await expect(page.getByText(`${assetCode} 已创建。`)).toBeVisible();
  await expect(page.getByText('数据版本 1', { exact: true })).toBeVisible();
  await page.getByLabel('资产名称').fill('端到端环境节点（已校核）');
  await page.getByRole('button', { name: '保存变更' }).click();
  await expect(page.getByText(`${assetCode} 已保存，当前版本 v2。`)).toBeVisible();
  await expect(page.getByText('数据版本 2', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: '空间配置' }).click();
  await expect(page.getByRole('heading', { name: '空间数据管理' })).toBeVisible();
  await page.getByLabel('对象名称').fill('端到端设备安装点');
  await page.getByLabel('对象编码').fill(featureCode);
  await page.getByLabel('来源依据', { exact: true }).fill('端到端登记记录');
  // Coordinates must be supplied explicitly; never rely on a fabricated default.
  await expect(page.getByLabel('纬度', { exact: true })).toHaveValue('');
  await expect(page.getByLabel('经度', { exact: true })).toHaveValue('');
  await page.getByLabel('纬度', { exact: true }).fill('31.230800');
  await page.getByLabel('经度', { exact: true }).fill('121.474500');
  await page.getByRole('button', { name: /保存待审核点位/ }).click();
  await expect(page.getByText('已建立 1 个待审核空间对象。')).toBeVisible();
  await page.getByRole('button', { name: '审核并发布' }).click();
  await expect(page.getByText(`${featureCode} 已通过审核并发布到运维地图。`)).toBeVisible();
  await page.getByRole('button', { name: 'GIS 总览' }).click();
  await expect(page.getByText(/个已发布空间对象/)).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test('管理员可校验、启用三维模型版本并由孪生页面鉴权加载', async ({ page }) => {
  // This is an end-to-end release path: it uploads and validates a GLB,
  // activates it, waits for Three.js to load it, then proves camera controls.
  // GitHub's software WebGL runner can take longer than the general UI budget;
  // keep the allowance local to this heavyweight workflow instead of masking
  // timeouts in ordinary interaction tests.
  test.setTimeout(180_000);
  const consoleErrors = trackConsoleErrors(page);
  const version = `e2e-model-${Date.now()}`;
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码').fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await expect(page.locator('.governance-nav')).toBeVisible();
  await page.getByRole('button', { name: '系统配置' }).click();
  await expect(page.getByText('三维模型版本', { exact: true })).toBeVisible();
  await expect(page.getByText('正在读取模型版本…', { exact: true })).toHaveCount(0, { timeout: 15_000 });
  await page.getByLabel('版本号').fill(version);
  await page.getByLabel('GLB 模型').setInputFiles(modelUploadFor(version));
  await expect(page.getByLabel('GLB 模型')).toHaveValue(/utility-tunnel\.glb$/);
  await page.getByLabel('版本说明').fill('浏览器回归验证模型发布与鉴权加载');
  await page.getByRole('button', { name: '上传并校验' }).click();
  await expect(page.getByText(/模型校验通过：\d+ 个命名节点，已覆盖全部设备，可启用。/)).toBeVisible({ timeout: 60_000 });
  const release = page.locator('.model-release-row').filter({ hasText: version });
  await expect(release).toBeVisible();
  await expect(release.getByText('设备节点映射完整，可以安全启用')).toBeVisible();
  await release.getByRole('button', { name: '启用此版本' }).click();
  await expect(release.getByText('当前使用', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '三维孪生' }).click();
  await expect(page.locator('.twin-model-readiness.loaded').getByText('模型已加载', { exact: true })).toBeVisible({ timeout: 60_000 });
  const zoomIn = page.getByRole('button', { name: '放大三维模型' });
  const zoomOut = page.getByRole('button', { name: '缩小三维模型' });
  await expect(zoomIn).toBeVisible();
  await expect(zoomOut).toBeVisible();
  const canvas = page.locator('.twin-canvas');
  const distanceBefore = Number(await canvas.getAttribute('data-camera-distance'));
  await zoomOut.dispatchEvent('click');
  await expect.poll(async () => Number(await canvas.getAttribute('data-camera-distance'))).toBeGreaterThan(distanceBefore);
  const distanceAfterZoomOut = Number(await canvas.getAttribute('data-camera-distance'));
  await page.waitForTimeout(500);
  expect(Number(await canvas.getAttribute('data-camera-distance'))).toBeCloseTo(distanceAfterZoomOut, 2);
  await zoomIn.dispatchEvent('click');

  const sceneBox = await canvas.boundingBox();
  expect(sceneBox).not.toBeNull();
  const cameraBeforeRotate = await canvas.getAttribute('data-camera-position');
  await page.mouse.move(sceneBox.x + sceneBox.width * .62, sceneBox.y + sceneBox.height * .45);
  await page.mouse.down({ button: 'left' });
  await page.mouse.move(sceneBox.x + sceneBox.width * .42, sceneBox.y + sceneBox.height * .68, { steps: 8 });
  await page.mouse.up({ button: 'left' });
  await expect.poll(() => canvas.getAttribute('data-camera-position')).not.toBe(cameraBeforeRotate);

  const targetBeforePan = await canvas.getAttribute('data-camera-target');
  await page.mouse.move(sceneBox.x + sceneBox.width * .54, sceneBox.y + sceneBox.height * .48);
  await page.mouse.down({ button: 'right' });
  await page.mouse.move(sceneBox.x + sceneBox.width * .68, sceneBox.y + sceneBox.height * .58, { steps: 8 });
  await page.mouse.up({ button: 'right' });
  await expect.poll(() => canvas.getAttribute('data-camera-target')).not.toBe(targetBeforePan);
  expect(consoleErrors).toEqual([]);
});

test('非空历史告警在趋势图上叠加', async ({ page, request }) => {
  const base = process.env.E2E_API_URL || 'http://127.0.0.1:8000/api';
  const login = await request.post(`${base}/auth/login/`, { data: { email: 'admin', password: adminPassword } });
  expect(login.ok()).toBe(true);
  const token = (await login.json()).accessToken;
  const headers = { Authorization: `Bearer ${token}` };
  const suffix = `${Date.now()}`.slice(-8);
  const assetCode = `ALRT-OVL-${suffix}`;
  // A dedicated asset isolates the telemetry and threshold alerts from the seed
  // assets, so ENV-01's latest metric and the seeded alert list stay unchanged.
  const created = await request.post(`${base}/assets/`, { headers, data: {
    code: assetCode, name: '告警叠加验证节点', zone: 'UT-ZA', type: '环境测点',
    integrationStatus: 'verified', locationSource: 'configured',
    mesh: `MESH_ALRT_OVL_${suffix}`, latitude: 31.2308, longitude: 121.4745,
  } });
  expect(created.ok(), await created.text()).toBe(true);
  const run = Date.now();
  // Breach/normal pairs create resolved threshold alerts inside the trend window;
  // ending on a normal reading leaves no persistent open alert.
  const readings = Array.from({ length: 12 }, (_, index) => ({
    eventId: `alert-overlay-${run}-${index}`,
    assetCode, metricKey: 'humidity', metric: '环境湿度',
    value: index % 2 === 0 ? 78 : 60, unit: '%RH', quality: 'good',
    recordedAt: new Date(run - (11 - index) * 60000).toISOString(),
  }));
  const result = await request.post(`${base}/telemetry/`, { headers, data: { readings } });
  expect(result.ok(), await result.text()).toBe(true);
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码', { exact: true }).fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await expect(page).toHaveURL(/dashboard/);
  await page.goto(`${webUrl}/telemetry?assetCode=${assetCode}&metricKey=humidity`);
  await expect(page.locator('.telemetry-history-chart canvas')).toBeVisible();
  const eventsRegion = page.getByRole('region', { name: '趋势时段告警事件' });
  await expect(eventsRegion).not.toContainText('加载失败');
  await expect(eventsRegion).not.toContainText('没有匹配事件');
  await expect(eventsRegion.getByText(/ALM-AUTO-/).first()).toBeVisible();
  // Chart-level evidence: the component exposes the alert-marker contract on the
  // DOM, proving the rendered chart received the markers (not just the list).
  const host = page.locator('.telemetry-history-chart-host');
  await expect(host).toHaveAttribute('data-markline-count', '6');
  const marklineTimes = ((await host.getAttribute('data-markline-times')) || '').split(',').map(Number);
  expect(marklineTimes).toHaveLength(6);
  expect(marklineTimes.every(Number.isFinite)).toBe(true);
  // Switching to a query with no matching alerts clears the stale markers.
  await page.goto(`${webUrl}/telemetry?assetCode=ENV-01&metricKey=temperature`);
  await expect(page.getByRole('region', { name: '趋势时段告警事件' })).toContainText('没有匹配事件');
});

test('多页事件加载、报警次数口径与页码刷新恢复', async ({ page, request }) => {
  const base = process.env.E2E_API_URL || 'http://127.0.0.1:8000/api';
  const login = await request.post(`${base}/auth/login/`, { data: { email: 'admin', password: adminPassword } });
  expect(login.ok()).toBe(true);
  const token = (await login.json()).accessToken;
  const headers = { Authorization: `Bearer ${token}` };
  const suffix = `${Date.now()}`.slice(-8);
  const assetCode = `PAGE-EVT-${suffix}`;
  const created = await request.post(`${base}/assets/`, { headers, data: {
    code: assetCode, name: '分页事件验证节点', zone: 'UT-ZB', type: '环境测点',
    integrationStatus: 'verified', locationSource: 'configured',
    mesh: `MESH_PAGE_EVT_${suffix}`, latitude: 31.2309, longitude: 121.4746,
  } });
  expect(created.ok(), await created.text()).toBe(true);
  const run = Date.now();
  const readings = Array.from({ length: 160 }, (_, index) => ({
    eventId: `page-evt-${run}-${index}`,
    assetCode, metricKey: 'humidity', metric: '环境湿度',
    value: index % 2 === 0 ? 78 : 60, unit: '%RH', quality: 'good',
    recordedAt: new Date(run - (159 - index) * 60000).toISOString(),
  }));
  for (let index = 0; index < readings.length; index += 100) {
    const result = await request.post(`${base}/telemetry/`, { headers, data: { readings: readings.slice(index, index + 100) } });
    expect(result.ok(), await result.text()).toBe(true);
  }
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码', { exact: true }).fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await expect(page).toHaveURL(/dashboard/);
  await page.goto(`${webUrl}/telemetry?assetCode=${assetCode}&metricKey=humidity`);
  const eventsRegion = page.getByRole('region', { name: '趋势时段告警事件' });
  await expect(eventsRegion).not.toContainText('加载失败');
  // The overlay is scoped to the current trend page (100 readings -> 50 breaches),
  // while the alarm-count metric reflects the full asset query (80 alerts).
  await expect(eventsRegion).toContainText('共 50 条告警，已加载 50 条');
  await expect(eventsRegion.getByRole('button', { name: '加载更多事件' })).toHaveCount(0);
  await expect(page.locator('.insight-metrics article').filter({ hasText: '报警次数' })).toContainText('80');
  await expect(page.locator('.insight-metrics article').filter({ hasText: '采集时段' })).toBeVisible();
  await eventsRegion.getByRole('button', { name: '查看当前筛选范围内的全部告警（80）' }).click();
  await expect(page).toHaveURL(new RegExp(`/alerts\\?.*assetCode=${assetCode}`));
  const completeAlertTable = page.getByRole('region', { name: '告警记录' });
  await expect(completeAlertTable).toContainText('ALM-AUTO-');
  await expect(completeAlertTable.locator('.table-row')).toHaveCount(80);
  const paging = page.getByRole('navigation', { name: '历史采集记录分页' });
  await page.goto(`${webUrl}/telemetry?assetCode=${assetCode}&metricKey=humidity`);
  await paging.getByRole('button', { name: '下一页' }).click();
  await expect(page).toHaveURL(/page=2/);
  await expect(paging).toContainText('第 2 / 2 页');
  await page.reload();
  await expect(paging).toContainText('第 2 / 2 页');
  await expect(page.getByRole('combobox', { name: '资产' })).toHaveValue(assetCode);
  await expect(page.getByLabel('监测项目')).toHaveValue('humidity');
});

test('筛选条件写入URL并在刷新后恢复', async ({ page }) => {
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码', { exact: true }).fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await expect(page).toHaveURL(/dashboard/);
  await page.goto(`${webUrl}/telemetry`);
  await page.getByRole('combobox', { name: '资产' }).selectOption('ENV-01');
  await page.getByLabel('监测项目').selectOption('temperature');
  await page.getByRole('button', { name: '查询数据' }).click();
  await expect(page).toHaveURL(/assetCode=ENV-01/);
  await expect(page).toHaveURL(/metricKey=temperature/);
  await page.reload();
  await expect(page.getByRole('combobox', { name: '资产' })).toHaveValue('ENV-01');
  await expect(page.getByLabel('监测项目')).toHaveValue('temperature');
});

test('已认证浏览器在 3 秒内通过 WebSocket 接收新告警，而非等待轮询快照', async ({ page, request }) => {
  const base = process.env.E2E_API_URL || 'http://127.0.0.1:8000/api';
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码', { exact: true }).fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await expect(page).toHaveURL(/dashboard/);
  await expect(page.locator('[title="实时推送已连接"]')).toBeVisible();
  // Keep the alert view open before the write. This makes the assertion prove
  // the pushed upsert path; navigating after a write could pass via its
  // ordinary REST initial-load request instead.
  await page.getByRole('button', { name: '告警中心' }).click();
  const alertsRegion = page.getByRole('region', { name: '告警记录' });
  await expect(alertsRegion).toBeVisible();

  const login = await request.post(`${base}/auth/login/`, { data: { email: 'admin', password: adminPassword } });
  expect(login.ok()).toBe(true);
  const headers = { Authorization: `Bearer ${(await login.json()).accessToken}` };
  const suffix = `${Date.now()}`.slice(-8);
  const assetCode = `WS-EVT-${suffix}`;
  const asset = await request.post(`${base}/assets/`, { headers, data: {
    code: assetCode, name: '实时推送验证节点', zone: 'UT-ZA', type: '环境测点',
    integrationStatus: 'verified', locationSource: 'configured',
    mesh: `MESH_WS_${suffix}`, latitude: 31.2307, longitude: 121.4744,
  } });
  expect(asset.ok(), await asset.text()).toBe(true);
  const propagationStartedAt = Date.now();
  const reading = await request.post(`${base}/telemetry/`, { headers, data: { readings: [{
    eventId: `ws-alert-${suffix}`, assetCode, metricKey: 'temperature', metric: '环境温度',
    value: 99, unit: '°C', quality: 'good', recordedAt: new Date().toISOString(),
  }] } });
  expect(reading.ok(), await reading.text()).toBe(true);

  await expect(alertsRegion).toContainText(assetCode, { timeout: 3_000 });
  expect(Date.now() - propagationStartedAt).toBeLessThan(3_000);
});

test('三维页在 3 秒内将实时新告警定位到已绑定设备', async ({ page, request }) => {
  const base = process.env.E2E_API_URL || 'http://127.0.0.1:8000/api';
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码', { exact: true }).fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await expect(page).toHaveURL(/dashboard/);
  await expect(page.locator('[title="实时推送已连接"]')).toBeVisible();
  await page.getByRole('button', { name: '三维孪生' }).click();
  await expect(page.locator('.twin-model-readiness.loaded').getByText('模型已加载', { exact: true })).toBeVisible({ timeout: 60_000 });
  const autoLocate = page.getByRole('checkbox', { name: '新告警自动定位' });
  await expect(autoLocate).toBeChecked();

  const login = await request.post(`${base}/auth/login/`, { data: { email: 'admin', password: adminPassword } });
  expect(login.ok()).toBe(true);
  const headers = { Authorization: `Bearer ${(await login.json()).accessToken}` };
  // Playwright's default assertion polling backs off to one-second intervals.
  // That makes an event received just before the three-second boundary appear
  // late to the test process, even though the browser rendered it on time.
  // Capture the actual DOM-mutation timestamp in the page before the write,
  // then compare it with the durable API-acceptance boundary below.
  await page.evaluate(() => {
    const message = '已定位 ENV-01';
    const readStatus = () => Array.from(document.querySelectorAll('[role="status"]'))
      .some((element) => element.textContent?.includes(message));
    window.__twinAutoLocateProbe = new Promise((resolve) => {
      let observer;
      const finish = (observedAt) => {
        observer?.disconnect();
        window.clearTimeout(timeout);
        resolve(observedAt);
      };
      const check = () => {
        if (readStatus()) finish(performance.timeOrigin + performance.now());
      };
      observer = new MutationObserver(check);
      observer.observe(document.body, { childList: true, subtree: true, characterData: true });
      const timeout = window.setTimeout(() => finish(null), 15_000);
      check();
    });
  });
  const reading = await request.post(`${base}/telemetry/`, { headers, data: { readings: [{
    eventId: `ws-twin-locate-${Date.now()}`,
    // ENV-01 is a required node of the released V07 GLB, so this proves an
    // actual model binding rather than a list-only alert reaction.
    assetCode: 'ENV-01', metricKey: 'temperature', metric: '环境温度',
    value: 99, unit: '°C', quality: 'good', recordedAt: new Date().toISOString(),
  }] } });
  expect(reading.ok(), await reading.text()).toBe(true);
  // The service has accepted the reading at this point. Measure the operator
  // notification path from that durable boundary rather than including the
  // variable HTTP ingest duration itself in a browser push-latency SLA.
  const propagationStartedAt = Date.now();

  const observedAt = await page.evaluate(() => window.__twinAutoLocateProbe);
  expect(observedAt).not.toBeNull();
  expect(observedAt - propagationStartedAt).toBeLessThan(3_000);
  await expect(page.getByRole('group', { name: '新告警自动定位' })).toContainText(/已定位 ENV-01/);
  // Keep the visual focus verification independent from the push budget: GPU
  // render scheduling may delay this status node, but must never drop it.
  await expect(page.locator('.twin-focus-status')).toContainText('ENV-01', { timeout: 10_000 });
});

test('已启用模型文件读取失败时不把预览场景误报为实体模型', async ({ page }) => {
  await page.route('**/api/twin/model-readiness/', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      status: 'ready',
      summary: { activeAssetCount: 19, mappedAssetCount: 19, unmappedAssetCount: 0 },
      missingMeshCodes: [], invalidMeshCodes: [], modelMismatchCodes: [], mappings: [],
      contract: { nodeNamePattern: 'A-Z, 0-9, hyphen and underscore', nodeNamesUnique: true, modelFileVerified: true, modelNodesCompatible: true, modelNodeInventoryAvailable: true },
      activeRelease: { id: 987, version: 'simulated-active-release' },
      updatedAt: new Date().toISOString(),
    }),
  }));
  await page.route('**/api/twin/model-file/**', (route) => route.fulfill({
    status: 503,
    contentType: 'application/json',
    body: JSON.stringify({ error: 'model_storage_unavailable' }),
  }));
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码', { exact: true }).fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await page.getByRole('button', { name: '三维孪生' }).click();
  const readiness = page.locator('.twin-model-readiness');
  await expect(readiness.getByText('模型文件不可用', { exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(readiness.getByText('模型已加载', { exact: true })).toHaveCount(0);
  await expect(page.locator('.twin-scene')).toHaveAttribute('data-model-state', 'fallback');
  await expect(page.locator('.twin-live[title*="实体模型文件暂时无法获取"]')).toContainText('模型文件暂不可用');
});

test('五个液位节点分别定位，L03 告警只高亮对应测点', async ({ page, request }) => {
  const base = process.env.E2E_API_URL || 'http://127.0.0.1:8000/api';
  const login = await request.post(`${base}/auth/login/`, { data: { email: 'admin', password: adminPassword } });
  expect(login.ok()).toBe(true);
  const headers = { Authorization: `Bearer ${(await login.json()).accessToken}` };

  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码', { exact: true }).fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await expect(page).toHaveURL(/dashboard/);
  await page.goto(`${webUrl}/twin-3d?asset=LEVEL-L01`);
  const cards = page.locator('.level-station-card');
  await expect(cards).toHaveCount(5);
  await expect(page.locator('.twin-scene')).toHaveAttribute('data-model-state', 'loaded', { timeout: 30_000 });
  const cameraTargets = new Set();
  for (let index = 1; index <= 5; index += 1) {
    const code = `LEVEL-L0${index}`;
    await cards.filter({ hasText: code }).click();
    await expect(page.locator('.twin-focus-status')).toContainText(code);
    await expect(page.locator('.twin-canvas')).toHaveAttribute('data-camera-target', /\d/);
    cameraTargets.add(await page.locator('.twin-canvas').getAttribute('data-camera-target'));
  }
  expect(cameraTargets.size).toBe(5);

  const response = await request.post(`${base}/telemetry/`, { headers, data: { readings: [{
    eventId: `level-l03-browser-${Date.now()}`, assetCode: 'LEVEL-L03', metricKey: 'level.detected',
    metric: '液位检测', value: 1, unit: 'bool', quality: 'good', recordedAt: new Date().toISOString(),
  }] } });
  expect(response.ok(), await response.text()).toBe(true);
  await page.goto(`${webUrl}/twin-3d?asset=LEVEL-L03`);
  await expect(cards.filter({ hasText: 'LEVEL-L03' })).toHaveClass(/alarm/);
  await expect(cards.filter({ hasText: 'LEVEL-L02' })).not.toHaveClass(/alarm/);
  await expect(page.locator('.twin-focus-status')).toContainText('LEVEL-L03');
  await expect(page.locator('.twin-inspector')).toContainText('液位检测');
});

test('V13 设计预览在新模型中分别定位五个液位探头', async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码', { exact: true }).fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await expect(page).toHaveURL(/dashboard/);
  await page.goto(`${webUrl}/twin-3d?model=v13&asset=LEVEL-L01`);
  await expect(page.getByText('V13 设计预览', { exact: true }).first()).toBeVisible();
  await expect(page.locator('.twin-scene')).toHaveAttribute('data-model-state', 'loaded', { timeout: 60_000 });
  await expect(page.locator('.twin-model-readiness')).toContainText('五个液位探头可分别定位');
  const cards = page.locator('.level-station-card');
  const cameraTargets = new Set();
  for (let index = 1; index <= 5; index += 1) {
    const code = `LEVEL-L0${index}`;
    await cards.filter({ hasText: code }).click();
    await expect(page.locator('.twin-focus-status')).toContainText(code);
    cameraTargets.add(await page.locator('.twin-canvas').getAttribute('data-camera-target'));
  }
  expect(cameraTargets.size).toBe(5);
  await page.getByRole('button', { name: '返回当前模型' }).click();
  await expect(page).not.toHaveURL(/model=v13/);
});
