import { expect, test } from '@playwright/test'

test('会话新建与重命名', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: '新建会话' }).click()
  await expect(page.locator('.session-item')).toHaveCount(2)
  await page.locator('.session-item').first().getByRole('button', { name: '改名' }).click()
})

test('打开设置并保存', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: '设置' }).click()
  await page.getByPlaceholder('sk-...').fill('sk-demo')
  await page.getByRole('button', { name: '保存' }).click()
  await expect(page.locator('.settings-drawer')).toHaveCount(0)
})

test('触发补全与流式演示', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: '补全 PoC' }).click()
  await page.getByRole('button', { name: '流式演示' }).click()
  await expect(page.locator('.stream-content')).toBeVisible()
})
