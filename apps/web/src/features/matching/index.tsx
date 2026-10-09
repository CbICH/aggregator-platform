import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, ApiError } from '../../shared/api';
import type { components } from '../../shared/api.generated';
import type { FeatureModule } from '../../shared/module';
import { Field, Notice } from '../../shared/ui';
import { MatchingPage } from './MatchingPage';

// --- Shared types ----------------------------------------------------------

type Specialization = 'backend' | 'qa';
type Grade = 'junior' | 'middle' | 'senior';
type WorkFormat = 'remote' | 'hybrid' | 'office';

interface CatalogItem {
  id: string;
  label: string;
  active: boolean;
}

interface Catalogs {
  version: string;
  specializations: CatalogItem[];
  grades: CatalogItem[];
  skills: CatalogItem[];
  stack: CatalogItem[];
  categories: CatalogItem[];
}

function message(error: unknown) {
  return error instanceof ApiError
    ? error.message
    : 'Не удалось выполнить действие. Повторите попытку.';
}

const GRADE_LABEL: Record<Grade, string> = { junior: 'Junior', middle: 'Middle', senior: 'Senior' };
const SPECIALIZATION_LABEL: Record<Specialization, string> = { backend: 'Backend', qa: 'QA' };
const WORK_FORMAT_LABEL: Record<WorkFormat, string> = { remote: 'Удалённо', hybrid: 'Гибрид', office: 'Офис' };

// --- Company ---------------------------------------------------------------

type CompanyResponse = components['schemas']['CompanyResponse'];

interface CompanyForm {
  name: string;
  description: string;
  industry: string;
  city: string;
  contact_name: string;
  contact_role: string;
  contact_email: string;
}

const EMPTY_COMPANY_FORM: CompanyForm = {
  name: '', description: '', industry: '', city: '',
  contact_name: '', contact_role: '', contact_email: '',
};

function toCompanyForm(c: CompanyResponse): CompanyForm {
  return {
    name: c.name, description: c.description, industry: c.industry, city: c.city,
    contact_name: c.contact_name, contact_role: c.contact_role ?? '', contact_email: c.contact_email,
  };
}

function toCompanyPayload(form: CompanyForm) {
  const role = form.contact_role.trim();
  return {
    name: form.name.trim(),
    description: form.description.trim(),
    industry: form.industry.trim(),
    city: form.city.trim(),
    contact_name: form.contact_name.trim(),
    contact_role: role.length ? role : null,
    contact_email: form.contact_email.trim(),
  };
}

function CompanyPage() {
  const [company, setCompany] = useState<CompanyResponse | null>(null);
  const [form, setForm] = useState<CompanyForm>(EMPTY_COMPANY_FORM);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    void (async () => {
      try {
        const data = await api<CompanyResponse>('/company');
        setCompany(data);
        setForm(toCompanyForm(data));
      } catch (reason) {
        if (reason instanceof ApiError && reason.status === 404) setCompany(null);
        else setError(message(reason));
      } finally { setLoading(false); }
    })();
  }, []);

  const update = <K extends keyof CompanyForm>(key: K, value: CompanyForm[K]) =>
    setForm((old) => ({ ...old, [key]: value }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(''); setSuccess('');
    const payload = toCompanyPayload(form);
    if (!payload.name || !payload.description || !payload.industry || !payload.city || !payload.contact_name || !payload.contact_email) {
      setError('Заполните все обязательные поля.'); return;
    }
    setSaving(true);
    try {
      const data = await api<CompanyResponse>('/company', {
        method: company ? 'PATCH' : 'POST',
        body: JSON.stringify(payload),
      });
      setCompany(data); setForm(toCompanyForm(data));
      setSuccess(company ? 'Профиль компании обновлён.' : 'Компания создана. Теперь можно описывать потребности.');
    } catch (reason) { setError(message(reason)); } finally { setSaving(false); }
  };

  if (loading) return <main className="assessment-page"><p role="status">Загружаем профиль компании…</p></main>;

  return (
    <main className="assessment-page">
      <section className="assessment-panel">
        <span className="eyebrow">{company ? 'ПРОФИЛЬ КОМПАНИИ' : 'ПЕРВЫЙ ШАГ'}</span>
        <h1>{company ? company.name : 'Представьте вашу компанию'}</h1>
        <p className="lead">
          {company
            ? 'Эти данные кандидат видит рядом с приглашением. Измените поля и сохраните.'
            : 'Кандидат должен понять, кто его приглашает и чем вы занимаетесь. Поля можно изменить потом.'}
        </p>
        <form className="assessment-form" onSubmit={submit}>
          <Field id="name" label="Название компании" value={form.name} onChange={(e) => update('name', e.target.value)} maxLength={120} placeholder="OrderFlow" required />
          <label className="field" htmlFor="description"><span>Описание</span>
            <textarea id="description" value={form.description} onChange={(e) => update('description', e.target.value)} maxLength={2000} rows={4} placeholder="Чем занимается компания, какой фронт работ." required />
          </label>
          <Field id="industry" label="Отрасль" value={form.industry} onChange={(e) => update('industry', e.target.value)} maxLength={40} placeholder="fintech, it-services, analytics…" required />
          <Field id="city" label="Город" value={form.city} onChange={(e) => update('city', e.target.value)} maxLength={80} placeholder="Москва" required />
          <Field id="contact_name" label="Контактное лицо" value={form.contact_name} onChange={(e) => update('contact_name', e.target.value)} maxLength={120} placeholder="Анна Соколова" required />
          <Field id="contact_role" label="Роль контактного лица" value={form.contact_role} onChange={(e) => update('contact_role', e.target.value)} maxLength={80} placeholder="HR, тимлид (необязательно)" />
          <Field id="contact_email" label="Email для связи" type="email" value={form.contact_email} onChange={(e) => update('contact_email', e.target.value)} maxLength={254} placeholder="hr@orderflow.com" required />
          {error && <Notice error>{error}</Notice>}
          {success && <Notice>{success}</Notice>}
          <button className="button primary" disabled={saving}>{saving ? 'Сохраняем…' : company ? 'Сохранить изменения' : 'Создать компанию'}</button>
          {company && <p className="hint" style={{ marginTop: 24 }}>Готово? <Link to="/employer/needs">Опишите потребность →</Link></p>}
        </form>
      </section>
    </main>
  );
}

