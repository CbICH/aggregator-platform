import { expect, test } from '@playwright/test';

test('candidate saves a private profile, updates it and handles a stale tab', async ({ page, request, context }, testInfo) => {
  const email = `profile-${Date.now()}@example.com`;
  const password = 'correct horse battery';
  const registration = await request.post('/api/v1/auth/register', { data: {
    email, password, role: 'candidate', consent_accepted: true, consent_version: 'registration-v1',
  } });
  expect(registration.status()).toBe(202);
  let messageId = '';
  await expect.poll(async () => {
    const inbox = await (await request.get(`http://localhost:8025/api/v1/search?query=${encodeURIComponent(`to:${email}`)}`)).json();
    messageId = inbox.messages?.[0]?.ID ?? '';
    return messageId;
  }).not.toBe('');
  const mail = await (await request.get(`http://localhost:8025/api/v1/message/${messageId}`)).json();
  const token = String(mail.Text).match(/#token=([^\s]+)/)?.[1];
  expect(token).toBeTruthy();
  expect((await request.post('/api/v1/auth/verify-email', { data: { token } })).ok()).toBeTruthy();

  await page.goto('/login');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Пароль', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Войти', exact: true }).click();
  await page.getByRole('link', { name: 'Заполнить профиль' }).click();
  await expect(page.getByRole('heading', { name: 'Расскажите о себе' })).toBeVisible();
  await expect(page.getByLabel('Контактный email')).toHaveValue(email);
  await expect(page.getByLabel('ФИО')).toHaveValue('');
  await page.getByLabel('ФИО').fill('Анна Тестовая');
  await page.getByRole('checkbox', { name: 'Backend', exact: true }).check();
  await page.getByLabel('Стаж в месяцах').fill('18');
  await page.getByLabel('Технологии', { exact: true }).fill('Python, PostgreSQL');
  await page.getByLabel('Софт-скиллы').fill('Работа в команде, коммуникация');
  await page.getByLabel('О себе и опыте').fill('Разрабатывала API и интеграции.');
  await page.getByLabel('Телефон', { exact: true }).fill('+7 900 000-00-00');
  await page.getByLabel('Предпочтительный способ связи').fill('Написать на email');
  await page.getByRole('checkbox', { name: 'Согласен на обработку данных моего профиля и резюме' }).check();
  await page.getByRole('button', { name: 'Сохранить профиль', exact: true }).click();
  await expect(page.getByText('Профиль сохранён. Данные доступны только вам.')).toBeVisible();
  await expect(page.getByText('Основные сведения заполнены.')).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('ФИО')).toHaveValue('Анна Тестовая');
  await expect(page.getByLabel('Технологии', { exact: true })).toHaveValue('python, postgresql');
  await expect(page.getByLabel('Телефон', { exact: true })).toHaveValue('+7 900 000-00-00');
  await expect(page.getByRole('checkbox', { name: 'Согласен на обработку данных моего профиля и резюме' })).toHaveCount(0);

  const stalePage = await context.newPage();
  await stalePage.goto('/candidate/profile');
  await expect(stalePage.getByLabel('ФИО')).toHaveValue('Анна Тестовая');
  await page.getByLabel('О себе и опыте').fill('Обновлённое резюме.');
  await page.getByRole('button', { name: 'Сохранить профиль', exact: true }).click();
  await expect(page.getByText('Профиль сохранён. Данные доступны только вам.')).toBeVisible();
  await stalePage.getByLabel('ФИО').fill('Несохранённая версия');
  await stalePage.getByRole('button', { name: 'Сохранить профиль', exact: true }).click();
  await expect(stalePage.getByRole('alert')).toContainText('Профиль изменился в другой вкладке');
  await expect(stalePage.getByLabel('ФИО')).toHaveValue('Несохранённая версия');
  await stalePage.getByRole('button', { name: 'Загрузить сохранённую версию' }).click();
  await expect(stalePage.getByLabel('ФИО')).toHaveValue('Анна Тестовая');
  await expect(stalePage.getByLabel('О себе и опыте')).toHaveValue('Обновлённое резюме.');
  const saved = await (await page.request.get('/api/v1/candidate/profile')).json();
  expect(saved.privacy.publication_enabled).toBe(false);
  expect(saved.privacy.discoverable).toBe(false);
  expect(saved.verified_category).toBeNull();
  await stalePage.close();
  await page.screenshot({ path: testInfo.outputPath('profile-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: testInfo.outputPath('profile-mobile.png'), fullPage: true });
});
