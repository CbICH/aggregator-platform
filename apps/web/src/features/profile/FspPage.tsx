import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, ApiError } from '../../shared/api';
import type { components } from '../../shared/api.generated';
import { Field, Notice } from '../../shared/ui';
import './profile.css';

type Fsp = components['schemas']['FspEvidence'];
const labels = { not_linked: 'ФСП ID не связан', linked_empty: 'Профиль связан; истории достижений нет', linked_with_data: 'Данные о достижениях получены', unavailable: 'Источник ФСП временно недоступен' };

export function FspPage() {
  const navigate = useNavigate();
  const [state, setState] = useState<Fsp | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setBusy(true); setError('');
    try { setState(await api<Fsp>('/candidate/fsp')); }
    catch (e) { setState(null); if (e instanceof ApiError && e.status === 401) navigate('/login'); else setError(e instanceof ApiError && [404, 503].includes(e.status) ? 'Источник ФСП временно недоступен. Вы можете продолжить без истории достижений.' : e instanceof Error ? e.message : 'Не удалось получить данные ФСП'); }
    finally { setBusy(false); }
  }, [navigate]);
  useEffect(() => { void load(); }, [load]);
  async function link(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const values = new FormData(event.currentTarget); setBusy(true); setError('');
    try { await api('/candidate/fsp-link', { method: 'POST', body: JSON.stringify({ fsp_id: String(values.get('fsp_id') ?? '').trim() }) }); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Не удалось связать профиль'); }
    finally { setBusy(false); }
  }
  async function unlink() {
    setBusy(true); setError('');
    try { await api('/candidate/fsp-link', { method: 'DELETE' }); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Не удалось отключить связь'); }
    finally { setBusy(false); }
  }
  return <main className="workspace profile-page"><Link className="profile-back" to="/candidate/profile">← Мой профиль</Link><span className="eyebrow">ФСП</span><h1>История достижений</h1><p className="lead">Связь с ФСП ID дополняет профиль. Отсутствие истории не мешает приглашениям.</p>
    {error && <Notice error>{error}</Notice>}{busy && <p role="status">Получаем данные ФСП…</p>}
    <section className="profile-section"><h2>{state ? labels[state.status] : 'Данные пока недоступны'}</h2>
      {state?.status === 'linked_with_data' && <p>Сигнал ФСП: {state.signal}/100 · {state.source === 'demo' ? 'демонстрационные данные' : 'реестр'}</p>}
      <button className="button" disabled={busy} onClick={() => void load()}>Обновить статус ФСП</button>
      {state?.status === 'not_linked' && <form onSubmit={link}><Field id="fsp-id" label="Ваш ФСП ID" name="fsp_id" required maxLength={100} /><p className="hint">После отправки сервис проверит связь; введённый ID сам по себе не подтверждает достижения.</p><button className="button primary" disabled={busy}>Связать профиль</button></form>}
      {state && ['linked_empty', 'linked_with_data'].includes(state.status) && <button className="button" disabled={busy} onClick={() => void unlink()}>Отключить связь</button>}
    </section></main>;
}
