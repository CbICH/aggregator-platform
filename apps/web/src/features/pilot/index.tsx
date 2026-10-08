import { useCallback, useEffect, useState } from 'react';
import type { components } from '../../shared/api.generated';
import { api, ApiError } from '../../shared/api';
import type { FeatureModule } from '../../shared/module';
import { Notice } from '../../shared/ui';

type PilotState = components['schemas']['PilotState'];
type PilotAttempt = components['schemas']['PilotAttemptPublic'];

function message(error: unknown) {
  return error instanceof ApiError ? error.message : 'Не удалось выполнить действие. Повторите попытку.';
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

function JoinPilot({ onJoined }: { onJoined: (state: PilotState) => void }) {
  const [invite, setInvite] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const join = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true); setError('');
    try {
      onJoined(await api<PilotState>('/candidate/pilot/join', {
        method: 'POST', body: JSON.stringify({ invite_code: invite.trim() }),
      }));
    } catch (reason) { setError(message(reason)); } finally { setBusy(false); }
  };
  return <section className="assessment-panel pilot-panel"><span className="eyebrow">КОНТРОЛИРУЕМЫЙ ПИЛОТ</span><h1>Вход по приглашению</h1><p className="lead">Пилот состоит из двух сопоставимых форм A/B. Он не изменяет вашу категорию и не влияет на подбор вакансий.</p><form className="assessment-form" onSubmit={join}><label className="field"><span>Код приглашения</span><input value={invite} onChange={(event) => setInvite(event.target.value)} autoComplete="off" maxLength={128} required /></label><button className="button primary" disabled={busy}>{busy ? 'Проверяем…' : 'Вступить в пилот'}</button></form>{error && <Notice error>{error}</Notice>}</section>;
}

function Question({ item, question, answers, setAnswer }: {
  item: components['schemas']['AssessmentItemPublic'];
  question: components['schemas']['AssessmentQuestion'];
  answers: Record<string, Record<string, unknown>>;
  setAnswer: (itemId: string, name: string, value: unknown) => void;
}) {
  if (question.kind === 'number') return <input type="number" value={String(answers[item.id]?.[question.name] ?? '')} onChange={(event) => setAnswer(item.id, question.name, event.target.value === '' ? '' : Number(event.target.value))} />;
  if (question.kind === 'choice') return <div className="question-options">{(question.choices ?? []).map((choice) => <label key={choice.id}><input type="radio" name={`${item.id}-${question.name}`} checked={answers[item.id]?.[question.name] === choice.id} onChange={() => setAnswer(item.id, question.name, choice.id)} /> {choice.label}</label>)}</div>;
  const selected = Array.isArray(answers[item.id]?.[question.name]) ? answers[item.id][question.name] as string[] : [];
  return <div className="question-options">{(question.choices ?? []).map((choice) => <label key={choice.id}><input type="checkbox" checked={selected.includes(choice.id)} onChange={(event) => setAnswer(item.id, question.name, event.target.checked ? [...selected, choice.id] : selected.filter((id) => id !== choice.id))} /> {choice.label}</label>)}</div>;
}

