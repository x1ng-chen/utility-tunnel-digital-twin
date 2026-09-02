const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');

const webUrl = process.env.E2E_WEB_URL || 'http://127.0.0.1:5173';
const adminPassword = '123';
const mapTilePattern = /https?:\/\/(?:[^/]+\.)?tile\.openstreetmap\.org\/.*/i;
const transparentMapTile = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
  'base64',
);
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

async function loginAsAdministrator(page) {
  await page.getByLabel('账号或邮箱').fill('admin');
  await page.getByLabel('密码').fill(adminPassword);
  await page.getByRole('button', { name: /安全登录/ }).click();
  await expect(page.getByRole('heading', { name: '运行，一眼掌握' })).toBeVisible();
}

async function openAuthenticatedPage(page, route) {
  await page.goto(`${webUrl}${route}`);
  // The visual audit intentionally performs full document navigations. Keep it
  // independent from token state left by earlier business scenarios: auth is
  // tested separately, while this test owns re-establishing its visual session.
  if (await page.getByLabel('账号或邮箱').isVisible()) {
    await loginAsAdministrator(page);
    if (route !== '/dashboard') await page.goto(`${webUrl}${route}`);
  }
}

async function isolateMapTiles(page) {
  await page.route(mapTilePattern, (route) => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: transparentMapTile,
  }));
}

async function inspectDesktopLayout(page, heading) {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  });
  const layout = await page.evaluate(() => {
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const visible = (element) => {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity) > 0 && rect.width > 0 && rect.height > 0;
    };
    const outsideViewport = [...document.querySelectorAll('body *')]
      .filter(visible)
      .map((element) => {
        const rect = element.getBoundingClientRect();
        return {
          tag: element.tagName,
          className: String(element.className || ''),
          left: Math.round(rect.left),
          right: Math.round(rect.right),
        };
      })
      .filter((item) => item.left < -1 || item.right > viewportWidth + 1)
      .sort((a, b) => Math.max(Math.abs(b.left), b.right - viewportWidth) - Math.max(Math.abs(a.left), a.right - viewportWidth))
      .slice(0, 8);
    const clippedControls = [...document.querySelectorAll('button, a, input, select')]
      .filter(visible)
      .map((element) => {
        const rect = element.getBoundingClientRect();
        return {
          label: (element.getAttribute('aria-label') || element.textContent || '').trim().slice(0, 40),
          width: Math.round(rect.width),
          height: Math.round(rect.height),
          scrollWidth: element.scrollWidth,
          scrollHeight: element.scrollHeight,
        };
      })
      .filter((item) => item.scrollWidth > item.width + 3 || item.scrollHeight > item.height + 3)
      .slice(0, 8);
    const sidebar = document.querySelector('.sidebar')?.getBoundingClientRect();
    const content = document.querySelector('.page-content')?.getBoundingClientRect();
    return {
      viewportWidth,
      viewportHeight,
      documentWidth: document.documentElement.scrollWidth,
      sidebarWidth: sidebar?.width || 0,
      contentLeft: content?.left || 0,
      contentRight: content?.right || 0,
      outsideViewport,
      clippedControls,
    };
  });
  expect(layout.documentWidth, `${heading} 不应产生整页横向滚动：${JSON.stringify(layout.outsideViewport)}`).toBeLessThanOrEqual(layout.viewportWidth + 1);
  expect(layout.contentLeft, `${heading} 内容区不得压入侧栏`).toBeGreaterThanOrEqual(layout.sidebarWidth - 1);
  expect(layout.contentRight, `${heading} 内容区不得越过视口`).toBeLessThanOrEqual(layout.viewportWidth + 1);
  expect(layout.clippedControls, `${heading} 存在尺寸过小或文字裁切的控件`).toEqual([]);
  const contentOpacity = await page.locator('.page-content > *').first().evaluate((element) => Number(getComputedStyle(element).opacity));
  expect(contentOpacity, `${heading} 首屏内容不得被过渡动画隐藏`).toBeGreaterThanOrEqual(.99);
}

test('全部业务页面通过桌面端布局巡检', async ({ page }) => {
  test.setTimeout(120_000);
  const consoleErrors = [];
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  page.on('pageerror', (error) => consoleErrors.push(error.message));
  await isolateMapTiles(page);
  await page.goto(webUrl);
  await loginAsAdministrator(page);

  const output = path.resolve(__dirname, '../../test-results/visual-audit');
  fs.mkdirSync(output, { recursive: true });
  for (const [route, heading, fileName] of pages) {
    await openAuthenticatedPage(page, route);
    await expect(page.getByRole('heading', { name: heading })).toBeVisible();
    await page.waitForTimeout(route === '/twin-3d' ? 1_500 : 1_200);
    await inspectDesktopLayout(page, heading);
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

test('全部业务页面通过三档桌面分辨率布局巡检', async ({ page }) => {
  test.setTimeout(240_000);
  const consoleErrors = [];
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  page.on('pageerror', (error) => consoleErrors.push(error.message));
  await isolateMapTiles(page);

  for (const viewport of [
    { width: 1366, height: 768 },
    { width: 1600, height: 900 },
    { width: 1920, height: 1080 },
  ]) {
    await page.setViewportSize(viewport);
    for (const [route, heading] of pages) {
      await openAuthenticatedPage(page, route);
      await expect(page.getByRole('heading', { name: heading })).toBeVisible();
      await page.waitForTimeout(route === '/twin-3d' ? 1_500 : 900);
      await inspectDesktopLayout(page, `${heading}（${viewport.width}×${viewport.height}）`);
    }
  }
  expect(consoleErrors).toEqual([]);
});
