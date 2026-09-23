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

test.beforeEach(async ({ context }) => {
  if (process.env.E2E_API_URL) {
    await context.addInitScript((url) => localStorage.setItem('vue-api-url', url), process.env.E2E_API_URL);
  }
});

test('正常特效光标覆盖侧栏与全屏并在窄屏恢复系统指针', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await openAuthenticatedPage(page, '/twin-3d');
  const cursor = page.locator('.experience-cursor');
  await expect(cursor).toHaveCount(1);
  await page.mouse.move(40, 210);
  await expect(cursor).toHaveClass(/active/);
  expect(await cursor.evaluate((el) => Number(getComputedStyle(el).zIndex)))
    .toBeGreaterThan(await page.locator('.command-sidebar').evaluate((el) => Number(getComputedStyle(el).zIndex)));
  await page.getByRole('button', { name: '全屏查看', exact: true }).click();
  await expect.poll(() => page.evaluate(() => !!document.fullscreenElement?.contains(document.querySelector('.experience-cursor')))).toBe(true);
  await page.mouse.move(420, 900);
  await page.mouse.down();
  await page.mouse.move(700, 900, { steps: 12 });
  await page.mouse.up();
  await expect(cursor).toHaveCSS('opacity', '1');
  expect(await cursor.evaluate((el) => el.style.transform)).toBe('translate3d(700px, 900px, 0px)');
  await page.evaluate(() => document.exitFullscreen());
  await expect.poll(() => cursor.evaluate((el) => el.parentElement.tagName)).toBe('BODY');
  await page.setViewportSize({ width: 600, height: 844 });
  await expect(cursor).toHaveCount(0);
  expect(await page.locator('button').first().evaluate((el) => getComputedStyle(el).cursor)).not.toBe('none');
  await page.setViewportSize({ width: 1440, height: 960 });
  await expect(cursor).toHaveCount(1);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(cursor).toHaveCount(0);
  expect(await page.locator('button').first().evaluate((el) => getComputedStyle(el).cursor)).not.toBe('none');
});

test('收起侧栏在普通与低高度窗口中保留全部导航入口', async ({ page }) => {
  await isolateMapTiles(page);
  await openAuthenticatedPage(page, '/dashboard');
  await page.getByRole('button', { name: '收起侧边栏', exact: true }).click();
  for (const viewport of [{ width: 1440, height: 960 }, { width: 1366, height: 600 }]) {
    await page.setViewportSize(viewport);
    const sidebar = page.getByRole('complementary', { name: '主导航' });
    const navigation = sidebar.locator('.command-nav');
    await expect(navigation.locator('.nav-item')).toHaveCount(pages.length);
    for (const [, , name] of pages) {
      const button = navigation.getByRole('button', { name, exact: true });
      await button.scrollIntoViewIfNeeded();
      const geometry = await button.evaluate((element) => {
        const box = element.getBoundingClientRect();
        const icon = element.querySelector('svg').getBoundingClientRect();
        const nav = element.closest('.command-nav').getBoundingClientRect();
        return {
          centeredX: Math.abs(icon.x + icon.width / 2 - box.x - box.width / 2),
          centeredY: Math.abs(icon.y + icon.height / 2 - box.y - box.height / 2),
          inside: box.top >= nav.top - 1 && box.bottom <= nav.bottom + 1,
          height: box.height,
        };
      });
      expect(geometry.inside, `${name} 必须能滚动到完整可见位置`).toBe(true);
      expect(geometry.height).toBeGreaterThanOrEqual(44);
      expect(geometry.centeredX).toBeLessThanOrEqual(1);
      expect(geometry.centeredY).toBeLessThanOrEqual(1);
    }
    await expect(sidebar.getByRole('button', { name: '退出登录', exact: true })).toBeInViewport();
    await expect(sidebar.getByRole('button', { name: '展开侧边栏', exact: true })).toBeInViewport();
  }
  await page.getByRole('button', { name: '展开侧边栏', exact: true }).click();
  await expect(page.getByRole('button', { name: '收起侧边栏', exact: true })).toBeVisible();
});

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

