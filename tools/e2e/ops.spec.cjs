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
  await page.goto(webUrl);
  await expect(page.getByRole('heading', { name: /让每一米管廊/ })).toBeVisible();
  await page.getByRole('button', { name: '进入演示工作区' }).click();
  await expect(page.getByRole('heading', { name: '运行，一眼掌握' })).toBeVisible();

  await page.getByRole('button', { name: '设备台账' }).click();
  await expect(page.getByRole('heading', { name: '设备台账' })).toBeVisible();
  await expect(page.getByLabel('设备空间定位图').getByRole('button')).toHaveCount(4);
  await page.getByLabel('搜索设备').fill('SEEP-W01');
  await expect(page.getByText('渗水监测点', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '定位 渗水监测点' }).click();
  await expect(page.getByText('70, 68', { exact: true })).toBeVisible();
  await page.getByLabel('搜索设备').fill('NO-SUCH-ASSET');
  await expect(page.getByText('没有匹配的设备节点，请调整搜索条件。')).toBeVisible();

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
  await page.getByLabel('工作邮箱').fill('operator@example.com');
  await page.getByLabel('密码').fill('demo-password-2026');
  await page.getByRole('button', { name: '连接 Django 并登录' }).click();
  await expect(page.getByRole('heading', { name: '运行，一眼掌握' })).toBeVisible();
  await expect(page.getByText('Django API', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: '告警中心' }).click();
  await page.locator('.table-row', { hasText: 'ALM-260826-003' }).getByRole('button', { name: '确认', exact: true }).click();
  await expect(page.getByTestId('alert-status-ALM-260826-003')).toHaveText('已确认');
  await page.getByRole('button', { name: '审计追踪' }).click();
  await expect(page.getByText('auth.login', { exact: true })).toBeVisible();
  expect(consoleErrors).toEqual([]);
});
