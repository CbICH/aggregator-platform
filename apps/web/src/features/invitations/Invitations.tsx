import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../app/Auth';
import { api, ApiError } from '../../shared/api';
import type { components } from '../../shared/api.generated';
import { Field, Notice } from '../../shared/ui';
import '../profile/profile.css';
import './invitations.css';

type Invitation = components['schemas']['InvitationResponse'];
type InvitationList = components['schemas']['InvitationListResponse'];
type PublicProfile = components['schemas']['CandidatePublic'];
type PublicList = components['schemas']['PublicProfileList'];
type Company = components['schemas']['EmployerInvitationContext'];
type Contacts = components['schemas']['CandidateContacts'];
type Need = components['schemas']['NeedResponse'];
type Privacy = components['schemas']['PrivacyResponse'];
const statuses = { sent: 'Отправлено', viewed: 'Просмотрено', accepted: 'Принято', declined: 'Отклонено' };
const money = (amount: number) => new Intl.NumberFormat('ru-RU').format(amount);
export const salary = (value: Invitation['salary']) => `${money(value.min)}–${money(value.max)} ₽ в месяц до вычета налогов`;
function errorText(e: unknown) { return e instanceof Error ? e.message : 'Не удалось выполнить запрос'; }

function InvitationCard({ item, base }: { item: Invitation; base: string }) {
  return <article className="profile-section offer-card"><span className={`offer-status ${item.status}`}>{statuses[item.status]}</span><h2>{item.company_name}</h2>
    <p>{item.candidate_alias} · {item.category_code ?? 'Категория на момент отправки не указана'}</p><p className="offer-salary">{salary(item.salary)}</p>
    <p>{item.description.slice(0, 180)}{item.description.length > 180 ? '…' : ''}</p><Link className="button" to={`${base}/${item.invitation_id}`}>Открыть предложение</Link></article>;
}

export function InvitationListPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [items, setItems] = useState<Invitation[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const base = user?.role === 'candidate' ? '/candidate/invitations' : '/employer/invitations';
  const load = useCallback(async (after?: string) => {
    setBusy(true); setError('');
    try { const result = await api<InvitationList>(`/invitations?limit=20${after ? `&cursor=${after}` : ''}`); setItems((old) => after ? [...old, ...result.items] : result.items); setCursor(result.next_cursor ?? null); }
    catch (e) { if (e instanceof ApiError && e.status === 401) navigate('/login'); else setError(errorText(e)); }
    finally { setBusy(false); }
  }, [navigate]);
  useEffect(() => { void load(); }, [load]);
  return <main className="workspace profile-page"><Link className="profile-back" to="/workspace">← Личный кабинет</Link><span className="eyebrow">ПРЕДЛОЖЕНИЯ</span>
    <div className="profile-heading"><h1>{user?.role === 'candidate' ? 'Ваши приглашения' : 'Отправленные приглашения'}</h1><button className="button" disabled={busy} onClick={() => void load()}>Обновить список</button></div>
    {user?.role === 'employer' && <p><Link to="/employer/candidates">Открыть доступные профили</Link></p>}
    {error && <Notice error>{error}</Notice>}{busy && <p role="status">Загружаем предложения…</p>}
    {!busy && !error && items.length === 0 && <section className="profile-section"><h2>Приглашений пока нет</h2><p>{user?.role === 'candidate' ? 'Когда работодатель предложит работу, здесь появятся условия и зарплата.' : 'Откройте профиль кандидата и отправьте адресное предложение с зарплатой.'}</p></section>}
    <div className="offers-grid">{items.map((item) => <InvitationCard key={item.invitation_id} item={item} base={base} />)}</div>
    {cursor && <button className="button" disabled={busy} onClick={() => void load(cursor)}>Показать ещё</button>}
  </main>;
}