// --- Needs -----------------------------------------------------------------

interface RequiredSkill {
  id: string;
  weight: number;
}

interface NeedResponse {
  id: string;
  company_id: string;
  title: string;
  description: string;
  specialization: Specialization;
  grades: Grade[];
  declared_stack: string[];
  required_skills: RequiredSkill[];
  work_format: WorkFormat;
  salary_min: number | null;
  salary_max: number | null;
  created_at: string;
  updated_at: string;
}

interface NeedList {
  items: NeedResponse[];
}

interface NeedForm {
  title: string;
  description: string;
  specialization: Specialization;
  grades: Grade[];
  declared_stack: string;
  required_skills: Record<string, number>; // skill_id → weight
  work_format: WorkFormat;
  salary_min: string;
  salary_max: string;
}

const EMPTY_NEED_FORM: NeedForm = {
  title: '',
  description: '',
  specialization: 'backend',
  grades: ['middle'],
  declared_stack: '',
  required_skills: {},
  work_format: 'remote',
  salary_min: '',
  salary_max: '',
};

function needToPayload(form: NeedForm) {
  return {
    title: form.title.trim(),
    description: form.description.trim(),
    specialization: form.specialization,
    grades: form.grades,
    declared_stack: form.declared_stack.split(',').map((s) => s.trim()).filter(Boolean),
    required_skills: Object.entries(form.required_skills).map(([id, weight]) => ({ id, weight })),
    work_format: form.work_format,
    salary_min: form.salary_min.trim() ? Number(form.salary_min) : null,
    salary_max: form.salary_max.trim() ? Number(form.salary_max) : null,
  };
}

