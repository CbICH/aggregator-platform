import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { api, ApiError } from '../../shared/api';
import type { FeatureModule } from '../../shared/module';
import { Field, Notice } from '../../shared/ui';

// --- Company types ---------------------------------------------------------

interface CompanyResponse {
  id: string;
  name: string;
  description: string;
  industry: string;
  city: string;
  contact_name: string;
  contact_role: string | null;
  contact_email: string;
  created_at: string;
  updated_at: string;
}

interface CompanyForm {
  name: string;
  description: string;
  industry: string;
  city: string;
  contact_name: string;
  contact_role: string;
  contact_email: string;
}

const EMPTY_FORM: CompanyForm = {
  name: '',
  description: '',
  industry: '',
  city: '',
  contact_name: '',
  contact_role: '',
  contact_email: '',
};

function toForm(company: CompanyResponse): CompanyForm {
  return {
    name: company.name,
    description: company.description,
    industry: company.industry,
    city: company.city,
    contact_name: company.contact_name,
    contact_role: company.contact_role ?? '',
    contact_email: company.contact_email,
  };
}

function toPayload(form: CompanyForm) {
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

function message(error: unknown) {
  return error instanceof ApiError
    ? error.message
    : 'Не удалось выполнить действие. Повторите попытку.';
}

// --- Candidate types -------------------------------------------------------

type Specialization = 'backend' | 'qa';
type Grade = 'junior' | 'middle' | 'senior';
type FspStatus = 'not_linked' | 'linked_empty' | 'linked_with_data' | 'unavailable';

interface Reason {
  code: string;
  label?: string | null;
  skill_id?: string | null;
  score?: number | null;
  date?: string | null;
}

interface Skill {
  id: string;
  score: number;
}

interface CandidateCard {
  candidate_id: string;
  display_name: string;
  specialization: Specialization;
  verified_grade: Grade;
  category_code: string;
  experience_years: number;
  work_format: string;
  declared_stack: string[];
  score: number;
  components: { test: number; fsp: number };
  skills: Skill[];
  fsp_status: FspStatus;
  reasons: Reason[];
}

interface CandidateList {
  items: CandidateCard[];
  total: number;
}

interface CategoryCard {
  code: string;
  specialization: Specialization;
  grade: Grade;
  active: boolean;
  candidate_count: number;
}

interface CategoryList {
  items: CategoryCard[];
}

const GRADE_LABEL: Record<Grade, string> = {
  junior: 'Junior',
  middle: 'Middle',
  senior: 'Senior',
};

const SPECIALIZATION_LABEL: Record<Specialization, string> = {
  backend: 'Backend',
  qa: 'QA',
};

const WORK_FORMAT_LABEL: Record<string, string> = {
  remote: 'Удалённо',
  hybrid: 'Гибрид',
  office: 'Офис',
};

// --- Company page ----------------------------------------------------------

function CompanyPage() {
  const [company, setCompany] = useState<CompanyResponse | null>(null);
  const [form, setForm] = useState<CompanyForm>(EMPTY_FORM);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    void (async () => {
      try {
        const data = await api<CompanyResponse>('/company');
        setCompany(data);
        setForm(toForm(data));
      } catch (reason) {
        if (reason instanceof ApiError && reason.status === 404) {
          setCompany(null);
        } else {
          setError(message(reason));
        }
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const update = <K extends keyof CompanyForm>(key: K, value: CompanyForm[K]) =>
    setForm((old) => ({ ...old, [key]: value }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    setSuccess('');
    const payload = toPayload(form);
    if (
      !payload.name
      || !payload.description
      || !payload.industry
      || !payload.city
      || !payload.contact_name
      || !payload.contact_email
    ) {
      setError('Заполните все обязательные поля.');
      return;
    }
    setSaving(true);
    try {
      const data = await api<CompanyResponse>('/company', {
        method: company ? 'PATCH' : 'POST',
        body: JSON.stringify(payload),
      });
      setCompany(data);
      setForm(toForm(data));
      setSuccess(
        company
          ? 'Профиль компании обновлён.'
          : 'Компания создана. Теперь можно смотреть кандидатов.',
      );
    } catch (reason) {
      setError(message(reason));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <main className="assessment-page"><p role="status">Загружаем профиль компании…</p></main>;
  }

  return (
    <main className="assessment-page">
      <section className="assessment-panel">
        <span className="eyebrow">{company ? 'ПРОФИЛЬ КОМПАНИИ' : 'ПЕРВЫЙ ШАГ'}</span>
        <h1>{company ? company.name : 'Представьте вашу компанию'}</h1>
        <p className="lead">
          {company
            ? 'Эти данные кандидат видит рядом с приглашением. Измените поля и сохраните.'
            : 'Кандидат должен понять, кто его приглашает и чем вы занимаетесь. Это разовое заполнение; поля можно изменить потом.'}
        </p>
        <form className="assessment-form" onSubmit={submit}>
          <Field id="name" label="Название компании" value={form.name} onChange={(e) => update('name', e.target.value)} maxLength={120} placeholder="OrderFlow" required />
          <label className="field">
            <span>Описание</span>
            <textarea id="description" value={form.description} onChange={(e) => update('description', e.target.value)} maxLength={2000} rows={4} placeholder="Чем компания занимается, какой фронт работ, сколько человек в команде." required />
          </label>
          <Field id="industry" label="Отрасль" value={form.industry} onChange={(e) => update('industry', e.target.value)} maxLength={40} placeholder="fintech, it-services, analytics…" required />
          <Field id="city" label="Город" value={form.city} onChange={(e) => update('city', e.target.value)} maxLength={80} placeholder="Москва" required />
          <Field id="contact_name" label="Контактное лицо" value={form.contact_name} onChange={(e) => update('contact_name', e.target.value)} maxLength={120} placeholder="Анна Соколова" required />
          <Field id="contact_role" label="Роль контактного лица" value={form.contact_role} onChange={(e) => update('contact_role', e.target.value)} maxLength={80} placeholder="HR, тимлид (необязательно)" />
          <Field id="contact_email" label="Email для связи" type="email" value={form.contact_email} onChange={(e) => update('contact_email', e.target.value)} maxLength={254} placeholder="hr@orderflow.com" required />
          {error && <Notice error>{error}</Notice>}
          {success && <Notice>{success}</Notice>}
          <button className="button primary" disabled={saving}>
            {saving ? 'Сохраняем…' : company ? 'Сохранить изменения' : 'Создать компанию'}
          </button>
          {company && (
            <p className="hint" style={{ marginTop: 24 }}>
              Готово? <Link to="/employer/candidates">Перейти к подборке кандидатов →</Link>
            </p>
          )}
        </form>
      </section>
    </main>
  );
}

// --- Candidates page -------------------------------------------------------

function fspBadge(status: FspStatus) {
  switch (status) {
    case 'linked_with_data': return { text: 'ФСП подтверждён', tone: 'fsp' };
    case 'linked_empty': return { text: 'ФСП: нет достижений', tone: 'muted' };
    case 'unavailable': return { text: 'ФСП временно недоступен', tone: 'warn' };
    default: return null;
  }
}

function CandidatesPage() {
  const [cards, setCards] = useState<CandidateCard[]>([]);
  const [total, setTotal] = useState(0);
  const [categories, setCategories] = useState<CategoryCard[]>([]);
  const [specialization, setSpecialization] = useState<Specialization | ''>('');
  const [grade, setGrade] = useState<Grade | ''>('');
  const [withFsp, setWithFsp] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (specialization) params.set('specialization', specialization);
      if (grade) params.set('grade', grade);
      if (withFsp) params.set('with_fsp_only', 'true');
      const query = params.toString();
      const data = await api<CandidateList>(`/employer/candidates${query ? '?' + query : ''}`);
      setCards(data.items);
      setTotal(data.total);
    } catch (reason) {
      setError(message(reason));
    } finally {
      setLoading(false);
    }
  }, [specialization, grade, withFsp]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void (async () => {
      try {
        const data = await api<CategoryList>('/employer/categories');
        setCategories(data.items);
      } catch {
        // не критично; подборка всё равно показывается
      }
    })();
  }, []);

  const activeCategories = categories.filter((c) => c.active && c.candidate_count > 0);

  return (
    <main className="assessment-page">
      <section className="assessment-heading">
        <div>
          <span className="eyebrow">ПОДБОР СПЕЦИАЛИСТОВ</span>
          <h1>Подборка кандидатов</h1>
          <p>Отсортировано по score. Формула учитывает балл теста и сигнал ФСП. Релевантность потребности прикрутим на следующем шаге.</p>
        </div>
        <strong className="participant-code">{total} в банке</strong>
      </section>

      <section className="assessment-panel" style={{ padding: 20, marginBottom: 20 }}>
        <div className="choice-row" style={{ gap: 10 }}>
          <button type="button" className={`button ${!specialization ? 'primary' : 'ghost'}`} onClick={() => setSpecialization('')}>Любая</button>
          <button type="button" className={`button ${specialization === 'backend' ? 'primary' : 'ghost'}`} onClick={() => setSpecialization('backend')}>Backend</button>
          <button type="button" className={`button ${specialization === 'qa' ? 'primary' : 'ghost'}`} onClick={() => setSpecialization('qa')}>QA</button>
          <span style={{ margin: '0 6px', color: '#776b82' }}>·</span>
          <button type="button" className={`button ${!grade ? 'primary' : 'ghost'}`} onClick={() => setGrade('')}>Все грейды</button>
          <button type="button" className={`button ${grade === 'junior' ? 'primary' : 'ghost'}`} onClick={() => setGrade('junior')}>Junior</button>
          <button type="button" className={`button ${grade === 'middle' ? 'primary' : 'ghost'}`} onClick={() => setGrade('middle')}>Middle</button>
          <button type="button" className={`button ${grade === 'senior' ? 'primary' : 'ghost'}`} onClick={() => setGrade('senior')}>Senior</button>
          <span style={{ margin: '0 6px', color: '#776b82' }}>·</span>
          <label className="choice-row" style={{ padding: '10px 12px', border: '1px solid #dcd5e5', borderRadius: 9 }}>
            <input type="checkbox" checked={withFsp} onChange={(e) => setWithFsp(e.target.checked)} /> Только с ФСП
          </label>
        </div>
      </section>

      {error && <Notice error>{error}</Notice>}
      {loading && <p role="status">Собираем подборку…</p>}

      {!loading && cards.length === 0 && !error && (
        <Notice>По выбранным фильтрам кандидатов нет. Снимите часть фильтров.</Notice>
      )}

      <div className="assessment-items" style={{ gap: 14 }}>
        {cards.map((card) => {
          const badge = fspBadge(card.fsp_status);
          return (
            <article key={card.candidate_id} className="assessment-panel" style={{ padding: 24 }}>
              <header style={{ display: 'flex', gap: 20, flexWrap: 'wrap', alignItems: 'flex-start' }}>
                <div style={{ flex: '1 1 220px' }}>
                  <h2 style={{ margin: 0 }}>{card.display_name}</h2>
                  <p style={{ margin: '4px 0 0', color: '#776b82', fontSize: 13 }}>
                    {SPECIALIZATION_LABEL[card.specialization]} · {GRADE_LABEL[card.verified_grade]} · {WORK_FORMAT_LABEL[card.work_format] ?? card.work_format} · {card.experience_years} лет опыта
                  </p>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <strong className="participant-code" style={{ fontSize: 36, letterSpacing: '-.03em' }}>{card.score.toFixed(1)}</strong>
                  <div style={{ fontSize: 11, color: '#776b82', textTransform: 'uppercase', letterSpacing: '.1em' }}>score</div>
                </div>
              </header>

              <div className="evidence-grid" style={{ marginTop: 18 }}>
                <article>
                  <span>Тест</span>
                  <strong>{card.components.test.toFixed(0)}</strong>
                  <p>Балл последнего подтверждённого теста.</p>
                </article>
                <article>
                  <span>ФСП</span>
                  <strong>{card.components.fsp.toFixed(0)}</strong>
                  <p>{badge ? badge.text : 'Без связи с ФСП.'}</p>
                </article>
                <article>
                  <span>Стек</span>
                  <strong style={{ fontSize: 14, lineHeight: 1.4 }}>{card.declared_stack.slice(0, 3).join(', ') || '—'}</strong>
                  <p>Заявлен кандидатом, не подтверждён тестом.</p>
                </article>
              </div>

              {card.skills.length > 0 && (
                <div style={{ marginTop: 18 }}>
                  <div style={{ fontSize: 11, color: '#776b82', textTransform: 'uppercase', letterSpacing: '.1em', fontWeight: 700, marginBottom: 8 }}>Подтверждённые навыки</div>
                  <div className="choice-row" style={{ gap: 8 }}>
                    {card.skills.map((skill) => (
                      <span key={skill.id} className="participant-code" style={{ padding: '6px 10px', borderRadius: 9, background: '#f4eff8', fontSize: 12 }}>
                        {skill.id} · {skill.score.toFixed(0)}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {card.reasons.length > 0 && (
                <div style={{ marginTop: 18, borderTop: '1px dashed #e5dcee', paddingTop: 16 }}>
                  <div style={{ fontSize: 11, color: '#542971', textTransform: 'uppercase', letterSpacing: '.1em', fontWeight: 700, marginBottom: 8 }}>Почему подходит</div>
                  <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {card.reasons.map((r, i) => (
                      <li key={i} style={{ fontSize: 13, color: '#542971' }}>
                        · {r.label ?? (r.skill_id ? `${r.skill_id} — ${r.score?.toFixed(0)} баллов` : r.code)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </article>
          );
        })}
      </div>

      {activeCategories.length > 0 && (
        <aside className="hint" style={{ marginTop: 32 }}>
          Доступные категории: {activeCategories.map((c) => `${c.code} (${c.candidate_count})`).join(', ')}.
        </aside>
      )}
    </main>
  );
}

// --- Module manifest -------------------------------------------------------

export const matching: FeatureModule = {
  routes: [
    { path: '/employer/company', element: <CompanyPage />, roles: ['employer'] },
    { path: '/employer/candidates', element: <CandidatesPage />, roles: ['employer'] },
  ],
  navigation: [
    { to: '/employer/company', label: 'Моя компания', roles: ['employer'] },
    { to: '/employer/candidates', label: 'Кандидаты', roles: ['employer'] },
  ],
};
