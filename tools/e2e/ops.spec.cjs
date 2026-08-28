const { test, expect } = require('@playwright/test');

const webUrl = process.env.E2E_WEB_URL || 'http://127.0.0.1:5173';

function trackConsoleErrors(page) {
  const errors = [];
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', (error) => errors.push(error.message));
  return errors;
}

test('演示工作区可完成孪生定位、筛选和告警确认', async ({ page }) => {
  const consoleErrors = trackConsoleErrors(page);
  await page.route(/https:\/\/.*\.tile\.openstreetmap\.org\/.*/, (route) => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64'),
  }));
  await page.goto(webUrl);
  await expect(page.getByRole('heading', { name: /让每一米管廊/ })).toBeVisible();
  await page.getByRole('button', { name: '进入演示工作区' }).click();
  await expect(page.getByRole('heading', { name: '运行，一眼掌握' })).toBeVisible();

  await page.getByRole('button', { name: '设备台账' }).click();
  await expect(page.getByRole('heading', { name: '设备台账' })).toBeVisible();
  await expect(page.getByLabel('设备空间定位图').getByRole('button')).toHaveCount(12);
  await page.getByLabel('搜索设备').fill('SEEP-W01');
  await expect(page.getByRole('complementary').getByRole('heading', { name: '水位传感器', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '定位 水位传感器' }).click();
  await expect(page.getByText('PC0 / ADC1_IN10', { exact: true })).toBeVisible();
  await page.getByLabel('搜索设备').fill('NO-SUCH-ASSET');
  await expect(page.getByText('没有匹配的设备节点，请调整搜索条件。')).toBeVisible();

  await page.getByRole('button', { name: 'GIS 总览' }).click();
  await expect(page.getByRole('heading', { name: 'GIS 空间运维总览' })).toBeVisible();
  await expect(page.locator('.gis-module-list > button')).toHaveCount(12);
  await page.getByRole('button', { name: /H-04 · UT-ZB/ }).click();
  await expect(page.getByRole('complementary').getByText('待标定', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: '数据洞察' }).click();
  await expect(page.getByRole('heading', { name: '数据洞察' })).toBeVisible();
  await expect(page.locator('.insight-metrics article').first()).toContainText('24');
  await page.getByLabel('质量').selectOption('suspect');
  await page.getByRole('button', { name: '查询数据' }).click();
  await expect(page.locator('.insight-metrics article').first()).toContainText('1');
  await expect(page.locator('.quality-strip')).toContainText('可疑 1');

  await page.getByRole('button', { name: '告警中心' }).click();
  await page.locator('.table-row', { hasText: 'ALM-260826-003' }).getByRole('button', { name: '确认', exact: true }).click();
  await expect(page.getByTestId('alert-status-ALM-260826-003')).toHaveText('已确认');
  expect(consoleErrors).toEqual([]);
});

test('Django API 模式可登录、读取数据并写入审计', async ({ page }) => {
  const consoleErrors = trackConsoleErrors(page);
  await page.goto(webUrl);
  await page.getByRole('button', { name: 'Django API' }).click();
  await page.getByLabel('API 地址').fill('http://127.0.0.1:8000/api');
  await page.getByLabel('账号或邮箱').fill('operator@example.com');
  await page.getByLabel('密码').fill('demo-password-2026');
  await page.getByRole('button', { name: '连接 Django 并登录' }).click();
  await expect(page.getByRole('heading', { name: '运行，一眼掌握' })).toBeVisible();
  await expect(page.getByText('Django API', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: '数据洞察' }).click();
  await expect(page.getByRole('heading', { name: '数据洞察' })).toBeVisible();
  await expect(page.getByText('POSTGRESQL HISTORY', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: '告警中心' }).click();
  await page.locator('.table-row', { hasText: 'ALM-260826-003' }).getByRole('button', { name: '确认', exact: true }).click();
  await expect(page.getByTestId('alert-status-ALM-260826-003')).toHaveText('已确认');
  await page.getByRole('button', { name: '审计追踪' }).click();
  await expect(page.getByText('auth.login', { exact: true }).first()).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test('管理员可创建并版本化维护资产与 GIS 坐标', async ({ page }) => {
  const consoleErrors = trackConsoleErrors(page);
  const suffix = `${Date.now()}`.slice(-8);
  const assetCode = `ENV-E2E-${suffix}`;
  const featureCode = `SEG-E2E-${suffix}`;
  await page.goto(webUrl);
  await page.getByRole('button', { name: 'Django API' }).click();
  await page.getByLabel('API 地址').fill('http://127.0.0.1:8000/api');
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码').fill('123');
  await page.getByRole('button', { name: '连接 Django 并登录' }).click();
  await page.getByRole('button', { name: '资产主数据' }).click();
  await expect(page.getByRole('heading', { name: '资产主数据' })).toBeVisible();
  await page.getByRole('button', { name: '新建资产' }).click();
  await page.getByLabel('资产编码').fill(assetCode);
  await page.getByLabel('资产名称').fill('端到端环境节点');
  await page.getByLabel('所属区域').fill('UT-ZA');
  await page.getByLabel('资产类型').fill('环境测点');
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

  await page.getByRole('button', { name: '空间数据管理' }).click();
  await expect(page.getByRole('heading', { name: '空间数据管理' })).toBeVisible();
  await page.getByLabel('GeoJSON 导入内容').fill(JSON.stringify({
    type: 'FeatureCollection',
    features: [{
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: [[121.473700, 31.230400], [121.473900, 31.230500]] },
      properties: { code: featureCode, name: '端到端管廊段', layerType: 'tunnel_segment', source: 'surveyed', sourceReference: `E2E 测绘成果 ${suffix}`, accuracyM: '0.250', status: 'draft' },
    }],
  }));
  await page.getByRole('button', { name: '校验并导入空间对象' }).click();
  await expect(page.getByText('已建立 1 个空间对象草稿。请在审核后将状态更新为 published。')).toBeVisible();
  await page.getByRole('button', { name: '审核并发布' }).click();
  await expect(page.getByText(`${featureCode} 已通过审核并发布到运维地图。`)).toBeVisible();
  await page.getByRole('button', { name: 'GIS 总览' }).click();
  await expect(page.getByText(/个已发布空间对象/)).toBeVisible();
  expect(consoleErrors).toEqual([]);
});
