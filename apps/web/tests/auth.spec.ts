import { expect, test } from '@playwright/test';

for (const role of ['candidate', 'employer'] as const) {
  test(`registration, mail verification, login and logout: ${role}`, async ({ page, request }) => {
    const email = `${role}-${Date.now()}@example.com`;
    await page.goto('/register');
    await page.getByRole('radio', { name: role === 'candidate' ? 'Ищу работу' : 'Ищу специалиста' }).check();
    await page.getByLabel('Email', { exact: true }).fill(email);
    await page.getByLabel('Пароль', { exact: true }).fill('correct horse battery');
    await page.getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Создать аккаунт' }).click();
    await expect(page).toHaveURL(/check-email/);
    let messageId = '';
    await expect.poll(async () => {
      const result = await request.get(`http://localhost:8025/api/v1/search?query=${encodeURIComponent(`to:${email}`)}`);
      const inbox = await result.json();
      messageId = inbox.messages?.[0]?.ID ?? '';
      return messageId;
    }).not.toBe('');
    const mail = await (await request.get(`http://localhost:8025/api/v1/message/${messageId}`)).json();
    const link = String(mail.Text).match(/https?:\/\/[^\s]+\/verify-email#token=[^\s]+/)?.[0];
    expect(link).toBeTruthy();
    await page.goto(link!);
    await page.getByRole('button', { name: 'Подтвердить email' }).click();
    await expect(page.getByRole('heading', { name: 'Email подтверждён' })).toBeVisible();
    await page.getByRole('link', { name: 'Продолжить', exact: true }).click();
    await page.getByLabel('Email', { exact: true }).fill(email);
    await page.getByLabel('Пароль', { exact: true }).fill('correct horse battery');
    await page.getByRole('button', { name: 'Войти', exact: true }).click();
    await expect(page).toHaveURL(/workspace/);
    await expect(page.getByText('Email подтверждён. Ваш аккаунт готов к работе.')).toBeVisible();
    await page.reload();
    await expect(page.getByRole('button', { name: 'Выйти' })).toBeVisible();
    await page.getByRole('button', { name: 'Выйти' }).click();
    await expect(page).toHaveURL(/login/);
    await page.goto('/workspace');
    await expect(page).toHaveURL(/login/);
  });
}