test('全部业务页面在窄屏保留全宽内容与底部导航', async ({ page }) => {
  test.setTimeout(180_000);
  await isolateMapTiles(page);
  const output = path.resolve(__dirname, '../../output/playwright/mobile-audit');
  fs.mkdirSync(output, { recursive: true });
  for (const viewport of [{ width: 390, height: 844 }, { width: 768, height: 1024 }]) {
    await page.setViewportSize(viewport);
    for (const [route, heading, fileName] of pages) {
      await openAuthenticatedPage(page, route);
      await expect(page.getByRole('heading', { name: heading })).toBeVisible();
      await page.evaluate(async () => {
        await document.fonts.ready;
        await Promise.all(document.getAnimations()
          .filter((animation) => animation.effect?.getTiming().iterations !== Infinity)
          .map((animation) => animation.finished.catch(() => {})));
      });
      // A route rebuild can expose the shell for one frame before the global
      // command layout finishes applying. Position alone is insufficient:
      // require the final fixed geometry before measuring this page, otherwise
      // the audit can inspect a transient sidebar flowing below long content.
      await expect.poll(() => page.locator('.command-sidebar').evaluate((element) => {
        const box = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return style.position === 'fixed'
          && Math.abs(box.bottom - innerHeight) <= 1
          && box.height <= 70;
      }), { timeout: 10_000 }).toBe(true);
      const dimensions = await page.evaluate(() => {
        const sidebar = document.querySelector('.command-sidebar').getBoundingClientRect();
        const main = document.querySelector('.command-main').getBoundingClientRect();
        return { width: innerWidth, height: innerHeight, documentWidth: document.documentElement.scrollWidth,
          sidebar: { x: sidebar.x, bottom: sidebar.bottom, height: sidebar.height, width: sidebar.width },
          main: { x: main.x, right: main.right } };
      });
      expect(dimensions.documentWidth, `${heading} 不得让整页横向溢出`).toBeLessThanOrEqual(viewport.width + 1);
      expect(dimensions.main.x, `${heading} 不得保留桌面侧栏占位`).toBeLessThanOrEqual(1);
      expect(dimensions.main.right).toBeLessThanOrEqual(viewport.width + 1);
      expect(dimensions.sidebar.x).toBe(0);
      expect(dimensions.sidebar.width).toBe(viewport.width);
      expect(dimensions.sidebar.bottom).toBe(viewport.height);
      expect(dimensions.sidebar.height).toBeLessThanOrEqual(70);
      await expect(page.locator('.compact-logout')).toBeInViewport();
      if (route === '/dashboard' && viewport.width <= 600) {
        const nodes = await page.locator('.tunnel-map .map-node').evaluateAll((elements) => elements.map((element) => {
          const box = element.getBoundingClientRect();
          return { x: box.x, y: box.y, right: box.right, bottom: box.bottom, height: box.height };
        }));
        expect(nodes.length).toBeGreaterThan(0);
        for (let index = 0; index < nodes.length; index += 1) {
          expect(nodes[index].height).toBeGreaterThanOrEqual(44);
          for (const other of nodes.slice(index + 1)) {
            const overlaps = nodes[index].x < other.right && nodes[index].right > other.x
              && nodes[index].y < other.bottom && nodes[index].bottom > other.y;
            expect(overlaps, '手机设备入口不能互相遮挡').toBe(false);
          }
        }
      }
      await page.screenshot({ path: path.join(output, `${viewport.width}-${fileName}.png`), fullPage: true });
    }
  }
});

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
    if (route === '/alerts' || route === '/assets') {
      const report = route === '/alerts' ? 'alerts' : 'assets';
      const button = page.getByRole('button', { name: route === '/alerts' ? '导出全部告警' : '导出全部设备', exact: true });
      const downloadPromise = page.waitForEvent('download');
      await button.click();
      const download = await downloadPromise;
      expect(download.suggestedFilename()).toContain(`utility-tunnel-${report}-`);
      expect(await download.failure()).toBeNull();
      await expect(button).toBeEnabled();
    }
    if (route === '/assets') {
      const alarmCard = page.locator('.asset-card-button').filter({ has: page.locator('.asset-status.alarm') }).first();
      await alarmCard.click();
      await expect(page.locator('.detail-heading .asset-status')).toHaveClass(/alarm/);
      await expect(page.locator('.detail-heading .asset-status')).toHaveText('告警');
      await expect(page.locator('.asset-map-node.selected')).toHaveClass(/alarm/);
    }
    if (route === '/gis') {
      await expect(page.locator('.gis-marker.alarm').first()).toBeVisible();
      await expect(page.locator('.gis-module-list button > i.alarm').first()).toBeVisible();
      await expect(page.locator('.gis-legend')).toContainText('告警');
      await expect(page.locator('.gis-marker.alarm i').first()).toHaveCSS('background-color', 'rgb(255, 77, 97)');
    }
    if (route === '/twin-3d') {
      const gap = await page.locator('.twin-stage-panel').evaluate((stage) => {
        const scene = stage.querySelector('.twin-scene');
        return stage.getBoundingClientRect().bottom - scene.getBoundingClientRect().bottom;
      });
      expect(gap, '三维画布应填满被详情面板撑高的容器').toBeLessThanOrEqual(2);
    }
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
