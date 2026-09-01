const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');

const webUrl = process.env.E2E_WEB_URL || 'http://127.0.0.1:5173';
const adminPassword = process.env.E2E_ADMIN_PASSWORD || '123';
const pages = [
  ['/dashboard', '运行，一眼掌握', '运行总览'],
  ['/alerts', '告警中心', '告警中心'],
  ['/work-orders', '工单中心', '工单中心'],
  ['/assets', '设备台账', '设备台账'],
  ['/twin-3d', '三维孪生中心', '三维孪生'],
  ['/gis', 'GIS 空间运维总览', 'GIS 总览'],
  ['/telemetry', '数据洞察', '数据洞察'],
  ['/asset-admin', '资产主数据', '资产配置'],
  ['/gis-admin', '空间数据管理', '空间配置'],
  ['/settings', '系统配置', '系统配置'],
  ['/audit', '审计追踪', '审计追踪'],
];

test('全部业务页面通过桌面端布局巡检', async ({ page }) => {
  test.setTimeout(120_000);
  const consoleErrors = [];
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  page.on('pageerror', (error) => consoleErrors.push(error.message));
  await page.route(/https:\/\/.*\.tile\.openstreetmap\.org\/.*/, (route) => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64'),
  }));
  await page.goto(webUrl);
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码').fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await expect(page.getByRole('heading', { name: '运行，一眼掌握' })).toBeVisible();

  const output = path.resolve(__dirname, '../../test-results/visual-audit');
  fs.mkdirSync(output, { recursive: true });
  for (const [route, heading, fileName] of pages) {
    await page.goto(`${webUrl}${route}`);
    await expect(page.getByRole('heading', { name: heading })).toBeVisible();
    await page.waitForTimeout(route === '/twin-3d' ? 1_500 : 1_200);
    const layout = await page.evaluate(() => ({
      viewport: window.innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      sidebarWidth: document.querySelector('.sidebar')?.getBoundingClientRect().width || 0,
      pageLeft: document.querySelector('.page-content')?.getBoundingClientRect().left || 0,
      overflowers: [...document.querySelectorAll('body *')]
        .map((element) => ({ tag: element.tagName, className: String(element.className || ''), right: Math.round(element.getBoundingClientRect().right) }))
        .filter((item) => item.right > window.innerWidth + 1)
        .sort((a, b) => b.right - a.right)
        .slice(0, 6),
    }));
    expect(layout.documentWidth, `${heading} 不应产生整页横向滚动：${JSON.stringify(layout.overflowers)}`).toBeLessThanOrEqual(layout.viewport + 1);
    expect(layout.pageLeft, `${heading} 内容区不得压入侧栏`).toBeGreaterThanOrEqual(layout.sidebarWidth - 1);
    const contentOpacity = await page.locator('.page-content > *').first().evaluate((element) => Number(getComputedStyle(element).opacity));
    expect(contentOpacity, `${heading} 首屏内容不得被过渡动画隐藏`).toBeGreaterThanOrEqual(.99);
    if (route === '/alerts') {
      const alertTable = await page.locator('.table-row').first().evaluate((row) => {
        const style = getComputedStyle(row);
        const children = [...row.children].map((child) => Math.round(child.getBoundingClientRect().left));
        return { display: style.display, columns: style.gridTemplateColumns, children };
      });
      expect(alertTable.display, `告警表格行必须使用网格布局：${JSON.stringify(alertTable)}`).toBe('grid');
      expect(new Set(alertTable.children).size, `告警表格各字段不得堆叠：${JSON.stringify(alertTable)}`).toBeGreaterThanOrEqual(4);
    }
    await page.screenshot({ path: path.join(output, `${fileName}.png`), fullPage: true });
  }
  expect(consoleErrors).toEqual([]);
});
