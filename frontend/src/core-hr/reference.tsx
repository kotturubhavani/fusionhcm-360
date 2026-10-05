import { useState } from 'react'
import type { FormEvent } from 'react'
import { Badge, Field, Notice, PageTitle, Select } from '../components/ui'
import { resources } from './types'
import type { Reference, References, Resource } from './types'
import type { CoreHrClient } from './api'
export function ReferencePage({
  api,
  refs,
  reload,
}: {
  api: CoreHrClient
  refs: References
  reload: () => Promise<void>
}) {
  const [resource, setResource] = useState<Resource>('legal-employers')
  const [editing, setEditing] = useState<Reference | 'new' | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const row = editing && editing !== 'new' ? editing : undefined
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setNotice('')
    const data = new FormData(event.currentTarget)
    const payload = Object.fromEntries(
      [...data.entries()]
        .filter(([key]) => key !== 'is_active')
        .map(([key, value]) => [
          key,
          value === '' ? null : String(value).trim(),
        ]),
    )
    try {
      await api.saveReference(
        resource,
        { ...payload, is_active: data.get('is_active') === 'on' },
        row?.id,
      )
      setEditing(null)
      await reload()
      setNotice(`${resources[resource]} saved.`)
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'Unable to save reference data.',
      )
    } finally {
      setBusy(false)
    }
  }
  async function toggle(record: Reference) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await api.saveReference(
        resource,
        { is_active: !record.is_active },
        record.id,
      )
      await reload()
      setNotice(
        `${record.name} ${record.is_active ? 'deactivated' : 'activated'}.`,
      )
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : 'Unable to update status.',
      )
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <PageTitle
        title="Reference data"
        description="Maintain the organizations and classifications used by Core HR."
      />
      <div className="panel space-y-5">
        <div className="flex flex-wrap justify-between items-end gap-4">
          <Select
            label="Reference type"
            name="resource"
            value={resource}
            disabled={busy}
            onChange={(event) => {
              setResource(event.target.value as Resource)
              setEditing(null)
              setError('')
              setNotice('')
            }}
          >
            {Object.entries(resources).map(([key, name]) => (
              <option key={key} value={key}>
                {name}
              </option>
            ))}
          </Select>
          <button
            className="primary"
            disabled={busy}
            onClick={() => {
              setEditing('new')
              setError('')
            }}
          >
            Add record
          </button>
        </div>
        {notice && <Notice>{notice}</Notice>}
        {error && <Notice error>{error}</Notice>}
        {editing && (
          <form
            key={`${resource}-${row?.id ?? 'new'}`}
            onSubmit={submit}
            className="rounded-xl border border-teal-200 bg-teal-50/30 p-5"
          >
            <h2>{row ? 'Edit record' : 'Create record'}</h2>
            <fieldset disabled={busy}>
              <div className="form-grid">
                <Field
                  label="Code"
                  name="code"
                  required
                  maxLength={30}
                  value={row?.code}
                />
                <Field
                  label="Name"
                  name="name"
                  required
                  maxLength={150}
                  value={row?.name}
                />
                {(resource === 'legal-employers' ||
                  resource === 'locations') && (
                  <Field
                    label="Country code (2 letters)"
                    name="country_code"
                    required
                    pattern="[A-Za-z]{2}"
                    maxLength={2}
                    value={row?.country_code}
                  />
                )}
                {resource === 'departments' && (
                  <Select
                    label="Business unit"
                    name="business_unit_id"
                    required
                    defaultValue={row?.business_unit_id ?? ''}
                  >
                    <option value="">Select business unit</option>
                    {refs['business-units']
                      .filter(
                        (unit) =>
                          unit.is_active || unit.id === row?.business_unit_id,
                      )
                      .map((unit) => (
                        <option key={unit.id} value={unit.id}>
                          {unit.name}
                        </option>
                      ))}
                  </Select>
                )}
                {(resource === 'jobs' || resource === 'grades') && (
                  <label className="field">
                    Description
                    <textarea
                      name="description"
                      maxLength={10000}
                      defaultValue={row?.description ?? ''}
                    />
                  </label>
                )}
                {resource === 'locations' && (
                  <>
                    <Field
                      label="City"
                      name="city"
                      maxLength={100}
                      value={row?.city ?? ''}
                    />
                    <Field
                      label="Address"
                      name="address_line"
                      maxLength={255}
                      value={row?.address_line ?? ''}
                    />
                  </>
                )}
              </div>
              <label className="my-5 flex gap-2 text-sm">
                <input
                  type="checkbox"
                  name="is_active"
                  defaultChecked={row?.is_active ?? true}
                />
                Active
              </label>
              <div className="actions">
                <button className="primary">
                  {busy ? 'Saving…' : 'Save record'}
                </button>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setEditing(null)}
                >
                  Cancel
                </button>
              </div>
            </fieldset>
          </form>
        )}
        {refs[resource].length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Name</th>
                  <th>Details</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {refs[resource].map((record) => (
                  <tr key={record.id}>
                    <td className="font-medium">{record.code}</td>
                    <td>{record.name}</td>
                    <td>
                      {record.country_code ??
                        record.description ??
                        refs['business-units'].find(
                          (unit) => unit.id === record.business_unit_id,
                        )?.name ??
                        '—'}
                      {record.city && <div>{record.city}</div>}
                      {record.address_line && <div>{record.address_line}</div>}
                    </td>
                    <td>
                      <Badge>{record.is_active ? 'Active' : 'Inactive'}</Badge>
                    </td>
                    <td>
                      <div className="flex gap-4">
                        <button
                          className="link"
                          disabled={busy}
                          onClick={() => {
                            setEditing(record)
                            setError('')
                          }}
                          aria-label={`Edit ${record.name}`}
                        >
                          Edit
                        </button>
                        <button
                          className="link"
                          disabled={busy}
                          onClick={() => toggle(record)}
                          aria-label={`${record.is_active ? 'Deactivate' : 'Activate'} ${record.name}`}
                        >
                          {record.is_active ? 'Deactivate' : 'Activate'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Notice>No records yet. Add a record to get started.</Notice>
        )}
        <p className="hint">
          Deactivation preserves historical records. Records cannot be deleted
          here.
        </p>
      </div>
    </>
  )
}
