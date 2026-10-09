import { useEffect, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, ApiError } from '../../shared/api';
import type { components } from '../../shared/api.generated';
import { Field, Notice } from '../../shared/ui';

type Filters = components['schemas']['SearchFilters'];
type Result = components['schemas']['SearchResponse'];
type History = components['schemas']['SearchHistory'];
type Summary = components['schemas']['SearchSummary'];
type Need = components['schemas']['NeedResponse'];
type Category = components['schemas']['CategoryCard'];
const emptyFilters: Filters = { need_id: null, specialization: null, grade: null, category_code: null, stack: [], with_fsp_only: false };
const errorText = (error: unknown) => error instanceof Error ? error.message : 'Не удалось загрузить подборку';

export function MatchingPage() {
  const [params, setParams] = useSearchParams();
  const searchId = params.get('search');
  const needParam = params.get('need');
  const [result, setResult] = useState<Result | null>(null);
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [stack, setStack] = useState('');
  const [needs, setNeeds] = useState<Need[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [history, setHistory] = useState<Summary[]>([]);
  const [historyOffset, setHistoryOffset] = useState<number | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [companyRequired, setCompanyRequired] = useState(false);

  useEffect(() => {
    let active = true;
    setBusy(true); setError('');
    void (async () => {
      try {
        const [owned, catalogue] = await Promise.all([
          api<components['schemas']['NeedList']>('/employer/needs'),
          api<components['schemas']['CategoryList']>('/employer/categories'),
        ]);
        if (!active) return;
        setNeeds(owned.items); setCategories(catalogue.items);
        const value = searchId
          ? await api<Result>(`/employer/searches/${encodeURIComponent(searchId)}`)
          : await api<Result>('/employer/searches', { method: 'POST', body: JSON.stringify({ ...emptyFilters, need_id: needParam }) });
        if (!searchId) {
          if (active) setParams({ search: value.id }, { replace: true });
          return;
        }
        const saved = await api<History>('/employer/searches');
        if (!active) return;
        setResult(value); setFilters(value.filters); setStack((value.filters.stack ?? []).join(', '));
        setHistory(saved.items); setHistoryOffset(saved.next_offset ?? null); setCompanyRequired(false);
      } catch (reason) {
        if (active) { setResult(null); setError(errorText(reason)); setCompanyRequired(reason instanceof ApiError && reason.code === 'COMPANY_REQUIRED'); setBusy(false); }
      } finally { if (active && searchId) setBusy(false); }
    })();
    return () => { active = false; };
  }, [searchId, needParam, setParams]);

  async function search(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const value = await api<Result>('/employer/searches', { method: 'POST', body: JSON.stringify({ ...filters, stack: stack.split(',').map((value) => value.trim()).filter(Boolean) }) });
      setParams({ search: value.id });
    } catch (reason) { setError(errorText(reason)); setBusy(false); }
  }

  async function refresh(more = false) {
    if (!result) return;
    setBusy(true); setError('');
    try {
      const value = await api<Result>(`/employer/searches/${result.id}${more && result.next_offset != null ? `?offset=${result.next_offset}` : ''}`);
      setResult(more ? { ...value, items: [...result.items, ...value.items] } : value);
    } catch (reason) { setResult(null); setError(errorText(reason)); } finally { setBusy(false); }
  }

  async function moreHistory() {
    if (historyOffset == null) return;
    setBusy(true);
    try {
      const value = await api<History>(`/employer/searches?offset=${historyOffset}`);
      setHistory((old) => [...old, ...value.items]); setHistoryOffset(value.next_offset ?? null);
    } catch (reason) { setError(errorText(reason)); } finally { setBusy(false); }
  }

  return <main className="assessment-page">
    <section className="assessment-heading"><div><span className="eyebrow">ОБРАТНЫЙ ПОДБОР</span><h1>Подбор кандидатов</h1>
      <p>Опишите потребность и сравните подтверждённые навыки. Контакты откроются после принятия приглашения.</p></div>
      <Link className="button" to="/employer/needs/new">Новая потребность</Link></section>
    {error && <Notice error>{error}{companyRequired && <p><Link to="/employer/company">Заполнить компанию</Link></p>}</Notice>}
    {!companyRequired && <form className="assessment-panel assessment-form" onSubmit={search}>
      <label className="field"><span>С учётом потребности</span><select disabled={busy} value={filters.need_id ?? ''} onChange={(event) => setFilters({ ...filters, need_id: event.target.value || null, specialization: null, grade: null })}>
        <option value="">Без потребности</option>{needs.map((need) => <option key={need.id} value={need.id}>{need.title}</option>)}</select></label>
      <div className="profile-contact-grid">
        <label className="field"><span>Специализация</span><select disabled={busy || !!filters.need_id} value={filters.specialization ?? ''} onChange={(event) => setFilters({ ...filters, specialization: (event.target.value || null) as Filters['specialization'] })}>
          <option value="">Любая</option><option value="backend">Backend</option><option value="qa">QA</option></select></label>
        <label className="field"><span>Грейд</span><select disabled={busy || !!filters.need_id} value={filters.grade ?? ''} onChange={(event) => setFilters({ ...filters, grade: (event.target.value || null) as Filters['grade'] })}>
          <option value="">Любой</option>{['junior', 'middle', 'senior'].map((grade) => <option key={grade} value={grade}>{grade}</option>)}</select></label>
      </div>
      <label className="field"><span>Категория</span><select disabled={busy} value={filters.category_code ?? ''} onChange={(event) => setFilters({ ...filters, category_code: (event.target.value || null) as Filters['category_code'] })}>
        <option value="">Все категории</option>{categories.map((category) => <option key={category.code} value={category.code}>{category.code} · {category.candidate_count} профилей</option>)}</select></label>
      <Field id="search-stack" label="Стек (через запятую)" value={stack} onChange={(event) => setStack(event.target.value)} placeholder="python, postgresql" maxLength={500} disabled={busy} />
      <p className="hint">Скрытый стек не используется в фильтре. Если стек не указан здесь, учитываются технологии выбранной потребности.</p>
      <label className="checkbox-line"><input type="checkbox" checked={filters.with_fsp_only ?? false} onChange={(event) => setFilters({ ...filters, with_fsp_only: event.target.checked })} disabled={busy} /> Только с достижениями ФСП</label>
      <button className="button primary" disabled={busy}>Подобрать и сохранить</button>
    </form>}
    {history.length > 0 && <section className="assessment-panel" style={{ marginTop: 18 }}>
      <label className="field"><span>Предыдущие подборки</span><select disabled={busy} value={result?.id ?? ''} onChange={(event) => setParams({ search: event.target.value })}>
        <option value="" disabled>Выберите подборку</option>
        {result && !history.some((item) => item.id === result.id) && <option value={result.id}>{result.need_title ?? 'Поиск по банку'} · текущая</option>}
        {history.map((item) => <option key={item.id} value={item.id}>{item.need_title ?? 'Поиск по банку'} · {new Date(item.created_at).toLocaleString('ru-RU')} · {item.original_total} профилей</option>)}
      </select></label>{historyOffset != null && <button type="button" className="button" disabled={busy} onClick={() => void moreHistory()}>Показать ещё подборки</button>}
      <p className="hint">Состав прежней подборки сохранён. Доступность профилей, видимые поля и баллы проверяются заново при открытии.</p>
    </section>}
    {busy && <p role="status">Собираем подборку…</p>}
    {result && <>
      <section className="assessment-heading" style={{ marginTop: 24 }}><div><h2>{result.need_title ?? 'Поиск по банку кандидатов'}</h2><p>{result.total} доступных профилей{result.unavailable_count ? ` · ${result.unavailable_count} больше недоступны` : ''}</p></div>
        <button type="button" className="button" disabled={busy} onClick={() => void refresh()}>Обновить подборку</button></section>
      <p className="hint">{result.applied_need_id ? 'Балл: тест ×0,65 + соответствие проверенных навыков ×0,25 + ФСП ×0,10.' : 'Балл: подтверждённый тест ×0,90 + ФСП ×0,10.'} Отсутствие истории ФСП не исключает кандидата.</p>
      {!busy && result.total === 0 && <Notice>Подходящих опубликованных профилей пока нет. Смените фильтры или откройте предыдущую подборку.</Notice>}
      <div className="assessment-items">
        {result.items.map((card) => <article className="assessment-panel" key={card.candidate_id}>
          <header style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}><div><h2>{card.display_name}</h2><p>{card.category_code}{card.experience_months != null ? ` · ${card.experience_months} мес. опыта` : ' · стаж скрыт'}</p></div><strong className="participant-code" style={{ fontSize: 28 }}>{card.score.toFixed(1)}</strong></header>
          <div className="evidence-grid"><div><span>Тест</span><p>{card.components.test?.toFixed(0)}/100</p></div>
            {card.components.relevance != null && <div><span>Соответствие навыков</span><p>{card.components.relevance.toFixed(0)}/100</p></div>}
            <div><span>ФСП</span><p>{card.components.fsp?.toFixed(0)}/100</p><p>{card.fsp_status === 'linked_with_data' ? (card.fsp_source === 'demo' ? 'Синтетический реестр ФСП' : 'Реестр ФСП') : card.fsp_status === 'unavailable' ? 'Реестр временно недоступен' : 'Нет истории достижений'}</p></div>
            <div><span>Заявленный стек</span><p>{card.declared_stack?.join(', ') || 'Стек скрыт'}</p></div></div>
          <h3>Почему подходит</h3><ul>{card.reasons.map((reason, index) => <li key={index}>{reason.code === 'SKILL_MATCH' ? `${reason.skill_id} · ${reason.score}/100` : reason.label ?? `${reason.skill_id} · ${reason.score}/100`}</li>)}</ul>
          {card.fsp_achievements?.map((achievement, index) => <p key={index}>{achievement.event} · {achievement.result} · {achievement.date}</p>)}
          <Link className="button primary" to={`/employer/invitations/new?candidate_id=${card.candidate_id}${result.applied_need_id ? `&need_id=${result.applied_need_id}` : ''}`}>Предложить работу</Link>
        </article>)}
      </div>{result.next_offset != null && <button type="button" className="button" disabled={busy} onClick={() => void refresh(true)}>Показать ещё кандидатов</button>}
    </>}
  </main>;
}