function NeedsListPage() {
  const [needs, setNeeds] = useState<NeedResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    void (async () => {
      try {
        const data = await api<NeedList>('/employer/needs');
        setNeeds(data.items);
      } catch (reason) {
        if (reason instanceof ApiError && reason.status === 409 && reason.code === 'COMPANY_REQUIRED') {
          setError('Сначала заполните профиль компании.');
        } else {
          setError(message(reason));
        }
      } finally { setLoading(false); }
    })();
  }, []);

  if (loading) return <main className="assessment-page"><p role="status">Загружаем потребности…</p></main>;

  return (
    <main className="assessment-page">
      <section className="assessment-heading">
        <div>
          <span className="eyebrow">ПОТРЕБНОСТЬ КОМАНДЫ</span>
          <h1>Ваши потребности</h1>
          <p>Опишите задачи, под которые ищете человека. На основе потребности строится персональная подборка.</p>
        </div>
        <Link to="/employer/needs/new" className="button primary">+ Новая потребность</Link>
      </section>

      {error && <Notice error>{error} {error.includes('компании') && <Link to="/employer/company">Перейти к компании →</Link>}</Notice>}

      {!error && needs.length === 0 && (
        <section className="assessment-panel">
          <p className="lead">Пока нет ни одной потребности. Создайте первую, чтобы увидеть подборку кандидатов именно под неё.</p>
          <Link to="/employer/needs/new" className="button primary" style={{ marginTop: 16, display: 'inline-block' }}>Создать первую потребность</Link>
        </section>
      )}

      <div className="assessment-items" style={{ gap: 14 }}>
        {needs.map((need) => (
          <article key={need.id} className="assessment-panel" style={{ padding: 24 }}>
            <header style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
              <div style={{ flex: '1 1 300px' }}>
                <h2 style={{ margin: 0 }}>{need.title}</h2>
                <p style={{ margin: '4px 0 0', color: '#776b82', fontSize: 13 }}>
                  {SPECIALIZATION_LABEL[need.specialization]} · {need.grades.map((g) => GRADE_LABEL[g]).join(', ')} · {WORK_FORMAT_LABEL[need.work_format]}
                </p>
              </div>
              <Link to={`/employer/matching/candidates?need=${need.id}`} className="button primary">Смотреть кандидатов</Link>
            </header>
            <p style={{ marginTop: 14, color: '#5c5366' }}>{need.description}</p>
            {need.required_skills.length > 0 && (
              <div style={{ marginTop: 14 }}>
                <div style={{ fontSize: 11, color: '#776b82', textTransform: 'uppercase', letterSpacing: '.1em', fontWeight: 700, marginBottom: 8 }}>Требуемые навыки</div>
                <div className="choice-row" style={{ gap: 8 }}>
                  {need.required_skills.map((rs) => (
                    <span key={rs.id} className="participant-code" style={{ padding: '6px 10px', borderRadius: 9, background: '#f4eff8', fontSize: 12 }}>
                      {rs.id} · вес {rs.weight}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {(need.salary_min || need.salary_max) && (
              <p className="hint" style={{ marginTop: 14 }}>
                Зарплата: {need.salary_min ? need.salary_min.toLocaleString('ru-RU') + ' ₽' : '…'} — {need.salary_max ? need.salary_max.toLocaleString('ru-RU') + ' ₽' : '…'}
              </p>
            )}
          </article>
        ))}
      </div>
    </main>
  );
}

function NeedCreatePage() {
  const navigate = useNavigate();
  const [form, setForm] = useState<NeedForm>(EMPTY_NEED_FORM);
  const [catalogs, setCatalogs] = useState<Catalogs | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    void (async () => {
      try {
        const data = await api<Catalogs>('/catalogs');
        setCatalogs(data);
      } catch { /* ok, скрыто */ }
    })();
  }, []);

  const update = <K extends keyof NeedForm>(key: K, value: NeedForm[K]) =>
    setForm((old) => ({ ...old, [key]: value }));

  const toggleGrade = (g: Grade) => {
    const next = form.grades.includes(g) ? form.grades.filter((x) => x !== g) : [...form.grades, g];
    update('grades', next);
  };

  const toggleSkill = (id: string) => {
    const next = { ...form.required_skills };
    if (id in next) delete next[id]; else next[id] = 1;
    update('required_skills', next);
  };

  const setSkillWeight = (id: string, weight: number) => {
    const next = { ...form.required_skills };
    next[id] = Math.max(1, Math.min(5, weight));
    update('required_skills', next);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    const payload = needToPayload(form);
    if (!payload.title || payload.title.length < 4) { setError('Укажите заголовок потребности (минимум 4 символа).'); return; }
    if (!payload.description || payload.description.length < 10) { setError('Опишите потребность чуть подробнее.'); return; }
    if (payload.grades.length === 0) { setError('Выберите хотя бы один допустимый грейд.'); return; }
    if (payload.required_skills.length === 0) { setError('Выберите хотя бы один требуемый навык.'); return; }
    if (payload.salary_min !== null && payload.salary_max !== null && payload.salary_min > payload.salary_max) {
      setError('Нижняя граница зарплаты не может превышать верхнюю.'); return;
    }

    setSaving(true);
    try {
      const created = await api<NeedResponse>('/employer/needs', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      navigate(`/employer/matching/candidates?need=${created.id}`);
    } catch (reason) {
      setError(message(reason));
    } finally { setSaving(false); }
  };

  // Фильтруем навыки по специализации, если можем
  const relevantSkills = catalogs?.skills.filter((s) => {
    if (form.specialization === 'backend') return s.id.startsWith('api.') || s.id.startsWith('data.');
    if (form.specialization === 'qa') return s.id.startsWith('qa.');
    return true;
  }) ?? [];

  return (
    <main className="assessment-page">
      <section className="assessment-panel">
        <span className="eyebrow">НОВАЯ ПОТРЕБНОСТЬ</span>
        <h1>Опишите, кого ищете</h1>
        <p className="lead">Опишите задачи и выберите проверяемые навыки — именно по ним кандидаты сортируются в подборке.</p>
        <form className="assessment-form" onSubmit={submit}>
          <Field id="title" label="Заголовок потребности" value={form.title} onChange={(e) => update('title', e.target.value)} maxLength={160} placeholder="Развитие API сервиса заказов" required />
          <label className="field" htmlFor="description"><span>Описание задач</span>
            <textarea id="description" value={form.description} onChange={(e) => update('description', e.target.value)} maxLength={2000} rows={5} placeholder="Что нужно будет делать в первые недели: багфиксы, фичи, миграции…" required />
          </label>

          <fieldset className="choice-field">
            <legend>Специализация</legend>
            <div className="choice-row">
              <label><input type="radio" checked={form.specialization === 'backend'} onChange={() => setForm({ ...form, specialization: 'backend', required_skills: {} })} /> Backend</label>
              <label><input type="radio" checked={form.specialization === 'qa'} onChange={() => setForm({ ...form, specialization: 'qa', required_skills: {} })} /> QA</label>
            </div>
          </fieldset>

          <fieldset className="choice-field">
            <legend>Допустимые грейды (можно несколько)</legend>
            <div className="choice-row">
              {(['junior', 'middle', 'senior'] as Grade[]).map((g) => (
                <label key={g}>
                  <input type="checkbox" checked={form.grades.includes(g)} onChange={() => toggleGrade(g)} /> {GRADE_LABEL[g]}
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className="choice-field">
            <legend>Проверяемые навыки <span style={{ color: '#776b82', fontWeight: 400 }}>(вес 1–5 показывает важность)</span></legend>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {relevantSkills.map((skill) => {
                const checked = skill.id in form.required_skills;
                return (
                  <label key={skill.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', border: '1px solid #dcd5e5', borderRadius: 9, background: checked ? '#f4eff8' : '#fff' }}>
                    <input type="checkbox" checked={checked} onChange={() => toggleSkill(skill.id)} />
                    <span style={{ flex: 1 }}><strong>{skill.id}</strong> — {skill.label}</span>
                    {checked && (
                      <input
                        type="number" min="1" max="5"
                        value={form.required_skills[skill.id]}
                        onChange={(e) => setSkillWeight(skill.id, Number(e.target.value))}
                        style={{ width: 60, padding: '6px 8px', border: '1px solid #dcd5e5', borderRadius: 7 }}
                      />
                    )}
                  </label>
                );
              })}
            </div>
          </fieldset>

          <Field id="declared_stack" label="Заявленный стек (через запятую)" value={form.declared_stack} onChange={(e) => update('declared_stack', e.target.value)} placeholder="python, postgresql, fastapi" />

          <fieldset className="choice-field">
            <legend>Формат работы</legend>
            <div className="choice-row">
              {(['remote', 'hybrid', 'office'] as WorkFormat[]).map((f) => (
                <label key={f}>
                  <input type="radio" checked={form.work_format === f} onChange={() => update('work_format', f)} /> {WORK_FORMAT_LABEL[f]}
                </label>
              ))}
            </div>
          </fieldset>

          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <Field id="salary_min" label="Зарплата от, ₽" type="number" value={form.salary_min} onChange={(e) => update('salary_min', e.target.value)} placeholder="180000" />
            <Field id="salary_max" label="Зарплата до, ₽" type="number" value={form.salary_max} onChange={(e) => update('salary_max', e.target.value)} placeholder="230000" />
          </div>

          {error && <Notice error>{error}</Notice>}
          <button className="button primary" disabled={saving}>{saving ? 'Сохраняем…' : 'Создать потребность и смотреть подборку'}</button>
        </form>
      </section>
    </main>
  );
}

// --- Module manifest -------------------------------------------------------

export const matching: FeatureModule = {
  routes: [
    { path: '/employer/company', element: <CompanyPage />, roles: ['employer'] },
    { path: '/employer/needs', element: <NeedsListPage />, roles: ['employer'] },
    { path: '/employer/needs/new', element: <NeedCreatePage />, roles: ['employer'] },
    { path: '/employer/matching/candidates', element: <MatchingPage />, roles: ['employer'] },
  ],
  navigation: [
    { to: '/employer/company', label: 'Моя компания', roles: ['employer'] },
    { to: '/employer/needs', label: 'Потребности', roles: ['employer'] },
    { to: '/employer/matching/candidates', label: 'Подбор кандидатов', roles: ['employer'] },
  ],
};
