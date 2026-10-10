import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, ApiError } from '../../shared/api';
import type { FeatureModule } from '../../shared/module';
import { Field, Notice } from '../../shared/ui';

function message(error: unknown) {
  return error instanceof ApiError
    ? error.message
    : 'Не удалось выполнить действие. Повторите попытку.';
}

// --- 1. Смена пароля в кабинете (залогинен) ------------------------------

function SecurityPage() {
  const [currentPassword, setCurrent] = useState('');
  const [newPassword, setNew] = useState('');
  const [repeatPassword, setRepeat] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const sameAsOld = newPassword.length > 0 && newPassword === currentPassword;
  const mismatch = repeatPassword.length > 0 && newPassword !== repeatPassword;
  const tooShort = newPassword.length > 0 && newPassword.length < 12;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(''); setSuccess(''); setFieldErrors({});
    if (sameAsOld) { setError('Новый пароль должен отличаться от текущего.'); return; }
    if (mismatch) { setError('Повтор пароля не совпадает.'); return; }
    if (tooShort) { setError('Новый пароль должен быть не короче 12 символов.'); return; }
    setBusy(true);
    try {
      const data = await api<{ message: string }>('/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      setSuccess(data.message);
      setCurrent(''); setNew(''); setRepeat('');
    } catch (reason) {
      setError(message(reason));
      if (reason instanceof ApiError && reason.fields) setFieldErrors(reason.fields);
    } finally { setBusy(false); }
  }

  return (
    <main className="workspace">
      <Link className="profile-back" to="/workspace">← Личный кабинет</Link>
      <span className="eyebrow">БЕЗОПАСНОСТЬ</span>
      <h1>Смена пароля</h1>
      <p className="lead">
        Укажите текущий пароль и новый. Другие активные сессии будут завершены — текущая вкладка останется.
      </p>

      <form onSubmit={submit} className="assessment-form" style={{ maxWidth: 480 }}>
        <Field id="current-password" label="Текущий пароль" type="password" autoComplete="current-password" required value={currentPassword} onChange={(e) => setCurrent(e.target.value)} error={fieldErrors.current_password} />
        <Field id="new-password" label="Новый пароль" type="password" autoComplete="new-password" minLength={12} maxLength={128} required value={newPassword} onChange={(e) => setNew(e.target.value)} hint="Не менее 12 символов" error={tooShort ? 'Не менее 12 символов' : sameAsOld ? 'Отличается от текущего' : fieldErrors.new_password} />
        <Field id="repeat-password" label="Повторите новый пароль" type="password" autoComplete="new-password" required value={repeatPassword} onChange={(e) => setRepeat(e.target.value)} error={mismatch ? 'Пароли не совпадают' : undefined} />
        {error && <Notice error>{error}</Notice>}
        {success && <Notice>{success}</Notice>}
        <button className="button primary" disabled={busy || !currentPassword || !newPassword || !repeatPassword || sameAsOld || mismatch || tooShort}>
          {busy ? 'Сохраняем…' : 'Сменить пароль'}
        </button>
      </form>
    </main>
  );
}

// --- 2. Забыл пароль — запросить ссылку (не залогинен) --------------------

export function PasswordResetRequestPage() {
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(''); setBusy(true);
    try {
      await api<{ message: string }>('/auth/password-reset/request', {
        method: 'POST',
        body: JSON.stringify({ email }),
      });
      setSent(true);
    } catch (reason) { setError(message(reason)); } finally { setBusy(false); }
  }

  return (
    <main className="centered">
      <section>
        <span className="eyebrow">ЗАБЫЛИ ПАРОЛЬ?</span>
        <h1>Сброс пароля</h1>
        {sent ? (
          <>
            <Notice>
              Если адрес <strong>{email}</strong> зарегистрирован, мы отправили на него ссылку для сброса пароля.
              Ссылка действует 30 минут и используется один раз.
            </Notice>
            <p className="auth-switch">
              Письмо не приходит?{' '}
              <button className="inline-button" onClick={() => { setSent(false); setEmail(''); }}>
                Запросить снова
              </button>
            </p>
            <p className="auth-switch">
              Вспомнили пароль? <Link to="/login">Войти</Link>
            </p>
          </>
        ) : (
          <>
            <p className="lead">
              Введите email, с которым вы регистрировались. Мы отправим на него одноразовую ссылку.
            </p>
            <form onSubmit={submit}>
              <Field id="reset-email" label="Email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
              {error && <Notice error>{error}</Notice>}
              <button className="button primary" disabled={busy || !email}>
                {busy ? 'Отправляем…' : 'Отправить ссылку'}
              </button>
            </form>
            <p className="auth-switch">
              Вспомнили пароль? <Link to="/login">Войти</Link>
            </p>
          </>
        )}
      </section>
    </main>
  );
}

