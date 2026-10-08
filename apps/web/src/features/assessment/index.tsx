import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import type { components } from '../../shared/api.generated';
import { api, ApiError } from '../../shared/api';
import type { FeatureModule } from '../../shared/module';
import { Notice } from '../../shared/ui';

type CategoryState = components['schemas']['CategoryState'];
type Attempt = components['schemas']['AssessmentResult'];
type History = components['schemas']['AssessmentHistory'];
type SurveyHistory = components['schemas']['SurveyHistory'];
type CategoryHistory = components['schemas']['CategoryHistory'];
type Survey = components['schemas']['SurveyCreate'];

const grades = [
  ['junior', 'Junior'],
  ['middle', 'Middle'],
  ['senior', 'Senior'],
] as const;
const families: Record<string, { label: string; skills: string; weight: number }> = {
  api: { label: 'Поведение API', skills: 'Поведение API, идемпотентность', weight: 40 },
  data: { label: 'Данные и границы', skills: 'SQL, граничные случаи', weight: 35 },
  decision: { label: 'Решение при ограничениях', skills: 'Поведение API', weight: 25 },
  defects: { label: 'Поиск дефектов', skills: 'Анализ дефектов', weight: 40 },
  test_design: { label: 'Набор проверок', skills: 'Проектирование тестов', weight: 35 },
  risk: { label: 'Приоритизация рисков', skills: 'Приоритизация рисков', weight: 25 },
};

function message(error: unknown) {
  return error instanceof ApiError ? error.message : 'Не удалось выполнить действие. Повторите попытку.';
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}

function Countdown({ deadline }: { deadline: string }) {
  const [left, setLeft] = useState(() => Math.max(0, new Date(deadline).getTime() - Date.now()));
  useEffect(() => {
    const timer = window.setInterval(() => setLeft(Math.max(0, new Date(deadline).getTime() - Date.now())), 1000);
    return () => window.clearInterval(timer);
  }, [deadline]);
  const minutes = Math.floor(left / 60_000);
  const seconds = Math.floor((left % 60_000) / 1000);
  return <strong className={left < 300_000 ? 'timer urgent' : 'timer'}>{minutes}:{String(seconds).padStart(2, '0')}</strong>;
}

function SurveyForm({ onStarted }: { onStarted: (attempt: Attempt) => void }) {
  const [form, setForm] = useState<Survey>({ industry: '', specialization: 'backend', declared_grade: 'middle', roles: [''], experience_months: 0 });
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const update = <K extends keyof Survey>(key: K, value: Survey[K]) => setForm((old) => ({ ...old, [key]: value }));
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    const payload = { ...form, industry: form.industry.trim(), roles: form.roles.map((role) => role.trim()).filter(Boolean) };
    if (!payload.industry || !payload.roles.length) { setError('Заполните отрасль и роль, на которую ориентируетесь.'); return; }
    setSaving(true);
    try {
      await api('/candidate/surveys', { method: 'POST', body: JSON.stringify(payload) });
      const attempt = await api<Attempt>('/assessments', { method: 'POST', body: JSON.stringify({ specialization: payload.specialization, target_grade: payload.declared_grade }) });
      onStarted(attempt);
    } catch (reason) { setError(message(reason)); } finally { setSaving(false); }
  };
  return <section className="assessment-panel"><span className="eyebrow">ПЕРЕД ТЕСТОМ</span><h1>Расскажите о направлении</h1><p className="lead">Опрос задаёт контекст попытки. Он не присваивает грейд: категорию подтверждает только результат теста.</p>
    <form className="assessment-form" onSubmit={submit}>
      <label className="field"><span>Отрасль</span><input value={form.industry} onChange={(event) => update('industry', event.target.value)} placeholder="Например, финтех" maxLength={80} /></label>
      <fieldset className="choice-field"><legend>Специализация</legend><div className="choice-row"><label><input type="radio" checked={form.specialization === 'backend'} onChange={() => update('specialization', 'backend')} /> Backend</label><label><input type="radio" checked={form.specialization === 'qa'} onChange={() => update('specialization', 'qa')} /> QA</label></div></fieldset>
      <fieldset className="choice-field"><legend>Какой уровень хотите подтвердить</legend><div className="choice-row">{grades.map(([id, label]) => <label key={id}><input type="radio" checked={form.declared_grade === id} onChange={() => update('declared_grade', id)} /> {label}</label>)}</div></fieldset>
      <label className="field"><span>Целевая роль</span><input value={form.roles[0]} onChange={(event) => update('roles', [event.target.value])} placeholder="Backend developer" maxLength={60} /></label>
      <label className="field"><span>Стаж в месяцах</span><input type="number" min="0" max="720" value={form.experience_months} onChange={(event) => update('experience_months', Number(event.target.value))} /></label>
      {error && <Notice error>{error}</Notice>}<button className="button primary" disabled={saving}>{saving ? 'Готовим задания…' : 'Начать тест'}</button>
    </form></section>;
}

