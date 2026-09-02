const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');

const webUrl = process.env.E2E_WEB_URL || 'http://127.0.0.1:5173';
const adminPassword = '123';

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
  await page.route(/https:\/\/.*\.tile\.openstreetmap\.org\/.*/, (route) => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64'),
  }));
  await page.goto(webUrl);
  await expect(page.getByRole('heading', { name: /让每一米管廊/ })).toBeVisible();
  await expect(page.getByRole('button', { name: '演示工作区' })).toHaveCount(0);
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码').fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await expect(page.getByRole('heading', { name: '运行，一眼掌握' })).toBeVisible();

  await page.getByRole('button', { name: '设备台账' }).click({ force: true });
  await expect(page.getByRole('heading', { name: '设备台账' })).toBeVisible();
  expect(await page.getByLabel('设备空间定位图').getByRole('button').count()).toBeGreaterThan(0);
  await page.getByLabel('搜索设备').fill('SEEP-W01');
  await expect(page.getByRole('complementary').getByRole('heading', { name: '水位传感器', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '定位 水位传感器' }).click({ force: true });
  await expect(page.getByText('PC0 / ADC1_IN10', { exact: true })).toBeVisible();
  await page.getByLabel('搜索设备').fill('NO-SUCH-ASSET');
  await expect(page.getByText('没有匹配的设备节点，请调整搜索条件。')).toBeVisible();

  await page.getByRole('button', { name: '数据洞察' }).click();
  await expect(page.getByRole('heading', { name: '数据洞察' })).toBeVisible();
  await expect(page.getByText('运行数据', { exact: true })).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test('三维孪生加载正式环形 V04 模型后仍可定位设备并展示告警状态', async ({ page }) => {
  test.setTimeout(120_000);
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
  await page.mouse.move(canvasBox.x + canvasBox.width * .72, canvasBox.y + canvasBox.height * .58, { steps: 8 });
  await page.mouse.up({ button: 'left' });
  await expect.poll(() => page.locator('.twin-canvas').getAttribute('data-camera-target')).not.toBe(targetBeforePan);
  await page.getByRole('button', { name: '启用自由旋转' }).click();
  await expect(page.getByRole('button', { name: '启用自由旋转' })).toHaveClass(/active/);
  const switcher = page.locator('.twin-quick-switch');
  await expect(page.locator('.twin-model-readiness').getByText('模型已加载', { exact: true })).toBeVisible();
  await expect(page.locator('.twin-model-readiness').getByText(/\d+ \/ \d+ 个设备已定位/)).toBeVisible();
  const modelReadiness = page.locator('.twin-model-readiness.loaded');
  await expect(modelReadiness.getByText('模型已加载', { exact: true })).toBeVisible();
  await expect(page.locator('.twin-model-contract').getByText(/\d+ \/ \d+ 个设备已具备标准节点名称/)).toBeVisible();
  await page.getByText('查看实体模型映射', { exact: true }).click();
  await expect(page.locator('.twin-model-binding-list').getByText('ENV-01', { exact: true })).toBeVisible();
  await switcher.getByRole('button', { name: '告警', exact: true }).click();
  expect(await switcher.getByRole('button', { name: /选择 / }).count()).toBeGreaterThan(0);
  await switcher.getByRole('button', { name: '全部', exact: true }).click();
  await page.getByRole('button', { name: 'ENV-01' }).click();
  const inspector = page.locator('.twin-inspector');
  await expect(inspector.getByText('MESH_ENV_01', { exact: true })).toBeVisible();
  await expect(inspector.getByText('运行正常', { exact: true })).toBeVisible();
  await inspector.getByRole('button', { name: '在 GIS 地图中查看' }).click();
  await expect(page).toHaveURL(/\/gis\?asset=ENV-01/);
  await expect(page.getByRole('heading', { name: 'GIS 空间运维总览' })).toBeVisible();
  await expect(page.locator('.gis-inspector').getByText('ENV-01 ·', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: '在三维中查看此设备 →' }).click();
  await expect(page).toHaveURL(/\/twin-3d\?asset=ENV-01/);
  await expect(page.locator('.twin-inspector').getByText('已从 GIS 地图定位到当前设备。', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'BT-01' }).click();
  await expect(page.locator('.twin-focus-status').getByText('HC-05 蓝牙模块', { exact: true })).toBeVisible();
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
  const firstAlert = page.locator('.table-row').first();
  await expect(firstAlert.getByText('ALM-260826-001', { exact: true })).toBeVisible();
  await firstAlert.getByRole('button', { name: '三维定位' }).click();
  await expect(page).toHaveURL(/\/twin-3d\?asset=CTRL-01/);
  const inspector = page.locator('.twin-inspector');
  await expect(inspector.getByText('已从告警 ALM-260826-001 定位到当前设备。', { exact: true })).toBeVisible();
  await expect(inspector.getByText('MESH_CTRL_01', { exact: true })).toBeVisible();
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
  await expect(page.getByText('链路在线', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: '数据洞察' }).click();
  await expect(page.getByRole('heading', { name: '数据洞察' })).toBeVisible();
  await expect(page.getByText('运行数据', { exact: true })).toBeVisible();
  await page.locator('.governance-nav summary').click();
  await page.getByRole('button', { name: '审计追踪' }).click();
  await expect(page.getByText('用户登录系统', { exact: true }).first()).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test('操作反馈在页面上方显示并在两秒内自动关闭', async ({ page }) => {
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码').fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await page.getByRole('button', { name: '导出运行快照' }).click();
  const notice = page.getByRole('status').filter({ hasText: '报表已生成' });
  await expect(notice).toBeVisible();
  await expect(notice.getByText('操作已完成', { exact: true })).toBeVisible();
  await expect(notice).toHaveCount(0, { timeout: 3200 });
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
  await expect(page.locator('.twin-inspector').getByText('MESH_CTRL_01', { exact: true })).toBeVisible();
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
  await expect(page.getByText('环境温度', { exact: true }).first()).toBeVisible();
  await page.getByRole('button', { name: '重置' }).click();
  await expect(page.getByRole('button', { name: '查询数据' })).toBeVisible();

  await page.locator('.governance-nav summary').click();
  await page.getByRole('button', { name: '审计追踪' }).click();
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
  await adminPage.locator('.governance-nav summary').click();
  await adminPage.getByRole('button', { name: '系统配置' }).click();
  const applicationRow = adminPage.locator('.registration-request-row').filter({ hasText: account });
  await expect(applicationRow).toBeVisible();
  await applicationRow.getByRole('button', { name: '批准并创建账号' }).click();
  await expect(applicationRow).toHaveCount(0);
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
  await page.locator('.governance-nav summary').click();
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
  await expect(page.getByText('乐观锁 v1')).toBeVisible();
  await page.getByLabel('资产名称').fill('端到端环境节点（已校核）');
  await page.getByRole('button', { name: '保存变更' }).click();
  await expect(page.getByText(`${assetCode} 已保存，当前版本 v2。`)).toBeVisible();
  await expect(page.getByText('乐观锁 v2')).toBeVisible();

  await page.getByRole('button', { name: '空间配置' }).click();
  await expect(page.getByRole('heading', { name: '空间数据管理' })).toBeVisible();
  await page.getByLabel('对象名称').fill('端到端管廊段');
  await page.getByLabel('对象编码').fill(featureCode);
  await page.getByRole('button', { name: '保存为待审核对象' }).click();
  await expect(page.getByText('已建立 1 个待审核空间对象。')).toBeVisible();
  await page.getByRole('button', { name: '审核并发布' }).click();
  await expect(page.getByText(`${featureCode} 已通过审核并发布到运维地图。`)).toBeVisible();
  await page.getByRole('button', { name: 'GIS 总览' }).click();
  await expect(page.getByText(/个已发布空间对象/)).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test('管理员可校验、启用三维模型版本并由孪生页面鉴权加载', async ({ page }) => {
  test.setTimeout(90_000);
  const consoleErrors = trackConsoleErrors(page);
  const version = `e2e-model-${Date.now()}`;
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码').fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await page.locator('.governance-nav summary').click();
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
