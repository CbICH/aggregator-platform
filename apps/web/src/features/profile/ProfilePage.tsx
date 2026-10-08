import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../app/Auth';
import { api, ApiError } from '../../shared/api';
import type { components } from '../../shared/api.generated';
import { Field, Notice } from '../../shared/ui';
import './profile.css';

type Profile = components['schemas']['CandidateSelf'];
type Policy = components['schemas']['ProfileProcessingPolicy'];
type ProfileRole = Profile['roles'][number];

const roleOptions: { id: ProfileRole; label: string }[] = [
  { id: 'backend', label: 'Backend' }, { id: 'frontend', label: 'Frontend' },
  { id: 'fullstack', label: 'Fullstack' }, { id: 'qa', label: 'QA' },
  { id: 'devops', label: 'DevOps' }, { id: 'data', label: 'Данные и аналитика' },
  { id: 'mobile', label: 'Мобильная разработка' }, { id: 'other', label: 'Другая роль' },
];

function tags(value: FormDataEntryValue | null) {
  return String(value ?? '').split(',').map((item) => item.trim()).filter(Boolean);
}

export function ProfilePage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [savedMessage, setSavedMessage] = useState('');
  const [fields, setFields] = useState<Record<string, string>>({});
  const [downloading, setDownloading] = useState(false);

  async function downloadPdf() {
    setDownloading(true); setError('');
    try {
      const response = await fetch('/api/v1/candidate/profile.pdf', { credentials: 'same-origin' });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        if (response.status === 401) navigate('/login');
        throw new Error(body?.error?.message ?? 'Не удалось скачать PDF');
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a'); link.href = url; link.download = 'fsp-signal-profile.pdf'; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(e instanceof Error ? e.message : 'Не удалось скачать PDF'); }
    finally { setDownloading(false); }
  }

  const load = useCallback(async () => {
    setLoading(true); setError(''); setSavedMessage(''); setFields({});
    try {
      const [draft, consent] = await Promise.all([
        api<Profile>('/candidate/profile'), api<Policy>('/candidate/profile-policy'),
      ]);
      setProfile(draft); setPolicy(consent);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) navigate('/login');
      else setError(e instanceof Error ? e.message : 'Не удалось загрузить профиль');
    } finally { setLoading(false); }
  }, [navigate]);
  useEffect(() => { void load(); }, [load]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!profile || !policy) return;
    const values = new FormData(event.currentTarget);
    setBusy(true); setError(''); setSavedMessage(''); setFields({});
    try {
      const result = await api<Profile>('/candidate/profile', {
        method: 'PATCH',
        body: JSON.stringify({
          expected_version: profile.version,
          full_name: String(values.get('full_name') ?? ''),
          roles: values.getAll('roles'), experience_months: Number(values.get('experience_months')),
          declared_stack: tags(values.get('declared_stack')), soft_skills: tags(values.get('soft_skills')),
          resume_text: String(values.get('resume_text') ?? ''),
          contacts: {
            email: String(values.get('contact_email') ?? '').trim() || null,
            phone: String(values.get('phone') ?? '').trim() || null,
            contact_method: String(values.get('contact_method') ?? ''),
          },
          ...(!profile.processing_consent_active ? {
            processing_consent_accepted: values.get('processing_consent') === 'on',
            processing_consent_version: policy.version,
          } : {}),
        }),
      });
      setProfile(result);
      setSavedMessage(result.privacy.discoverable ? 'Профиль сохранён. Публичные поля доступны работодателям.' : 'Профиль сохранён. Данные доступны только вам.');
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) navigate('/login');
      else {
        setError(e instanceof Error ? e.message : 'Не удалось сохранить профиль');
        if (e instanceof ApiError) setFields(e.fields ?? {});
      }
    } finally { setBusy(false); }
  }

  if (loading) return <main className="workspace"><p role="status">Загружаем профиль…</p></main>;
  if (!profile || !policy) return <main className="workspace"><Notice error>{error || 'Профиль недоступен'}</Notice>
    <button className="button" onClick={() => void load()}>Повторить загрузку</button></main>;

  return <main className="workspace profile-page">
    <Link className="profile-back" to="/workspace">← Личный кабинет</Link>
    <div className="profile-heading"><div><span className="eyebrow">МОЙ ПРОФИЛЬ</span><h1>Расскажите о себе</h1>
      <p className="lead">Опыт, технологии и задачи, с которыми вам интересно работать.</p></div>
      <span className="profile-private">{profile.privacy.discoverable ? 'Профиль опубликован' : 'Приватный профиль'}</span></div>
    {!user?.email_verified && <Notice>Профиль можно заполнить сейчас. <Link to="/check-email">Подтвердите email</Link>, чтобы продолжить основной путь.</Notice>}
    <div className="profile-layout">
      <form className="profile-form" onSubmit={save} key={profile.version}>
        <fieldset disabled={busy} className="profile-section"><legend>Основная информация</legend>
          <p className="muted">Можно сохранить черновик и вернуться к заполнению позже.</p>
          <Field id="full-name" label="ФИО" name="full_name" defaultValue={profile.full_name} autoComplete="name" maxLength={200} placeholder="Иван Петров" />
          <fieldset className="profile-roles"><legend>Роли</legend><div className="profile-role-grid">
            {roleOptions.map((role) => <label key={role.id}><input type="checkbox" name="roles" value={role.id} defaultChecked={profile.roles.includes(role.id)} />{role.label}</label>)}
          </div></fieldset>
          <Field id="experience" label="Стаж в месяцах" name="experience_months" type="number" min={0} max={1200} step={1} required defaultValue={profile.experience_months} />
          <p className="hint">Если опыта пока нет, укажите 0.</p>
          <Field id="stack" label="Технологии" name="declared_stack" defaultValue={profile.declared_stack.join(', ')} maxLength={1500} placeholder="Python, PostgreSQL, Git" />
          <p className="hint">Перечислите через запятую. Это ваш заявленный стек; навыки подтверждаются отдельно тестированием.</p>
          <Field id="soft-skills" label="Софт-скиллы" name="soft_skills" defaultValue={profile.soft_skills.join(', ')} maxLength={1600} placeholder="Работа в команде, коммуникация" />
          <label className="field" htmlFor="resume"><span>О себе и опыте</span>
            <textarea id="resume" name="resume_text" rows={6} maxLength={12000} defaultValue={profile.resume_text} placeholder="Какие задачи решали, чем гордитесь и над чем хотите работать?" /></label>
        </fieldset>
        <fieldset disabled={busy} className="profile-section"><legend>Контакты</legend>
          <p className="muted">Контакты сохраняются отдельно от информации для работодателей.</p>
          <div className="profile-contact-grid">
            <Field id="contact-email" label="Контактный email" name="contact_email" type="email" maxLength={254} autoComplete="email" defaultValue={profile.contacts.email ?? ''} />
            <Field id="phone" label="Телефон" name="phone" type="tel" maxLength={32} autoComplete="tel" defaultValue={profile.contacts.phone ?? ''} placeholder="+7 900 000-00-00" />
          </div>
          <p className="hint">Контактный email не меняет адрес входа в аккаунт.</p>
          <Field id="contact-method" label="Предпочтительный способ связи" name="contact_method" maxLength={200} defaultValue={profile.contacts.contact_method} placeholder="Написать на email" />
        </fieldset>
        <section className="profile-section profile-save">
          {!profile.processing_consent_active && <>
            <label className="consent"><input type="checkbox" name="processing_consent" required disabled={busy} />
              <span>Согласен на обработку данных моего профиля и резюме</span></label>
            <details className="policy"><summary>Условия обработки профиля</summary><p>{policy.text}</p></details>
          </>}
          {error && <Notice error>{error}{Object.keys(fields).length > 0 && <ul>{Object.entries(fields).map(([name, value]) => <li key={name}>{value}</li>)}</ul>}
            <button type="button" className="inline-button" disabled={busy} onClick={() => void load()}>Загрузить сохранённую версию</button></Notice>}
          {savedMessage && <Notice>{savedMessage}</Notice>}
          <button className="button primary" disabled={busy}>{busy ? 'Сохраняем…' : 'Сохранить профиль'}</button>
          <p className="hint">Сохранение профиля не публикует его и не открывает контакты работодателям.</p>
        </section>
      </form>
      <aside className="profile-summary">
        <section className="profile-section"><span className="eyebrow">ВАШ ПРОГРЕСС</span><h2>{profile.saved ? 'Черновик сохранён' : 'Начните с профиля'}</h2>
          <p>{profile.profile_complete ? 'Основные сведения заполнены.' : 'Для полного профиля добавьте ФИО, роль, технологии и хотя бы один контакт.'}</p>
          {profile.updated_at && <p className="muted">Сохранено {new Date(profile.updated_at).toLocaleString('ru-RU')}</p>}
        </section>
        <section className="profile-section"><h2>Подтверждение навыков</h2>
          <p>{profile.verified_category ? profile.verified_category.category_code : 'Категория пока не подтверждена. Она появится после тестирования.'}</p>
          <p className="muted">Заявленный опыт и технологии не назначают грейд автоматически.</p></section>
        <section className="profile-section"><h2>Доступ к профилю</h2><p>{profile.privacy.discoverable ? 'Выбранные поля доступны работодателям.' : profile.privacy.publication_enabled ? 'Согласие принято. Для показа работодателям нужно подтвердить категорию и заполнить профиль.' : 'Сейчас данные доступны только вам.'}</p>
          <Link className="button" to="/candidate/privacy">Настройки приватности</Link></section>
        <section className="profile-section"><h2>Профиль ФСП</h2><p>{{ not_linked: 'ФСП ID не связан', linked_empty: 'Профиль связан, истории достижений нет', linked_with_data: 'Достижения ФСП получены', unavailable: 'Источник ФСП пока недоступен' }[(profile.fsp ?? { status: 'unavailable' }).status]}</p>
          {(profile.fsp ?? { status: 'unavailable' }).status === 'linked_with_data' && <p>Сигнал: {(profile.fsp ?? { signal: 0 }).signal}/100 · {(profile.fsp ?? { source: 'demo' }).source === 'demo' ? 'демонстрационные данные' : 'реестр'}</p>}
          <p className="muted">История ФСП не обязательна для основного пути.</p><Link to="/candidate/fsp">Управлять связью с ФСП ID</Link></section>
        <section className="profile-section"><h2>Ваш PDF-профиль</h2><p className="muted">Личный документ содержит контакты. Сохраните изменения перед скачиванием.</p>
          <button className="button" disabled={downloading || !profile.saved || !user?.email_verified} onClick={() => void downloadPdf()}>{downloading ? 'Готовим PDF…' : 'Скачать PDF'}</button></section>
      </aside>
    </div>
  </main>;
}
