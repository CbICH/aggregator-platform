import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { api, ApiError } from '../../shared/api';
import type { FeatureModule } from '../../shared/module';
import { Field, Notice } from '../../shared/ui';

// --- Shared helpers --------------------------------------------------------

function message(error: unknown) {
  return error instanceof ApiError
    ? error.message
    : 'Не удалось выполнить действие. Повторите попытку.';
}

// --- Company ---------------------------------------------------------------

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
      setSuccess(company ? 'Профиль компании обновлён.' : 'Компания создана.');
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
          {company && <p className="hint" style={{ marginTop: 24 }}>Готово? <Link to="/employer/candidates">Перейти к кандидатам →</Link></p>}
        </form>
      </section>
    </main>
  );
}


// --- Module manifest -------------------------------------------------------
//
// Страница кандидатов (/employer/candidates), её контактная подстраница
// (/employer/candidates/:id/contacts) и приглашения живут в модуле D
// (features/invitations). Этот модуль отвечает только за профиль компании.


export const matching: FeatureModule = {
  routes: [
    { path: '/employer/company', element: <CompanyPage />, roles: ['employer'] },
  ],
  navigation: [
    { to: '/employer/company', label: 'Моя компания', roles: ['employer'] },
  ],
};
