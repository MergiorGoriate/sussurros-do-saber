const {test, expect} = require('@playwright/test');

test('learning resources open lessons and explain answers', async ({page}) => {
  await page.goto('/aprender');
  const card = page.locator('.learning-card[data-resource-id="8"]');
  await card.locator('.open-learning-resource').click();
  const dialog = page.locator('#learning-lesson-8');
  await expect(dialog).toBeVisible();
  await dialog.getByLabel('3', {exact: true}).check();
  await dialog.getByRole('button', {name: 'Verificar resposta', exact: true}).click();
  await expect(dialog.locator('.learning-feedback')).toHaveText('Resposta correcta.');
  await expect(dialog.locator('.learning-explanation')).toBeVisible();
  await dialog.getByRole('button', {name: 'Recomeçar exercício'}).click();
  await expect(dialog.locator('.learning-explanation')).toBeHidden();
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
});

test('collection supports removal and accent-insensitive search', async ({page}) => {
  await page.addInitScript(() => localStorage.removeItem('learningCollection'));
  await page.goto('/aprender');
  const card = page.locator('.learning-card[data-resource-id="7"]');
  await page.locator('#resourceSearch').fill('hipoteses');
  await expect(card).toBeVisible();
  await expect(page.locator('#resourceCount')).toHaveText('1');
  await card.locator('.save-resource').click();
  await page.locator('#savedFilter').check();
  await expect(card).toBeVisible();
  await card.locator('.save-resource').click();
  await expect(page.locator('#resourceEmpty')).toBeVisible();
  await page.locator('#clearLearningFilters').click();
  await expect(page.locator('#resourceCount')).toHaveText('9');
});
