import { expect, test, type BrowserContext, type Page } from '@playwright/test';

const password = 'correct horse battery';
async function login(page: Page, email: string) {
  await page.goto('/login');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Пароль', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Войти', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Начните с ваших навыков' }).or(page.getByRole('heading', { name: 'Найдите человека для ваших задач' }))).toBeVisible();
}
async function csrf(context: BrowserContext) { return (await context.cookies()).find((cookie) => cookie.name === 'signal_csrf')?.value ?? ''; }

test('D: publication, immutable invitation, acceptance, contacts, revocation and decline across two roles', async ({ browser }, testInfo) => {
  const candidateContext = await browser.newContext();
  const employerContext = await browser.newContext();
  const otherContext = await browser.newContext();
  const candidate = await candidateContext.newPage();
  const employer = await employerContext.newPage();
  const other = await otherContext.newPage();
  await login(candidate, 'd01@example.com');
  await candidate.goto('/candidate/privacy');
  const publication = candidate.getByRole('checkbox', { name: 'Разрешаю публикацию моего профиля работодателям' });
  await publication.check();
  await candidate.getByRole('button', { name: 'Сохранить настройки', exact: true }).click();
  await expect(candidate.getByRole('heading', { name: 'Профиль доступен работодателям' })).toBeVisible();

  await login(employer, 'e01@example.com');
  await employer.goto('/employer/candidates');
  await expect(employer.getByRole('heading', { name: 'Кандидат D01', exact: true })).toBeVisible();
  await expect(employer.getByText('d01@example.com', { exact: true })).toHaveCount(0);
  await employer.getByRole('article').filter({ has: employer.getByRole('heading', { name: 'Кандидат D01', exact: true }) }).getByRole('link', { name: 'Предложить работу' }).click();
  const description = `Разрабатывайте API и интеграции в нашей команде. ${Date.now()}`;
  await employer.getByLabel('Описание предложения').fill(description);
  await employer.getByLabel('Зарплата от, ₽').fill('120000');
  await employer.getByLabel('Зарплата до, ₽').fill('160000');
  await employer.getByRole('checkbox', { name: 'python · 80/100' }).check();
  await employer.getByRole('button', { name: 'Отправить приглашение' }).click();
  await expect(employer.getByText(description, { exact: true })).toBeVisible();
  await expect(employer.getByText('120 000–160 000 ₽ в месяц до вычета налогов', { exact: true })).toBeVisible();
  const iid = employer.url().split('/').pop()!;
  const contactPath = '/api/v1/employer/candidates/10000000-0000-4000-8000-000000000001/contacts';
  expect((await employerContext.request.get(contactPath)).status()).toBe(404);

  await candidate.goto('/candidate/invitations');
  await candidate.getByRole('article').filter({ hasText: description }).getByRole('link', { name: 'Открыть предложение' }).click();
  await expect(candidate.getByText('Просмотрено', { exact: true })).toBeVisible();
  await expect(candidate.getByRole('button', { name: 'Принять предложение' })).toBeDisabled();
  await candidate.getByRole('checkbox', { name: /Разрешаю передать мои контакты компании/ }).check();
  await candidate.getByRole('button', { name: 'Принять предложение' }).click();
  await expect(candidate.getByText('Предложение принято. Компания может получить контакты.')).toBeVisible();
  await candidate.screenshot({ path: testInfo.outputPath('accepted-candidate.png'), fullPage: true });
  await candidate.setViewportSize({ width: 390, height: 844 });
  expect(await candidate.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await candidate.screenshot({ path: testInfo.outputPath('accepted-mobile.png'), fullPage: true });
  await candidate.setViewportSize({ width: 1280, height: 720 });
  await employer.getByRole('button', { name: 'Обновить предложение' }).click();
  await employer.getByRole('link', { name: 'Открыть контакты' }).click();
  await expect(employer.getByText('Email: d01@example.com', { exact: true })).toBeVisible();
  await employer.screenshot({ path: testInfo.outputPath('contacts-employer.png'), fullPage: true });

  await login(other, 'e02@example.com');
  expect((await otherContext.request.get(contactPath)).status()).toBe(404);
  await other.goto(`/employer/invitations/${iid}`);
  await expect(other.getByRole('alert')).toContainText('Предложение недоступно');
  await expect(other.getByText(description, { exact: true })).toHaveCount(0);

  await candidate.goto('/candidate/privacy');
  await candidate.screenshot({ path: testInfo.outputPath('privacy-candidate.png'), fullPage: true });
  await candidate.getByRole('button', { name: 'Скрыть профиль', exact: true }).click();
  await expect(candidate.getByRole('heading', { name: 'Профиль пока не виден в подборках' })).toBeVisible();
  expect((await employerContext.request.get('/api/v1/employer/candidates/10000000-0000-4000-8000-000000000001')).status()).toBe(404);
  expect((await employerContext.request.get(contactPath)).status()).toBe(200);
  await candidate.getByRole('button', { name: 'Отозвать доступ к контактам', exact: true }).click();
  await expect(candidate.getByRole('status')).toContainText('Настройки сохранены.');
  await employer.getByRole('button', { name: 'Обновить доступ' }).click();
  await expect(employer.getByRole('alert')).toContainText('Контакты недоступны');
  await expect(employer.getByText('Email: d01@example.com', { exact: true })).toHaveCount(0);
  const replay = await candidateContext.request.post(`/api/v1/invitations/${iid}/decision`, { headers: { 'X-CSRF-Token': await csrf(candidateContext) }, data: { action: 'accept', expected_version: 1, contact_consent_accepted: true, contact_consent_version: 'contact-transfer-v1' } });
  expect(replay.status()).toBe(200);
  expect((await replay.json()).contact_access_active).toBe(false);

  await employer.goto('/employer/candidates');
  await employer.getByRole('article').filter({ has: employer.getByRole('heading', { name: 'Кандидат D02', exact: true }) }).getByRole('link', { name: 'Предложить работу' }).click();
  await employer.getByLabel('Описание предложения').fill('Ещё одно предложение для проверки отказа без раскрытия контактов.');
  await employer.getByLabel('Зарплата от, ₽').fill('90000');
  await employer.getByLabel('Зарплата до, ₽').fill('110000');
  await employer.getByRole('button', { name: 'Отправить приглашение' }).click();
  await expect(employer.getByText('Отправлено', { exact: true })).toBeVisible();
  const declinedId = employer.url().split('/').pop()!;
  await candidateContext.clearCookies();
  await login(candidate, 'd02@example.com');
  await candidate.goto(`/candidate/invitations/${declinedId}`);
  await candidate.getByRole('button', { name: 'Отклонить', exact: true }).click();
  await expect(candidate.getByText('Предложение отклонено. Оно не даёт компании доступ к контактам.')).toBeVisible();
  expect((await employerContext.request.get('/api/v1/employer/candidates/10000000-0000-4000-8000-000000000002/contacts')).status()).toBe(404);
  await candidate.goto('/candidate/profile');
  const downloadPromise = candidate.waitForEvent('download');
  await candidate.getByRole('button', { name: 'Скачать PDF', exact: true }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('fsp-signal-profile.pdf');
  await download.saveAs(testInfo.outputPath('owner-profile.pdf'));
  await candidateContext.close(); await employerContext.close(); await otherContext.close();
});