function PilotForm({ attempt, onDone }: { attempt: PilotAttempt; onDone: () => Promise<void> }) {
  const items = attempt.items ?? [];
  const [answers, setAnswers] = useState<Record<string, Record<string, unknown>>>(() => Object.fromEntries(items.map((item) => [item.id, item.answers ?? {}])));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const setAnswer = (itemId: string, name: string, value: unknown) => setAnswers((old) => ({ ...old, [itemId]: { ...old[itemId], [name]: value } }));
  const save = async () => api(`/candidate/pilot/attempts/${attempt.id}/answers`, { method: 'PUT', body: JSON.stringify({ answers }) });
  const saveDraft = async () => { setBusy(true); setError(''); try { await save(); } catch (reason) { setError(message(reason)); } finally { setBusy(false); } };
  const submit = async () => { setBusy(true); setError(''); try { await save(); await api(`/candidate/pilot/attempts/${attempt.id}/submit`, { method: 'POST' }); await onDone(); } catch (reason) { setError(message(reason)); } finally { setBusy(false); } };
  return <main className="assessment-page"><div className="assessment-heading"><div><span className="eyebrow">ПИЛОТ · ФОРМА {attempt.form_code}</span><h1>Независимая форма {attempt.sequence} из 2</h1><p>Черновик сохраняет ответы. После отправки результат не показывается, чтобы не повлиять на вторую форму.</p></div><div className="timer-card"><span>До завершения</span><Countdown deadline={attempt.deadline_at} /></div></div><div className="assessment-items">{items.map((item) => <article className="task-card" key={item.id}><div className="task-meta"><span>{String(item.position).padStart(2, '0')}</span><span>{item.family}</span></div><h2>{item.title}</h2><p>{item.scenario}</p>{item.questions.map((question) => <fieldset className="question" key={question.name}><legend>{question.label}</legend><Question item={item} question={question} answers={answers} setAnswer={setAnswer} /></fieldset>)}</article>)}</div>{error && <Notice error>{error}</Notice>}<div className="assessment-actions"><button className="button ghost" disabled={busy} onClick={() => void saveDraft()}>Сохранить черновик</button><button className="button primary" disabled={busy} onClick={() => void submit()}>{busy ? 'Отправляем…' : 'Отправить форму'}</button></div></main>;
}

function PilotWorkspace({ state, refresh }: { state: PilotState; refresh: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const start = async () => { setBusy(true); setError(''); try { await api<PilotAttempt>('/candidate/pilot/attempts', { method: 'POST' }); await refresh(); } catch (reason) { setError(message(reason)); } finally { setBusy(false); } };
  if (state.current_attempt) return <PilotForm attempt={state.current_attempt} onDone={refresh} />;
  const attempts = state.attempts ?? [];
  const expired = attempts.some((attempt) => attempt.status === 'expired');
  const sent = attempts.filter((attempt) => attempt.status === 'awaiting_manual_review' || attempt.status === 'reviewed').length;
  return <main className="assessment-page"><section className="assessment-panel pilot-panel"><span className="eyebrow">КОНТРОЛИРУЕМЫЙ ПИЛОТ</span><h1>{state.specialization} · {state.target_grade}</h1><p className="lead">Ваш код участника: <strong className="participant-code">{state.participant_code}</strong></p><div className="pilot-progress"><span>Порядок: {state.form_order === 'A-first' ? 'сначала A, затем B' : 'сначала B, затем A'}</span><span>Отправлено форм: {sent} из 2</span></div>{!state.manual_review_ready ? <p>Перед началом координатор фиксирует независимую оценку эксперта либо двух рецензентов. Передайте ему только код участника и дождитесь разблокировки.</p> : expired ? <Notice error>Одна из форм истекла. Сообщите код участника координатору: он зафиксирует исключение в отчёте.</Notice> : sent === 2 ? <p>Обе формы получены. Результаты не показываются участнику и будут обработаны оператором вместе с ручной оценкой.</p> : <><p>{sent === 0 ? 'Формы проходят подряд в назначенном порядке. Не обсуждайте задания и ответы с другими участниками.' : 'Первая форма получена. Запустите вторую без просмотра результатов.'}</p><div className="assessment-actions"><button className="button primary" disabled={busy} onClick={() => void start()}>{busy ? 'Открываем…' : sent === 0 ? 'Начать первую форму' : 'Начать вторую форму'}</button></div></>}{error && <Notice error>{error}</Notice>}</section></main>;
}

function PilotPage() {
  const [state, setState] = useState<PilotState | null>(null);
  const [error, setError] = useState('');
  const refresh = useCallback(async () => { setError(''); try { setState(await api<PilotState>('/candidate/pilot')); } catch (reason) { setError(message(reason)); } }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  if (error) return <main className="assessment-page"><Notice error>{error}</Notice></main>;
  if (!state) return <main className="assessment-page"><p>Загружаем пилот…</p></main>;
  return state.enrolled ? <PilotWorkspace state={state} refresh={refresh} /> : <main className="assessment-page"><JoinPilot onJoined={setState} /></main>;
}

export const pilot: FeatureModule = { routes: [{ path: '/candidate/pilot', element: <PilotPage />, roles: ['candidate'] }], navigation: [{ to: '/candidate/pilot', label: 'Пилот A/B', roles: ['candidate'] }] };
