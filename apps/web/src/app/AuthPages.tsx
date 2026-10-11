import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, ApiError, type Policy, type Role } from '../shared/api';
import { Field, Notice } from '../shared/ui';
import { useAuth } from './Auth';

function message(error: unknown) { return error instanceof Error ? error.message : 'Не удалось выполнить запрос'; }

export function AuthPage({ register = false }: { register?: boolean }) {
  const [role, setRole] = useState<Role>('candidate');
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const auth = useAuth();
  const navigate = useNavigate();
  useEffect(() => {
    if (register) api<Policy>('/auth/registration-policy').then(setPolicy).catch((e) => setError(message(e)));
  }, [register]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(''); setBusy(true);
    const values = new FormData(event.currentTarget);
    const email = String(values.get('email'));
    try {
      await api(register ? '/auth/register' : '/auth/login', {
        method: 'POST', body: JSON.stringify({ email, password: values.get('password'),
          ...(register ? { role, consent_accepted: values.get('consent') === 'on', consent_version: policy?.version } : {}) }),
      });
      if (register) navigate('/check-email', { state: { email } });
      else { await auth.refresh(); navigate('/workspace'); }
    } catch (e) {
      if (register && e instanceof ApiError && e.code === 'MAIL_UNAVAILABLE') {
        navigate('/check-email', { state: { email, deliveryFailed: true } });
      } else setError(message(e));
    } finally { setBusy(false); }
  }

  return <main className="auth-layout">
    <section className="auth-story">
      <span className="eyebrow">ФСП СИГНАЛ</span>
      <h1>Ваши навыки.<br />Подтверждённый<br /><span>результат.</span></h1>
      <p>Покажите, что умеете. Получайте предложения с понятными задачами и открытой зарплатой.</p>
      <div className="story-path"><span>01 · Подтвердите навыки</span><span>02 · Получите предложение</span><span>03 · Выберите команду</span></div>
    </section>
    <section className="auth-card">
      <span className="eyebrow">{register ? 'НАЧАЛО ПУТИ' : 'С ВОЗВРАЩЕНИЕМ'}</span>
      <h2>{register ? 'Создайте аккаунт' : 'Войдите в Сигнал'}</h2>
      <p className="muted">{register ? 'Выберите, с какой стороны начать.' : 'Продолжите работу в своём кабинете.'}</p>
      {register && <fieldset className="role-picker"><legend className="sr-only">Ваша роль</legend>
        {(['candidate', 'employer'] as const).map((value) => <label key={value} className={role === value ? 'selected' : ''}>
          <input type="radio" name="role" value={value} checked={role === value} onChange={() => setRole(value)} />
          {value === 'candidate' ? 'Ищу работу' : 'Ищу специалиста'}
        </label>)}
      </fieldset>}
      <form onSubmit={submit}>
        <Field id="email" label="Email" name="email" type="email" autoComplete="email" required maxLength={254} placeholder="you@example.com" />
        <Field id="password" label="Пароль" name="password" type="password" autoComplete={register ? 'new-password' : 'current-password'} required minLength={12} maxLength={128} />
        <p className="hint">Не менее 12 символов.</p>
        {register && <><label className="consent"><input type="checkbox" name="consent" required />
          <span>Согласен на обработку данных для работы сервиса</span></label>
          <details className="policy"><summary>Условия обработки данных</summary><p>{policy?.text ?? 'Загружаем условия…'}</p></details></>}
        {error && <Notice error>{error}</Notice>}
        <button className="button primary wide" disabled={busy || (register && !policy)}>{busy ? 'Подождите…' : register ? 'Создать аккаунт' : 'Войти'}</button>
      </form>
      <p className="auth-switch">{register ? 'Уже есть аккаунт?' : 'Первый раз здесь?'} <Link to={register ? '/login' : '/register'}>{register ? 'Войти' : 'Зарегистрироваться'}</Link></p>
      {!register && <p className="auth-switch">Забыли пароль? <Link to="/password-reset">Восстановить доступ</Link></p>}
    </section>
  </main>;
}

export function CheckEmail({ initialEmail = '', failed = false }: { initialEmail?: string; failed?: boolean }) {
  const [email, setEmail] = useState(initialEmail);
  const [status, setStatus] = useState('');
  const [error, setError] = useState(failed ? 'Почтовый сервер недоступен. Аккаунт сохранён; попробуйте отправить письмо позже.' : '');
  const [busy, setBusy] = useState(false);
  async function resend(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setStatus('');
    try { await api('/auth/resend-verification', { method: 'POST', body: JSON.stringify({ email }) }); setStatus('Если адрес ожидает подтверждения, письмо отправлено. Проверьте также папку «Спам».'); }
    catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  }
  return <main className="centered"><section className="auth-card">
    <span className="eyebrow">ОДИН ШАГ ДО СТАРТА</span><h1>Подтвердите email</h1>
    <p className="muted">Откройте ссылку из письма. Она действует 30 минут. Если письмо не пришло, запросите новое.</p>
    <form onSubmit={resend}><Field id="resend-email" label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
      {error && <Notice error>{error}</Notice>}{status && <Notice>{status}</Notice>}
      <button className="button primary wide" disabled={busy}>{busy ? 'Отправляем…' : 'Отправить письмо повторно'}</button></form>
    <Link className="text-link" to="/login">Перейти ко входу</Link>
  </section></main>;
}

export function VerifyEmail() {
  const [token] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('token'));
  const [status, setStatus] = useState<'idle' | 'busy' | 'done' | 'error'>('idle');
  const [error, setError] = useState('');
  const auth = useAuth();
  useEffect(() => { window.history.replaceState(null, '', window.location.pathname); }, []);
  async function verify() {
    setStatus('busy');
    try { await api('/auth/verify-email', { method: 'POST', body: JSON.stringify({ token }) }); setStatus('done'); await auth.refresh(); }
    catch (e) { setError(message(e)); setStatus('error'); }
  }
  return <main className="centered"><section className="auth-card">
    <span className="eyebrow">ПОДТВЕРЖДЕНИЕ АДРЕСА</span><h1>{status === 'done' ? 'Email подтверждён' : 'Завершите регистрацию'}</h1>
    {status === 'done' ? <><p>Теперь можно продолжить работу в кабинете.</p><Link className="button primary" to={auth.user ? '/workspace' : '/login'}>Продолжить</Link></> : <>
      <p className="muted">Нажмите кнопку, чтобы подтвердить адрес. Ссылка используется один раз.</p>
      {(!token || error) && <Notice error>{error || 'В ссылке отсутствует код подтверждения'}</Notice>}
      <button className="button primary wide" disabled={!token || status === 'busy'} onClick={() => void verify()}>{status === 'busy' ? 'Проверяем…' : 'Подтвердить email'}</button>
      <Link className="text-link" to="/check-email">Запросить новое письмо</Link></>}
  </section></main>;
}