function AttemptView({ attempt, onFinished }: { attempt: Attempt; onFinished: (next: Attempt) => void }) {
  const [answers, setAnswers] = useState<Record<string, Record<string, unknown>>>(() => Object.fromEntries((attempt.items ?? []).map((item) => [item.id, item.answers ?? {}])));
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const setAnswer = (itemId: string, name: string, value: unknown) => setAnswers((old) => ({ ...old, [itemId]: { ...old[itemId], [name]: value } }));
  const save = async () => api<Attempt>(`/assessments/${attempt.id}/answers`, { method: 'PUT', body: JSON.stringify({ answers }) });
  const saveDraft = async () => { setBusy(true); setError(''); try { onFinished(await save()); } catch (reason) { setError(message(reason)); } finally { setBusy(false); } };
  const submit = async () => { setBusy(true); setError(''); try { await save(); onFinished(await api<Attempt>(`/assessments/${attempt.id}/submit`, { method: 'POST' })); } catch (reason) { setError(message(reason)); } finally { setBusy(false); } };
  return <main className="assessment-page"><div className="assessment-heading"><div><span className="eyebrow">ТЕСТ · {attempt.specialization} · {attempt.target_grade}</span><h1>Подтверждение навыков</h1><p>Сохранение черновика не завершает попытку. Оценка выполняется сервером после отправки.</p></div><div className="timer-card"><span>До завершения</span><Countdown deadline={attempt.deadline_at} /></div></div>
    <div className="assessment-items">{(attempt.items ?? []).map((item) => <article className="task-card" key={item.id}><div className="task-meta"><span>{String(item.position).padStart(2, '0')}</span><span>{families[item.family]?.label ?? item.family}</span></div><h2>{item.title}</h2><p>{item.scenario}</p>{item.questions.map((question) => <fieldset className="question" key={question.name}><legend>{question.label}</legend>{question.kind === 'number' ? <input type="number" value={String(answers[item.id]?.[question.name] ?? '')} onChange={(event) => setAnswer(item.id, question.name, event.target.value === '' ? '' : Number(event.target.value))} /> : question.kind === 'choice' ? <div className="question-options">{(question.choices ?? []).map((choice) => <label key={choice.id}><input type="radio" name={`${item.id}-${question.name}`} checked={answers[item.id]?.[question.name] === choice.id} onChange={() => setAnswer(item.id, question.name, choice.id)} /> {choice.label}</label>)}</div> : <div className="question-options">{(question.choices ?? []).map((choice) => { const selected = Array.isArray(answers[item.id]?.[question.name]) ? answers[item.id][question.name] as string[] : []; return <label key={choice.id}><input type="checkbox" checked={selected.includes(choice.id)} onChange={(event) => setAnswer(item.id, question.name, event.target.checked ? [...selected, choice.id] : selected.filter((id) => id !== choice.id))} /> {choice.label}</label>; })}</div>}</fieldset>)}</article>)}</div>
    {error && <Notice error>{error}</Notice>}<div className="assessment-actions"><button className="button ghost" disabled={busy} onClick={() => void saveDraft()}>Сохранить черновик</button><button className="button primary" disabled={busy} onClick={() => void submit()}>{busy ? 'Проверяем…' : 'Завершить и проверить'}</button></div></main>;
}

function Result({ attempt, state, onConfirmed, onRetake, onHigher }: { attempt: Attempt; state: CategoryState; onConfirmed: () => void; onRetake: () => void; onHigher: (attempt: Attempt) => void }) {
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const confirm = async () => { setBusy(true); setError(''); try { await api('/candidate/category/confirm', { method: 'POST', body: JSON.stringify({ assessment_id: attempt.id }) }); onConfirmed(); } catch (reason) { setError(message(reason)); } finally { setBusy(false); } };
  const passed = attempt.status === 'passed';
  const higher = ({ junior: 'middle', middle: 'senior' } as const)[attempt.target_grade as 'junior' | 'middle'];
  const startHigher = async () => { if (!higher) return; setBusy(true); setError(''); try { onHigher(await api<Attempt>('/assessments', { method: 'POST', body: JSON.stringify({ specialization: attempt.specialization, target_grade: higher }) })); } catch (reason) { setError(message(reason)); } finally { setBusy(false); } };
  return <main className="assessment-page"><section className="result-panel"><span className="eyebrow">РЕЗУЛЬТАТ ТЕСТА</span><h1>{passed ? 'Результат готов' : 'Попытка не пройдена'}</h1><div className="score-block"><strong>{attempt.score?.toFixed(1) ?? '—'}</strong><span>из 100</span></div><p>{passed ? 'Вы прошли порог 70 баллов и минимум по критическим семействам. Подтвердите категорию отдельным действием.' : 'Текущая подтверждённая категория не изменится. Через 24 часа можно повторить этот уровень или выбрать другой путь.'}</p></section>
    <section className="evidence-grid">{Object.entries(attempt.family_scores ?? {}).map(([family, value]) => <article key={family}><span>{families[family]?.label ?? family}</span><strong>{value} / {families[family]?.weight}</strong><p>{families[family]?.skills}</p></article>)}</section>
    <div className="assessment-actions">{passed && <button className="button primary" disabled={busy} onClick={() => void confirm()}>{busy ? 'Подтверждаем…' : `Подтвердить ${attempt.specialization} · ${attempt.target_grade}`}</button>}{passed && !state.verified && attempt.next_grade_recommended && higher && <button className="button ghost" disabled={busy} onClick={() => void startHigher()}>Попробовать {higher}</button>}{!passed && <button className="button ghost" onClick={onRetake}>Выбрать новую попытку</button>}</div>{error && <Notice error>{error}</Notice>}</main>;
}

