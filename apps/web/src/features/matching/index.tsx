import { useEffect, useState, type FormEvent } from 'react';
import { api, ApiError } from '../../shared/api';
import type { components } from '../../shared/api.generated';
import type { FeatureModule } from '../../shared/module';
import { Field, Notice } from '../../shared/ui';

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
          : 'Компания создана. Теперь можно приглашать специалистов.',
      );
    } catch (reason) {
      setError(message(reason));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <main className="assessment-page">
        <p role="status">Загружаем профиль компании…</p>
      </main>
    );
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
          <Field
            id="name"
            label="Название компании"
            value={form.name}
            onChange={(event) => update('name', event.target.value)}
            maxLength={120}
            placeholder="OrderFlow"
            required
          />
          <label className="field">
            <span>Описание</span>
            <textarea
              id="description"
              value={form.description}
              onChange={(event) => update('description', event.target.value)}
              maxLength={2000}
              rows={4}
              placeholder="Чем компания занимается, какой фронт работ, сколько человек в команде. Это читает кандидат при приглашении."
              required
            />
          </label>
          <Field
            id="industry"
            label="Отрасль"
            value={form.industry}
            onChange={(event) => update('industry', event.target.value)}
            maxLength={40}
            placeholder="fintech, it-services, analytics…"
            required
          />
          <Field
            id="city"
            label="Город"
            value={form.city}
            onChange={(event) => update('city', event.target.value)}
            maxLength={80}
            placeholder="Москва"
            required
          />
          <Field
            id="contact_name"
            label="Контактное лицо"
            value={form.contact_name}
            onChange={(event) => update('contact_name', event.target.value)}
            maxLength={120}
            placeholder="Анна Соколова"
            required
          />
          <Field
            id="contact_role"
            label="Роль контактного лица"
            value={form.contact_role}
            onChange={(event) => update('contact_role', event.target.value)}
            maxLength={80}
            placeholder="HR, тимлид (необязательно)"
          />
          <Field
            id="contact_email"
            label="Email для связи"
            type="email"
            value={form.contact_email}
            onChange={(event) => update('contact_email', event.target.value)}
            maxLength={254}
            placeholder="hr@orderflow.com"
            required
          />
          {error && <Notice error>{error}</Notice>}
          {success && <Notice>{success}</Notice>}
          <button className="button primary" disabled={saving}>
            {saving ? 'Сохраняем…' : company ? 'Сохранить изменения' : 'Создать компанию'}
          </button>
        </form>
      </section>
    </main>
  );
}

export const matching: FeatureModule = {
  routes: [{ path: '/employer/company', element: <CompanyPage />, roles: ['employer'] }],
  navigation: [{ to: '/employer/company', label: 'Моя компания', roles: ['employer'] }],
};
