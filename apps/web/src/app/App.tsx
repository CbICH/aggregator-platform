import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useState, type ReactNode } from 'react';
import { AuthProvider, useAuth } from './Auth';
import { AuthPage, CheckEmail, VerifyEmail } from './AuthPages';
import { Notice } from '../shared/ui';
import type { Role } from '../shared/api';
import { assessment } from '../features/assessment';
import { matching } from '../features/matching';
import { profile } from '../features/profile';
import { invitations } from '../features/invitations';

const features = [assessment, matching, profile, invitations];

function Guard({ children, roles }: { children: ReactNode; roles?: Role[] }) {
  const auth = useAuth();
  if (auth.loading) return <main className="centered"><p role="status">Загружаем кабинет…</p></main>;
  if (auth.error) return <main className="centered"><Notice error>{auth.error} <button className="button" onClick={() => void auth.refresh()}>Повторить</button></Notice></main>;
  if (!auth.user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(auth.user.role)) return <main className="centered"><Notice error>Этот раздел недоступен для вашей роли.</Notice></main>;
  return children;
}

function Header() {
  const { user, logout } = useAuth();
  const [error, setError] = useState('');
  return <><header className="topbar"><Link to={user ? '/workspace' : '/'} className="brand"><span className="brand-icon">С</span>ФСП <strong>Сигнал</strong></Link>
    <nav aria-label="Основная навигация">{user ? <><span className="role-badge">{user.role === 'candidate' ? 'Кандидат' : 'Работодатель'}</span>
      {features.flatMap((feature) => feature.navigation).filter((item) => item.roles.includes(user.role)).map((item) => <Link key={item.to} to={item.to}>{item.label}</Link>)}
      <button className="button ghost" onClick={() => { setError(''); void logout().catch(() => setError('Не удалось выйти. Повторите попытку.')); }}>Выйти</button></> : <Link className="button ghost" to="/login">Войти</Link>}</nav>
  </header>{error && <Notice error>{error}</Notice>}</>;
}

function Workspace() {
  const { user, refresh } = useAuth();
  return <main className="workspace"><span className="eyebrow">ЛИЧНЫЙ КАБИНЕТ</span>
    <h1>{user?.role === 'candidate' ? 'Начните с ваших навыков' : 'Найдите человека для ваших задач'}</h1>
    <p className="lead">{user?.email}</p>
    {!user?.email_verified ? <Notice>Подтвердите email, чтобы продолжить. <Link to="/check-email">Отправить письмо</Link> · <button className="inline-button" onClick={() => void refresh()}>Я подтвердил адрес</button></Notice> : <Notice>Email подтверждён. Ваш аккаунт готов к работе.</Notice>}
    <div className="module-grid">{(user?.role === 'candidate' ? [
      ['01', 'Профиль', 'Расскажите об опыте и выберите, что увидит работодатель.'],
      ['02', 'Подтверждение навыков', 'Пройдите тест и получите подтверждённую категорию.'],
      ['03', 'Предложения', 'Сравните задачи и зарплату, затем выберите подходящую команду.'],
    ] : [
      ['01', 'Потребность команды', 'Опишите задачи будущего сотрудника и нужные навыки.'],
      ['02', 'Подбор специалистов', 'Оцените подтверждённые навыки и основания рекомендации.'],
      ['03', 'Приглашения', 'Предложите кандидату конкретную работу и зарплату.'],
    ]).map(([number, title, text]) => <section className="module-card" key={number}><span className="step-number">{number}</span><h2>{title}</h2><p>{text}</p><span className="coming-soon">Скоро будет доступно</span></section>)}</div>
  </main>;
}

function MailPage() {
  const location = useLocation();
  const { user } = useAuth();
  const state = location.state as { email?: string; deliveryFailed?: boolean } | null;
  return <CheckEmail initialEmail={state?.email ?? user?.email ?? ''} failed={state?.deliveryFailed} />;
}

function Root() {
  const { user, loading } = useAuth();
  return loading ? <main className="centered"><p>Загрузка…</p></main> : <Navigate to={user ? '/workspace' : '/register'} replace />;
}

export function App() {
  return <AuthProvider><Header /><Routes>
    <Route path="/" element={<Root />} />
    <Route path="/register" element={<AuthPage key="register" register />} />
    <Route path="/login" element={<AuthPage key="login" />} />
    <Route path="/check-email" element={<MailPage />} />
    <Route path="/verify-email" element={<VerifyEmail />} />
    <Route path="/workspace" element={<Guard><Workspace /></Guard>} />
    {features.flatMap((feature) => feature.routes).map((route) => <Route key={route.path} path={route.path} element={<Guard roles={route.roles}>{route.element}</Guard>} />)}
    <Route path="*" element={<main className="centered"><section><h1>Страница не найдена</h1><Link to="/">На главную</Link></section></main>} />
  </Routes><footer className="footer">ФСП Сигнал <span>От подтверждённых навыков — к новой команде</span></footer></AuthProvider>;
}