export function CandidateDirectory() {
  const navigate = useNavigate();
  const [items, setItems] = useState<PublicProfile[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const load = useCallback(async (after?: string) => {
    setBusy(true); setError('');
    try { const result = await api<PublicList>(`/employer/candidates?limit=20${after ? `&cursor=${after}` : ''}`); setItems((old) => after ? [...old, ...result.items] : result.items); setCursor(result.next_cursor ?? null); }
    catch (e) { if (e instanceof ApiError && e.status === 401) navigate('/login'); else setError(errorText(e)); }
    finally { setBusy(false); }
  }, [navigate]);
  useEffect(() => { void load(); }, [load]);
  return <main className="workspace profile-page"><Link className="profile-back" to="/workspace">← Личный кабинет</Link><span className="eyebrow">ПРОФИЛИ</span><div className="profile-heading"><h1>Доступные кандидаты</h1><button className="button" disabled={busy} onClick={() => void load()}>Обновить</button></div>
    <p><Link to="/employer/matching/candidates">Подобрать кандидатов по потребности</Link></p>
    <p className="lead">Опубликованные профили с подтверждённой категорией. Контакты открываются после принятия предложения.</p>
    {error && <Notice error>{error}</Notice>}{busy && <p role="status">Загружаем профили…</p>}{!busy && !error && items.length === 0 && <Notice>Пока нет опубликованных профилей с подтверждённой категорией.</Notice>}
    <div className="offers-grid">{items.map((item) => <article className="profile-section" key={item.candidate_id}><h2>{item.display_name}</h2><p>{item.verified_category?.category_code}</p>
      {item.roles && <p>Роли: {item.roles.join(', ')}</p>}{item.declared_stack && <p>Технологии: {item.declared_stack.join(', ')}</p>}{item.experience_months != null && <p>Стаж: {item.experience_months} мес.</p>}
      <Link className="button primary" to={`/employer/invitations/new?candidate_id=${item.candidate_id}`}>Предложить работу</Link></article>)}</div>
    {cursor && <button className="button" disabled={busy} onClick={() => void load(cursor)}>Показать ещё</button>}
  </main>;
}

export function InvitationForm() {
  const [params] = useSearchParams();
  const candidateId = params.get('candidate_id');
  const needId = params.get('need_id');
  const navigate = useNavigate();
  const [candidate, setCandidate] = useState<PublicProfile | null>(null);
  const [company, setCompany] = useState<Company | null>(null);
  const [need, setNeed] = useState<Need | null>(null);
  const [error, setError] = useState('');
  const [fields, setFields] = useState<string[]>([]);
  const [busy, setBusy] = useState(true);
  const [retry, setRetry] = useState(0);
  const [attempt, setAttempt] = useState<{ key: string; body: string } | null>(null);
  useEffect(() => {
    let active = true;
    if (!candidateId) { setError('Откройте форму из карточки кандидата.'); setBusy(false); return; }
    setBusy(true); setError('');
    void Promise.all([api<PublicProfile>(`/employer/candidates/${encodeURIComponent(candidateId)}`), api<Company>('/employer/invitation-context'), needId ? api<Need>(`/employer/needs/${encodeURIComponent(needId)}`) : Promise.resolve(null)]).then(([profile, info, savedNeed]) => { if (active) { setCandidate(profile); setCompany(info); setNeed(savedNeed); } }).catch((e) => { if (active) { if (e instanceof ApiError && e.status === 401) navigate('/login'); else setError(errorText(e)); } }).finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [candidateId, needId, retry, navigate]);
  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const body = JSON.stringify({ candidate_id: candidateId, need_id: needId, description: values.get('description'), salary: { min: Number(values.get('salary_min')), max: Number(values.get('salary_max')) }, company_contact: values.get('company_contact'), evidence_refs: values.getAll('evidence') });
    const key = attempt?.body === body ? attempt.key : crypto.randomUUID();
    setAttempt({ key, body }); setBusy(true); setError(''); setFields([]);
    try { const result = await api<Invitation>('/invitations', { method: 'POST', headers: { 'Idempotency-Key': key }, body }); navigate(`/employer/invitations/${result.invitation_id}`); }
    catch (e) { if (e instanceof ApiError && e.status === 401) navigate('/login'); else { setError(errorText(e)); if (e instanceof ApiError) setFields(Object.values(e.fields ?? {})); } }
    finally { setBusy(false); }
  }
  return <main className="workspace profile-page"><Link className="profile-back" to="/employer/candidates">← К кандидатам</Link><span className="eyebrow">НОВОЕ ПРЕДЛОЖЕНИЕ</span><h1>Предложите конкретную работу</h1>
    {error && <Notice error>{error}{fields.map((field, index) => <p key={index}>{field}</p>)}{!candidate && <button className="inline-button" onClick={() => setRetry(retry + 1)}>Повторить загрузку</button>}</Notice>}
    {busy && !candidate && <p role="status">Загружаем кандидата…</p>}
    {candidate && company && <div className="profile-layout"><form className="profile-form" onSubmit={send}><fieldset className="profile-section" disabled={busy}><legend>Условия предложения</legend><p>{company.company_name} → {candidate.display_name}</p>
      <label className="field" htmlFor="description"><span>Описание предложения</span><textarea id="description" name="description" rows={6} minLength={20} maxLength={6000} required defaultValue={need ? `${need.title}\n${need.description}\nФормат работы: ${need.work_format}` : ''} placeholder="Задачи, команда, формат работы и условия" /></label>
      <div className="profile-contact-grid"><Field id="salary-min" label="Зарплата от, ₽" defaultValue={need?.salary_min ?? ''} name="salary_min" type="number" min={1} step={1} required /><Field id="salary-max" label="Зарплата до, ₽" defaultValue={need?.salary_max ?? ''} name="salary_max" type="number" min={1} step={1} required /></div>
      <p className="hint">Рубли в месяц до вычета налогов. Оба значения обязательны.</p>
      <Field id="company-contact" label="Связь с работодателем" name="company_contact" defaultValue={company.company_contact} minLength={3} maxLength={300} required />
      <h2>Основания выбора</h2><div className="privacy-fields">{candidate.verified_category?.skills.map((skill) => <label key={skill.id}><input type="checkbox" name="evidence" defaultChecked={need?.required_skills.some((required) => required.id === skill.id) ?? false} value={skill.id} />{skill.id} · {skill.score}/100</label>)}</div>
      <button className="button primary" disabled={busy}>{busy ? 'Отправляем…' : 'Отправить приглашение'}</button></fieldset></form>
      <aside className="profile-summary"><section className="profile-section"><h2>{candidate.display_name}</h2><p>{candidate.verified_category?.category_code}</p><p>{candidate.declared_stack?.join(', ') ?? 'Стек скрыт'}</p><p className="muted">Предложение можно отправить без опубликованной вакансии. Контакты кандидата пока закрыты.</p></section></aside></div>}
  </main>;
}

export function InvitationPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [item, setItem] = useState<Invitation | null>(null);
  const [privacy, setPrivacy] = useState<Privacy | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(true);
  const [consent, setConsent] = useState(false);
  const candidate = user?.role === 'candidate';
  const base = candidate ? '/candidate/invitations' : '/employer/invitations';
  const load = useCallback(async () => {
    setBusy(true); setError('');
    try {
      const value = candidate ? await api<Invitation>(`/invitations/${id}/view`, { method: 'POST' }) : await api<Invitation>(`/invitations/${id}`);
      setItem(value); if (candidate) setPrivacy(await api<Privacy>('/candidate/privacy'));
    } catch (e) { setItem(null); if (e instanceof ApiError && e.status === 401) navigate('/login'); else setError(errorText(e)); }
    finally { setBusy(false); }
  }, [candidate, id, navigate]);
  useEffect(() => { void load(); }, [load]);
  async function decide(action: 'accept' | 'decline') {
    if (!item) return;
    setBusy(true); setError('');
    try { setItem(await api<Invitation>(`/invitations/${id}/decision`, { method: 'POST', body: JSON.stringify({ action, expected_version: item.version, ...(action === 'accept' ? { contact_consent_accepted: consent, contact_consent_version: privacy?.contact_policy.version } : {}) }) })); }
    catch (e) { if (e instanceof ApiError && e.status === 401) navigate('/login'); else setError(errorText(e)); }
    finally { setBusy(false); }
  }
  return <main className="workspace profile-page"><Link className="profile-back" to={base}>← Все приглашения</Link><span className="eyebrow">ПРЕДЛОЖЕНИЕ</span><div className="profile-heading"><h1>{item?.company_name ?? 'Приглашение'}</h1><button className="button" disabled={busy} onClick={() => void load()}>Обновить предложение</button></div>
    {error && <Notice error>{error}</Notice>}{busy && <p role="status">Обновляем предложение…</p>}
    {item && <div className="profile-layout"><section className="profile-section"><span className={`offer-status ${item.status}`}>{statuses[item.status]}</span><p className="offer-salary">{salary(item.salary)}</p><p className="offer-description">{item.description}</p><h2>Связь с работодателем</h2><p>{item.company_contact}</p>
      <h2>Основания выбора на момент отправки</h2><p>{item.category_code}</p>{item.evidence.length > 0 ? <ul>{item.evidence.map((evidence) => <li key={evidence.skill_id}>{evidence.skill_id}: {evidence.score}/100 · тест {evidence.assessment_version}</li>)}</ul> : <p>Работодатель не выделил отдельные навыки.</p>}
      {candidate && ['sent', 'viewed'].includes(item.status) && <div className="offer-decision"><label className="consent"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} disabled={busy} /><span>Разрешаю передать мои контакты компании «{item.company_name}» при принятии предложения</span></label>
        {privacy && <details className="policy"><summary>Условия передачи контактов</summary><p>{privacy.contact_policy.text}</p></details>}
        <div className="offer-actions"><button className="button primary" disabled={busy || !consent || !privacy} onClick={() => void decide('accept')}>Принять предложение</button><button className="button" disabled={busy} onClick={() => void decide('decline')}>Отклонить</button></div></div>}
      {item.status === 'accepted' && <Notice>{item.contact_access_active ? 'Предложение принято. Компания может получить контакты.' : 'Предложение принято. Доступ к контактам отозван.'}</Notice>}
      {item.status === 'declined' && <Notice>Предложение отклонено. Оно не даёт компании доступ к контактам.</Notice>}
      {!candidate && item.contact_access_active && <Link className="button primary" to={`/employer/candidates/${item.candidate_id}/contacts`}>Открыть контакты</Link>}
    </section><aside className="profile-summary"><section className="profile-section"><h2>{item.candidate_alias}</h2><p>Отправлено {new Date(item.created_at).toLocaleString('ru-RU')}</p>{item.viewed_at && <p>Просмотрено {new Date(item.viewed_at).toLocaleString('ru-RU')}</p>}{item.decided_at && <p>Решение {new Date(item.decided_at).toLocaleString('ru-RU')}</p>}<p className="muted">Условия зафиксированы при отправке и не меняются после обновления профиля или компании.</p></section></aside></div>}
  </main>;
}

export function ContactPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [contacts, setContacts] = useState<Contacts | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(true);
  const load = useCallback(async () => {
    setBusy(true); setError(''); setContacts(null);
    try { setContacts(await api<Contacts>(`/employer/candidates/${id}/contacts`)); }
    catch (e) { if (e instanceof ApiError && e.status === 401) navigate('/login'); else setError(errorText(e)); }
    finally { setBusy(false); }
  }, [id, navigate]);
  useEffect(() => { void load(); }, [load]);
  return <main className="workspace profile-page"><Link className="profile-back" to="/employer/invitations">← Приглашения</Link><h1>Контакты кандидата</h1><p className="lead">Доступ действует для вашей компании после явного разрешения кандидата.</p>
    <button className="button" disabled={busy} onClick={() => void load()}>Обновить доступ</button>{busy && <p role="status">Проверяем доступ…</p>}{error && <Notice error>{error}</Notice>}
    {contacts && <section className="profile-section"><p>Email: {contacts.email ?? 'не указан'}</p><p>Телефон: {contacts.phone ?? 'не указан'}</p><p>Способ связи: {contacts.contact_method || 'не указан'}</p></section>}
  </main>;
}
