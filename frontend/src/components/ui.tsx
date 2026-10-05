import type { ReactNode } from 'react'
export function Notice({
  children,
  error = false,
}: {
  children: ReactNode
  error?: boolean
}) {
  return (
    <div
      role={error ? 'alert' : 'status'}
      className={error ? 'notice error' : 'notice'}
    >
      {children}
    </div>
  )
}
export function LoadState({
  busy,
  error,
  reload,
}: {
  busy: boolean
  error: string
  reload: () => void
}) {
  return busy ? (
    <Notice>Loading…</Notice>
  ) : error ? (
    <Notice error>
      {error}{' '}
      <button className="link" onClick={reload}>
        Try again
      </button>
    </Notice>
  ) : null
}
export function PageTitle({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children?: ReactNode
}) {
  return (
    <div className="page-title">
      <div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  )
}
export function Badge({ children }: { children: ReactNode }) {
  return <span className="badge">{children}</span>
}
export function Field({
  label,
  name,
  type = 'text',
  required = false,
  value,
  ...props
}: {
  label: string
  name: string
  type?: string
  required?: boolean
  value?: string
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, 'value'>) {
  return (
    <label className="field">
      {label}
      {required && ' *'}
      <input
        name={name}
        type={type}
        required={required}
        defaultValue={value}
        {...props}
      />
    </label>
  )
}
export function Select({
  label,
  name,
  children,
  ...props
}: {
  label: string
  name: string
  children: ReactNode
} & React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <label className="field">
      {label}
      {props.required && ' *'}
      <select name={name} {...props}>
        {children}
      </select>
    </label>
  )
}
export function Facts({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="facts">
      {items.map(([key, value]) => (
        <div key={key}>
          <dt>{key}</dt>
          <dd>{value || 'Not provided'}</dd>
        </div>
      ))}
    </dl>
  )
}
