import type { InputHTMLAttributes, ReactNode } from 'react';

type FieldProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  id: string;
  /** Серверная или клиентская ошибка валидации конкретного поля. Если задана, поле подсвечивается красным и под ним выводится сообщение. */
  error?: string;
  /** Подсказка под полем (серая, помогает заполнить). Можно использовать вместо отдельного <p className="hint">. */
  hint?: ReactNode;
};

export function Field({ label, id, error, hint, required, ...props }: FieldProps) {
  const describedBy = [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(' ') || undefined;
  return (
    <label className={`field ${error ? 'field-invalid' : ''} ${required ? 'field-required' : ''}`} htmlFor={id}>
      <span>{label}</span>
      <input
        id={id}
        required={required}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        {...props}
      />
      {hint && !error && <small id={`${id}-hint`} className="field-hint">{hint}</small>}
      {error && <small id={`${id}-error`} className="field-error" role="alert">{error}</small>}
    </label>
  );
}

export function Notice({ children, error = false }: { children: ReactNode; error?: boolean }) {
  return <div className={`notice ${error ? 'notice-error' : ''}`} role={error ? 'alert' : 'status'}>{children}</div>;
}
