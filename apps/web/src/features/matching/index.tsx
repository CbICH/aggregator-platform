import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { api, ApiError } from '../../shared/api';
import type { components } from '../../shared/api.generated';
import type { FeatureModule } from '../../shared/module';
import { Field, Notice } from '../../shared/ui';

type CompanyResponse = components['schemas']['CompanyResponse'];
type CandidateCard = components['schemas']['CandidateCard'];
type CandidateList = components['schemas']['CandidateList'];

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


// --- Company page ---------------------------------------------------------


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

  const update = useCallback(
    (key: keyof CompanyForm) => (value: string) => {
      setForm((prev) => ({ ...prev, [key]: value }));
    },
    []
  );

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError('');
    setSuccess('');
    setSaving(true);
    try {
      const payload = toPayload(form);
      const method = company ? 'PATCH' : 'POST';
      const data = await api<CompanyResponse>('/company', { method, body: payload });
      setCompany(data);
      setForm(toForm(data));
      setSuccess(company ? 'Профиль компании обновлён' : 'Профиль компании создан');
    } catch (reason) {
      setError(message(reason));
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="feature">Загрузка профиля компании…</div>;
  }

  return (
    <div className="feature feature--matching">
      <header>
        <h1>{company ? 'Профиль компании' : 'Создать компанию'}</h1>
        <p className="muted">
          Один работодатель — одна компания. Профиль используется в приглашениях и подборке.
        </p>
      </header>

      {error && <Notice tone="error">{error}</Notice>}
      {success && <Notice tone="success">{success}</Notice>}

      <form onSubmit={handleSubmit} className="form">
        <Field label="Название" required>
          <input value={form.name} onChange={(e) => update('name')(e.target.value)} required />
        </Field>
        <Field label="Описание" required>
          <textarea
            value={form.description}
            onChange={(e) => update('description')(e.target.value)}
            rows={4}
            required
          />
        </Field>
        <div className="grid-2">
          <Field label="Отрасль" required>
            <input
              value={form.industry}
              onChange={(e) => update('industry')(e.target.value)}
              required
            />
          </Field>
          <Field label="Город" required>
            <input value={form.city} onChange={(e) => update('city')(e.target.value)} required />
          </Field>
        </div>
        <h2>Контактное лицо</h2>
        <div className="grid-2">
          <Field label="ФИО" required>
            <input
              value={form.contact_name}
              onChange={(e) => update('contact_name')(e.target.value)}
              required
            />
          </Field>
          <Field label="Роль">
            <input
              value={form.contact_role}
              onChange={(e) => update('contact_role')(e.target.value)}
              placeholder="например, HR-партнёр"
            />
          </Field>
        </div>
        <Field label="Email" required>
          <input
            type="email"
            value={form.contact_email}
            onChange={(e) => update('contact_email')(e.target.value)}
            required
          />
        </Field>
        <div className="form-actions">
          <button type="submit" disabled={saving}>
            {saving ? 'Сохранение…' : company ? 'Сохранить изменения' : 'Создать компанию'}
          </button>
        </div>
      </form>
    </div>
  );
}


// --- Candidates page ------------------------------------------------------


function CandidatesPage() {
  const [data, setData] = useState<CandidateList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [specialization, setSpecialization] = useState<'' | 'backend' | 'qa'>('');
  const [grade, setGrade] = useState<'' | 'junior' | 'middle' | 'senior'>('');
  const [withFspOnly, setWithFspOnly] = useState(false);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (specialization) params.set('specialization', specialization);
    if (grade) params.set('grade', grade);
    if (withFspOnly) params.set('with_fsp_only', 'true');
    const query = params.toString();
    void (async () => {
      try {
        const list = await api<CandidateList>(`/employer/candidates${query ? '?' + query : ''}`);
        setData(list);
        setError('');
      } catch (reason) {
        setError(message(reason));
      } finally {
        setLoading(false);
      }
    })();
  }, [specialization, grade, withFspOnly]);

  return (
    <div className="feature feature--matching">
      <header>
        <h1>Подборка кандидатов</h1>
        <p className="muted">
          Формула: тест ×0.90 + ФСП ×0.10. С потребностью добавляется релевантность.
          Подключение к реальным кандидатам из профилей блока D — следующая итерация.
        </p>
      </header>

      {error && <Notice tone="error">{error}</Notice>}

      <div className="candidate-filters">
        <fieldset>
          <legend>Специализация</legend>
          <label>
            <input
              type="radio"
              name="specialization"
              checked={specialization === ''}
              onChange={() => setSpecialization('')}
            />
            Любая
          </label>
          <label>
            <input
              type="radio"
              name="specialization"
              checked={specialization === 'backend'}
              onChange={() => setSpecialization('backend')}
            />
            Backend
          </label>
          <label>
            <input
              type="radio"
              name="specialization"
              checked={specialization === 'qa'}
              onChange={() => setSpecialization('qa')}
            />
            QA
          </label>
        </fieldset>

        <fieldset>
          <legend>Грейд</legend>
          <label>
            <input
              type="radio"
              name="grade"
              checked={grade === ''}
              onChange={() => setGrade('')}
            />
            Все
          </label>
          {(['junior', 'middle', 'senior'] as const).map((g) => (
            <label key={g}>
              <input
                type="radio"
                name="grade"
                checked={grade === g}
                onChange={() => setGrade(g)}
              />
              {g[0].toUpperCase() + g.slice(1)}
            </label>
          ))}
        </fieldset>

        <label className="checkbox">
          <input
            type="checkbox"
            checked={withFspOnly}
            onChange={(e) => setWithFspOnly(e.target.checked)}
          />
          Только с ФСП
        </label>
      </div>

      {loading ? (
        <p>Загрузка…</p>
      ) : data && data.items.length ? (
        <ul className="candidate-list">
          {data.items.map((card: CandidateCard) => (
            <li key={card.candidate_id} className="candidate-card">
              <header>
                <h2>{card.display_name}</h2>
                <span className="muted">
                  {card.specialization} · {card.verified_grade} ·{' '}
                  {card.experience_years ? card.experience_years + ' лет опыта' : 'опыт не указан'}
                </span>
                <span className="score">{card.score.toFixed(1)}</span>
              </header>
              <dl className="grid-3">
                <div>
                  <dt>Тест</dt>
                  <dd>{Math.round(card.components.test ?? 0)}</dd>
                </div>
                <div>
                  <dt>ФСП</dt>
                  <dd>{Math.round(card.components.fsp ?? 0)}</dd>
                </div>
                <div>
                  <dt>Стек</dt>
                  <dd>{card.declared_stack.join(', ') || '—'}</dd>
                </div>
              </dl>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">
          Пока нет опубликованных кандидатов. Выдача наполнится, когда кандидаты пройдут тест
          и подтвердят категорию.
        </p>
      )}
    </div>
  );
}


// --- Feature module manifest ---------------------------------------------


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