// --- 3. Подтверждение сброса — ввод нового пароля (не залогинен) ----------

export function PasswordResetConfirmPage() {
  const navigate = useNavigate();
  const [token, setToken] = useState('');
  const [newPassword, setNew] = useState('');
  const [repeat, setRepeat] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Токен приходит в URL fragment (#token=XXX), чтобы не попасть в server logs
  useEffect(() => {
    const hash = window.location.hash;
    if (hash.startsWith('#token=')) setToken(hash.slice('#token='.length));
  }, []);

  const mismatch = repeat.length > 0 && newPassword !== repeat;
  const tooShort = newPassword.length > 0 && newPassword.length < 12;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(''); setSuccess('');
    if (!token) { setError('Ссылка повреждена: нет токена. Запросите новую ссылку.'); return; }
    if (tooShort) { setError('Пароль должен быть не короче 12 символов.'); return; }
    if (mismatch) { setError('Пароли не совпадают.'); return; }
    setBusy(true);
    try {
      const data = await api<{ message: string }>('/auth/password-reset/confirm', {
        method: 'POST',
        body: JSON.stringify({ token, new_password: newPassword }),
      });
      setSuccess(data.message);
      setTimeout(() => navigate('/login'), 1500);
    } catch (reason) { setError(message(reason)); } finally { setBusy(false); }
  }

  return (
    <main className="centered">
      <section>
        <span className="eyebrow">НОВЫЙ ПАРОЛЬ</span>
        <h1>Задайте новый пароль</h1>
        {!token && (
          <Notice error>
            В ссылке нет токена. Откройте её из письма целиком или{' '}
            <Link to="/password-reset">запросите новую ссылку</Link>.
          </Notice>
        )}
        <form onSubmit={submit}>
          <Field id="reset-new-password" label="Новый пароль" type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={newPassword} onChange={(e) => setNew(e.target.value)} hint="Не менее 12 символов" error={tooShort ? 'Не менее 12 символов' : undefined} />
          <Field id="reset-repeat" label="Повторите пароль" type="password" autoComplete="new-password" required value={repeat} onChange={(e) => setRepeat(e.target.value)} error={mismatch ? 'Пароли не совпадают' : undefined} />
          {error && <Notice error>{error}</Notice>}
          {success && <Notice>{success} Переходим на страницу входа…</Notice>}
          <button className="button primary" disabled={busy || !token || !newPassword || !repeat || tooShort || mismatch}>
            {busy ? 'Сохраняем…' : 'Задать новый пароль'}
          </button>
        </form>
        <p className="auth-switch">
          Вспомнили пароль? <Link to="/login">Войти</Link>
        </p>
      </section>
    </main>
  );
}


// --- Module manifest ------------------------------------------------------
// SecurityPage живёт как защищённая страница с навигацией.
// PasswordResetRequestPage и PasswordResetConfirmPage экспортируются отдельно
// и регистрируются в App.tsx как публичные роуты рядом с /login.


export const account: FeatureModule = {
  routes: [
    { path: '/account/security', element: <SecurityPage />, roles: ['candidate', 'employer'] },
  ],
  navigation: [
    { to: '/account/security', label: 'Пароль', roles: ['candidate', 'employer'] },
  ],
};
