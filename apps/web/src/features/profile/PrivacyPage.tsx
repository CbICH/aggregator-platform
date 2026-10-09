import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, ApiError } from '../../shared/api';
import type { components } from '../../shared/api.generated';
import { Notice } from '../../shared/ui';
import './profile.css';

type Privacy = components['schemas']['PrivacyResponse'];
const fields = [{ id: 'roles', label: 'Роли' }, { id: 'declared_stack', label: 'Технологии' }, { id: 'experience_months', label: 'Стаж' }];
const reasons: Record<string, string> = { email_not_verified: 'Подтвердите email', profile_incomplete: 'Заполните основные сведения профиля', processing_consent_required: 'Примите условия обработки профиля', publication_consent_required: 'Разрешите публикацию', category_not_verified: 'Подтвердите категорию тестированием' };

export function PrivacyPage() {
  const navigate = useNavigate();
  const [privacy, setPrivacy] = useState<Privacy | null>(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [revokeProcessing, setRevokeProcessing] = useState(false);
  const load = useCallback(async () => {
    setBusy(true); setError(''); setMessage('');
    try { setPrivacy(await api<Privacy>('/candidate/privacy')); }
    catch (e) { if (e instanceof ApiError && e.status === 401) navigate('/login'); else setError(e instanceof Error ? e.message : 'Не удалось загрузить настройки'); }
    finally { setBusy(false); }
  }, [navigate]);
  useEffect(() => { void load(); }, [load]);

  async function change(payload: Record<string, unknown>) {
    if (!privacy) return;
    setBusy(true); setError(''); setMessage('');
    try { setPrivacy(await api<Privacy>('/candidate/privacy', { method: 'PATCH', body: JSON.stringify({ expected_version: privacy.version, ...payload }) })); setMessage('Настройки сохранены.'); }
    catch (e) { if (e instanceof ApiError && e.status === 401) navigate('/login'); else setError(e instanceof Error ? e.message : 'Не удалось сохранить настройки'); }
    finally { setBusy(false); }
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const publication = values.get('publication') === 'on';
    await change({ visible_fields: values.getAll('visible_fields'), ...(publication && !privacy?.publication_enabled ? {
      publication_enabled: true, publication_consent_accepted: true, publication_consent_version: privacy?.publication_policy.version,
    } : !publication && privacy?.publication_enabled ? { publication_enabled: false } : {}) });
  }
  async function revokeProfileProcessing() {
    if (!privacy) return;
    setBusy(true); setError(''); setMessage('');
    try {
      setPrivacy(await api<Privacy>('/candidate/consents', { method: 'POST', body: JSON.stringify({ expected_version: privacy.version, consent_type: 'profile_processing', action: 'revoke', version: 'profile-processing-v1' }) }));
      setMessage('Согласие на обработку отозвано. Публикация и доступ компаний к контактам отключены.'); setRevokeProcessing(false);
    } catch (e) { if (e instanceof ApiError && e.status === 401) navigate('/login'); else setError(e instanceof Error ? e.message : 'Не удалось отозвать согласие'); }
    finally { setBusy(false); }
  }
  return <main className="workspace profile-page"><Link className="profile-back" to="/candidate/profile">← Мой профиль</Link>
    <span className="eyebrow">ПРИВАТНОСТЬ</span><h1>Вы управляете доступом</h1><p className="lead">Публикация профиля и передача контактов — отдельные разрешения.</p>
    {error && <Notice error>{error} <button className="inline-button" disabled={busy} onClick={() => void load()}>Загрузить актуальные настройки</button></Notice>}
    {message && <Notice>{message}</Notice>}
    {!privacy ? <section className="profile-section">{busy ? <p role="status">Загружаем настройки…</p> : <button className="button" onClick={() => void load()}>Повторить</button>}</section> : <div className="profile-layout">
      <form className="profile-form" onSubmit={save} key={privacy.version}><fieldset className="profile-section" disabled={busy || privacy.version === 0}>
        <legend>Публикация</legend><p>Работодатели увидят псевдоним и подтверждённые навыки. ФИО, свободное резюме и контакты остаются приватными.</p>
        <label className="consent"><input type="checkbox" name="publication" defaultChecked={privacy.publication_enabled} /><span>Разрешаю публикацию моего профиля работодателям</span></label>
        <details className="policy"><summary>Условия публикации</summary><p>{privacy.publication_policy.text}</p></details>
        <h2>Дополнительные видимые поля</h2><div className="privacy-fields">{fields.map((field) => <label key={field.id}><input type="checkbox" name="visible_fields" value={field.id} defaultChecked={(privacy.visible_fields ?? []).includes(field.id)} />{field.label}</label>)}</div>
        <p className="hint">Скрытые поля не передаются работодателям и не участвуют в их фильтрах. В публичном стеке отображаются распознанные технологии; произвольный текст остаётся приватным.</p>
        <button className="button primary" disabled={busy || privacy.version === 0}>{busy ? 'Сохраняем…' : 'Сохранить настройки'}</button>
      </fieldset>{privacy.version === 0 && <Notice>Сначала <Link to="/candidate/profile">сохраните профиль</Link>.</Notice>}
      <section className="profile-section"><h2>Отозвать публикацию</h2><p>Профиль исчезнет из новых и сохранённых подборок. Условия уже отправленных предложений сохранятся.</p>
        <button type="button" className="button" disabled={busy || !privacy.publication_enabled} onClick={() => void change({ publication_enabled: false })}>Скрыть профиль</button></section>
      <section className="profile-section"><h2>Отозвать доступ к контактам</h2><p>Компании больше не смогут получать контакты через сервис. Это не удалит сведения, которые они уже получили.</p>
        <button type="button" className="button" disabled={busy || privacy.version === 0} onClick={() => void change({ revoke_contact_access: true })}>Отозвать доступ к контактам</button></section>
      <section className="profile-section"><h2>Обработка данных профиля</h2><p>После отзыва профиль будет скрыт и компании потеряют доступ к контактам. Для нового сохранения и PDF нужно снова принять условия обработки.</p>
        <label className="consent"><input type="checkbox" checked={revokeProcessing} onChange={(event) => setRevokeProcessing(event.target.checked)} disabled={busy || !privacy.processing_consent_active} /><span>Хочу отозвать согласие на обработку профиля</span></label>
        <button type="button" className="button" disabled={busy || !revokeProcessing || !privacy.processing_consent_active} onClick={() => void revokeProfileProcessing()}>Отозвать согласие на обработку</button></section>
      </form><aside className="profile-summary"><section className="profile-section"><span className="eyebrow">ВИДИМОСТЬ</span><h2>{privacy.discoverable ? 'Профиль доступен работодателям' : 'Профиль пока не виден в подборках'}</h2>
        {(privacy.blocked_reasons ?? []).length > 0 && <ul>{(privacy.blocked_reasons ?? []).map((reason) => <li key={reason}>{reasons[reason] ?? reason}</li>)}</ul>}
        <p className="muted">Отсутствие истории ФСП не мешает публикации.</p></section>
        <section className="profile-section"><h2>История согласий</h2>{privacy.consents.length === 0 ? <p>Согласий пока нет.</p> : privacy.consents.map((receipt, index) => <p key={index}>{receipt.consent_type === 'publication' ? 'Публикация' : receipt.consent_type === 'profile_processing' ? 'Обработка профиля' : 'Передача контактов'}: {receipt.revoked_at ? 'отозвано' : 'принято'} · {new Date(receipt.accepted_at).toLocaleDateString('ru-RU')}</p>)}</section>
      </aside></div>}
  </main>;
}
