const { test, expect } = require('@playwright/test');
const { randomUUID } = require('node:crypto');

const baseURL = process.env.E2E_BASE_URL || 'http://127.0.0.1:18080';
const password = 'secret123';

test('xhs analysis center smoke flow with real backend', async ({ page }) => {
  const username = `analysis_e2e_${randomUUID().replace(/-/g, '').slice(0, 16)}`;

  await page.goto(`${baseURL}/login`);
  await page.getByText('注册').click();
  await page.getByPlaceholder('请输入账号').fill(username);
  await page.getByPlaceholder('请输入密码').fill(password);
  await page.getByPlaceholder('请再次输入密码').fill(password);
  await page.getByRole('button', { name: /创建并进入/ }).click();

  await expect(page.getByText('选择平台工作区')).toBeVisible({ timeout: 15000 });
  await page.getByRole('heading', { name: '小红书' }).click();
  await expect(page).toHaveURL(/\/platforms\/xhs\/dashboard/, { timeout: 15000 });

  const groupName = `E2E分析组-${randomUUID().replace(/-/g, '').slice(0, 8)}`;

  await page.goto(`${baseURL}/platforms/xhs/keywords`);
  await expect(page.getByText('关键词组')).toBeVisible({ timeout: 15000 });
  await page.getByPlaceholder('关键词组名称').fill(groupName);
  await page.getByPlaceholder('关键词，用逗号或换行分隔').fill('Claude Code,AI编程,Cursor');
  await page.getByRole('button', { name: /创建/ }).click();
  await expect(page.getByText('关键词组已创建。')).toBeVisible({ timeout: 15000 });

  const analyzeButton = page.getByRole('button', { name: /分析/ }).first();
  await expect(analyzeButton).toBeVisible({ timeout: 15000 });
  await analyzeButton.click();
  await expect(page).toHaveURL(/\/platforms\/xhs\/analytics\?keyword_group_id=\d+/, { timeout: 15000 });

  await expect(page.getByRole('heading', { name: '小红书分析中心' })).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole('dialog')).toBeVisible({ timeout: 15000 });
  await expect(page.getByText('选择范围')).toBeVisible();
  await expect(page.locator(`input[value="${groupName} - 小红书分析报告"]`)).toBeVisible({ timeout: 15000 });

  await page.getByRole('button', { name: /检查数据健康/ }).click();
  await expect(page.getByText(/当前数据低于最低门槛|当前数据达到生成门槛/)).toBeVisible({ timeout: 15000 });

  const blocked = page.getByText('当前数据低于最低门槛');
  if (await blocked.isVisible().catch(() => false)) {
    await expect(page.getByText('缺口')).toBeVisible();
    await expect(page.getByText('采集建议')).toBeVisible();
  }

  await page.getByRole('button', { name: /进入生成确认/ }).click();
  await expect(page.getByText('生成确认')).toBeVisible({ timeout: 15000 });

  const generateButton = page.getByRole('button', { name: /生成报告/ });
  await expect(generateButton).toBeVisible();
  await expect(generateButton).toBeDisabled();
});