function AssessmentPage() {
  const [state, setState] = useState<CategoryState | null>(null); const [history, setHistory] = useState<History | null>(null); const [surveyHistory, setSurveyHistory] = useState<SurveyHistory | null>(null); const [categoryHistory, setCategoryHistory] = useState<CategoryHistory | null>(null); const [attempt, setAttempt] = useState<Attempt | null>(null); const [loading, setLoading] = useState(true); const [error, setError] = useState('');
  const load = useCallback(async () => { setLoading(true); setError(''); try { const [category, attempts, surveys, categories] = await Promise.all([api<CategoryState>('/candidate/category'), api<History>('/candidate/assessments'), api<SurveyHistory>('/candidate/surveys'), api<CategoryHistory>('/candidate/category/history')]); setState(category); setHistory(attempts); setSurveyHistory(surveys); setCategoryHistory(categories); const postVerification = category.verified ? (attempts.items ?? []).find((item) => new Date(item.started_at) > new Date(category.verified!.assigned_at)) : attempts.items?.[0]; const current = (attempts.items ?? []).find((item) => item.status === 'in_progress') ?? category.provisional ?? postVerification; setAttempt(current ? await api<Attempt>(`/assessments/${current.id}`) : null); } catch (reason) { setError(message(reason)); } finally { setLoading(false); } }, []);
  useEffect(() => { void load(); }, [load]);
  if (loading) return <main className="centered"><p role="status">Загружаем тестирование…</p></main>;
  if (error) return <main className="centered"><Notice error>{error} <button className="inline-button" onClick={() => void load()}>Повторить</button></Notice></main>;
  if (attempt) return attempt.status === 'in_progress' ? <AttemptView attempt={attempt} onFinished={(next) => { setAttempt(next.status === 'in_progress' ? next : null); void load(); }} /> : <Result attempt={attempt} state={state!} onConfirmed={() => void load()} onRetake={() => setAttempt(null)} onHigher={setAttempt} />;
  if (!state?.verified) return <main className="assessment-page"><SurveyForm onStarted={setAttempt} />{(surveyHistory?.items ?? []).length > 0 && <section className="history"><h2>История опросов</h2>{(surveyHistory?.items ?? []).map((survey) => <article key={survey.id}><span>{formatDate(survey.created_at)}</span><strong>{survey.specialization} · {survey.declared_grade}</strong><span>{survey.industry}</span></article>)}</section>}</main>;
  return <main className="assessment-page"><section className="assessment-panel"><span className="eyebrow">МОЯ КАТЕГОРИЯ</span><h1>{state.verified.category_code}</h1><p className="lead">Подтверждено тестом {state.verified.test_score.toFixed(1)} из 100. Следующая смена категории доступна {formatDate(state.verified.next_change_at)}.</p><div className="evidence-grid">{state.verified.skills.map((skill) => <article key={skill.id}><span>{skill.id}</span><strong>{skill.score.toFixed(1)}</strong><p>подтверждено тестом</p></article>)}</div></section><section className="history"><h2>История категорий</h2>{(categoryHistory?.items ?? []).map((item) => <article key={item.assessment_id}><span>{formatDate(item.assigned_at)}</span><strong>{item.category_code}</strong><span>Следующая смена: {formatDate(item.next_change_at)}</span></article>)}</section><section className="history"><h2>История попыток</h2>{(history?.items ?? []).map((item) => <article key={item.id}><span>{formatDate(item.started_at)}</span><strong>{item.specialization} · {item.target_grade}</strong><span>{item.status === 'passed' ? `Пройдено: ${item.score}` : item.status === 'failed' ? `Не пройдено: ${item.score}` : 'Истекло'}</span></article>)}</section><section className="history"><h2>История опросов</h2>{(surveyHistory?.items ?? []).map((survey) => <article key={survey.id}><span>{formatDate(survey.created_at)}</span><strong>{survey.specialization} · {survey.declared_grade}</strong><span>{survey.industry}</span></article>)}</section></main>;
}

export const assessment: FeatureModule = { routes: [{ path: '/candidate/assessment', element: <AssessmentPage />, roles: ['candidate'] }], navigation: [{ to: '/candidate/assessment', label: 'Мой тест', roles: ['candidate'] }] };
