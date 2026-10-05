import { useLoad } from '../components/useLoad'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Field, Select, Notice, LoadState, PageTitle } from '../components/ui'
import { fullName, label, today } from './types'
import type { References, Reference, Version, Worker, Placement } from './types'
import type { CoreHrClient } from './api'
import { compensationPayload, hirePayload, versionPayload } from './payloads'
function Options({
  rows,
  selected,
}: {
  rows: Reference[]
  selected?: string | null
}) {
  return (
    <>
      {rows
        .filter((row) => row.is_active || row.id === selected)
        .map((row) => (
          <option key={row.id} value={row.id}>
            {row.name}
            {!row.is_active && ' (inactive)'}
          </option>
        ))}
    </>
  )
}
export function OrganizationFields({
  refs,
  workers,
  initial,
  excludePerson,
}: {
  refs: References
  workers: Worker[]
  initial?: Version | null
  excludePerson?: string
}) {
  const [unit, setUnit] = useState(initial?.business_unit_id ?? '')
  const [department, setDepartment] = useState(initial?.department_id ?? '')
  return (
    <div className="form-grid">
      <Select
        label="Business unit"
        name="business_unit_id"
        required
        value={unit}
        onChange={(event) => {
          setUnit(event.target.value)
          setDepartment('')
        }}
      >
        <option value="">Select business unit</option>
        <Options rows={refs['business-units']} selected={unit} />
      </Select>
      <Select
        label="Department"
        name="department_id"
        required
        value={department}
        onChange={(event) => setDepartment(event.target.value)}
      >
        <option value="">Select department</option>
        <Options
          rows={refs.departments.filter((row) => row.business_unit_id === unit)}
          selected={department}
        />
      </Select>
      <Select
        label="Job"
        name="job_id"
        required
        defaultValue={initial?.job_id ?? ''}
      >
        <option value="">Select job</option>
        <Options rows={refs.jobs} selected={initial?.job_id} />
      </Select>
      <Select
        label="Grade"
        name="grade_id"
        defaultValue={initial?.grade_id ?? ''}
      >
        <option value="">No grade</option>
        <Options rows={refs.grades} selected={initial?.grade_id} />
      </Select>
      <Select
        label="Location"
        name="location_id"
        required
        defaultValue={initial?.location_id ?? ''}
      >
        <option value="">Select location</option>
        <Options rows={refs.locations} selected={initial?.location_id} />
      </Select>
      <Select
        label="Manager assignment"
        name="manager_assignment_id"
        defaultValue={initial?.manager_assignment_id ?? ''}
      >
        <option value="">No manager</option>
        {workers
          .filter((worker) => worker.person.id !== excludePerson)
          .flatMap((worker) =>
            worker.placements
              .filter(
                (p) =>
                  p.version?.status === 'ACTIVE' ||
                  p.assignment.id === initial?.manager_assignment_id,
              )
              .map((p) => (
                <option key={p.assignment.id} value={p.assignment.id}>
                  {fullName(worker.person)} · {p.assignment.assignment_number}
                </option>
              )),
          )}
      </Select>
      <Select
        label="Assignment status"
        name="status"
        required
        defaultValue={initial?.status ?? 'ACTIVE'}
      >
        {['ACTIVE', 'ON_LEAVE', 'SUSPENDED'].map((value) => (
          <option key={value} value={value}>
            {label(value)}
          </option>
        ))}
      </Select>
      <Select
        label="Work time"
        name="work_time_type"
        required
        defaultValue={initial?.work_time_type ?? 'FULL_TIME'}
      >
        <option value="FULL_TIME">Full time</option>
        <option value="PART_TIME">Part time</option>
      </Select>
    </div>
  )
}
function SalaryFields({
  amount = '',
  currency = '',
}: {
  amount?: string
  currency?: string
}) {
  return (
    <>
      <Field
        label="Annual base salary"
        name="annual_base_salary"
        required
        value={amount}
        inputMode="decimal"
        pattern="[0-9]{1,12}(\.[0-9]{1,2})?"
        placeholder="750000.00"
      />
      <Field
        label="Currency (3 letters)"
        name="currency"
        required
        value={currency}
        pattern="[A-Za-z]{3}"
        maxLength={3}
        placeholder="INR"
      />
    </>
  )
}
export function HirePage({
  api,
  refs,
  personId,
  personName,
  onDone,
  onCancel,
}: {
  api: CoreHrClient
  refs: References
  personId?: string
  personName?: string
  onDone?: (date: string) => void
  onCancel?: () => void
}) {
  const navigate = useNavigate()
  const [date, setDate] = useState(today())
  const candidates = useLoad(() => api.workers(date), [api, date])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const payload = hirePayload(new FormData(event.currentTarget), !!personId)
      const result = await api.hire(payload, personId)
      if (onDone) onDone(payload.joining_date)
      else
        navigate(`/workers/${result.person.id}?as_of=${payload.joining_date}`, {
          state: { notice: 'Worker hired successfully.' },
        })
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : 'Unable to hire worker.',
      )
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <PageTitle
        title={personId ? `Rehire ${personName}` : 'Hire worker'}
        description="Create an employment relationship, assignment and initial compensation. Required fields are marked *."
      />
      <form className="panel space-y-6" onSubmit={submit}>
        <fieldset disabled={busy} className="space-y-6">
          {!personId && (
            <section>
              <h2>Personal information</h2>
              <div className="form-grid">
                <Field
                  label="Person number"
                  name="person_number"
                  required
                  maxLength={30}
                />
                <Field
                  label="First name"
                  name="first_name"
                  required
                  maxLength={100}
                />
                <Field
                  label="Last name"
                  name="last_name"
                  required
                  maxLength={100}
                />
                <Field
                  label="Preferred name"
                  name="preferred_name"
                  maxLength={100}
                />
                <Field
                  label="Personal email"
                  name="personal_email"
                  type="email"
                />
                <Field label="Phone" name="phone" maxLength={30} />
                <Field
                  label="Date of birth"
                  name="date_of_birth"
                  type="date"
                  max={today()}
                />
              </div>
              <p className="hint">
                Person numbers are permanent and retained on rehire.
              </p>
            </section>
          )}
          <section>
            <h2>Employment</h2>
            <div className="form-grid">
              <Select
                label="Legal employer"
                name="legal_employer_id"
                required
                defaultValue=""
              >
                <option value="">Select legal employer</option>
                <Options rows={refs['legal-employers']} />
              </Select>
              <Select
                label="Employment type"
                name="employment_type"
                defaultValue="REGULAR"
              >
                {['REGULAR', 'FIXED_TERM', 'INTERN'].map((value) => (
                  <option key={value} value={value}>
                    {label(value)}
                  </option>
                ))}
              </Select>
              <Field
                label="Joining date"
                name="joining_date"
                type="date"
                required
                value={date}
                onInput={(event) => {
                  if (event.currentTarget.value)
                    setDate(event.currentTarget.value)
                }}
              />
              <Field
                label="Planned end date"
                name="end_date"
                type="date"
                min={date}
              />
              <Field
                label="Assignment number"
                name="assignment_number"
                required
                maxLength={30}
              />
            </div>
          </section>
          <section>
            <h2>Assignment</h2>
            <LoadState {...candidates} />
            {candidates.data && (
              <OrganizationFields
                key={date}
                refs={refs}
                workers={candidates.data}
                excludePerson={personId}
              />
            )}
            <p className="hint">
              Manager choices reflect the joining date. Eligibility is checked
              when saved.
            </p>
          </section>
          <section>
            <h2>Initial compensation</h2>
            <div className="form-grid">
              <SalaryFields />
            </div>
          </section>
          {error && <Notice error>{error}</Notice>}
          <div className="actions">
            <button className="primary" disabled={busy || !candidates.data}>
              {busy ? 'Saving…' : personId ? 'Rehire worker' : 'Hire worker'}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => (onCancel ? onCancel() : navigate('/workers'))}
            >
              Cancel
            </button>
          </div>
        </fieldset>
      </form>
    </>
  )
}
export type ChangeKind = 'assignment' | 'compensation' | 'terminate'
export function ChangeForm({
  api,
  refs,
  placement,
  personId,
  kind,
  onDone,
  onCancel,
}: {
  api: CoreHrClient
  refs: References
  placement: Placement
  personId: string
  kind: ChangeKind
  onDone: (date: string) => void
  onCancel: () => void
}) {
  const [date, setDate] = useState(today())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const candidates = useLoad(
    () =>
      kind === 'assignment'
        ? api.workers(date)
        : Promise.resolve([] as Worker[]),
    [api, date, kind],
  )
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    const data = new FormData(event.currentTarget)
    const submittedDate = String(data.get('effective_from'))
    try {
      const path =
        kind === 'terminate'
          ? `/work-relationships/${placement.work_relationship.id}/terminate`
          : `/assignments/${placement.assignment.id}/${kind === 'assignment' ? 'changes' : 'compensation'}`
      const payload =
        kind === 'assignment'
          ? { ...versionPayload(data), effective_from: submittedDate }
          : kind === 'compensation'
            ? compensationPayload(data)
            : {
                end_date: submittedDate,
                reason: String(data.get('reason') ?? '').trim() || null,
              }
      await api.request(path, 'POST', payload)
      onDone(submittedDate)
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : 'Unable to save change.',
      )
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="panel border-teal-300" aria-label="Employment change">
      <h2>
        {kind === 'assignment'
          ? 'Change assignment'
          : kind === 'compensation'
            ? 'Change compensation'
            : 'Terminate employment'}
      </h2>
      <p className="hint">
        {kind === 'terminate'
          ? 'This ends the employment relationship and its assignments. History is retained. The end date is inclusive.'
          : 'A new dated record is added. Choose a date after the latest recorded change; the backend validates the full history.'}
      </p>
      <form onSubmit={submit}>
        <fieldset disabled={busy} className="space-y-5">
          <div className="form-grid">
            <Field
              label={kind === 'terminate' ? 'End date' : 'Effective date'}
              name="effective_from"
              type="date"
              required
              value={date}
              min={placement.assignment.start_date}
              onInput={(event) => {
                if (event.currentTarget.value)
                  setDate(event.currentTarget.value)
              }}
            />
            {kind === 'compensation' && (
              <SalaryFields
                amount={placement.compensation?.annual_base_salary}
                currency={placement.compensation?.currency}
              />
            )}
            {kind === 'terminate' && (
              <Field label="Termination reason" name="reason" maxLength={255} />
            )}
          </div>
          {kind === 'assignment' && (
            <>
              <LoadState {...candidates} />
              {candidates.data && (
                <OrganizationFields
                  key={date}
                  refs={refs}
                  workers={candidates.data}
                  initial={placement.version}
                  excludePerson={personId}
                />
              )}
            </>
          )}
          {kind === 'terminate' && (
            <label className="flex items-start gap-3 text-sm">
              <input type="checkbox" required className="mt-1" />I confirm that
              this employment relationship and its assignments should end on the
              selected date.
            </label>
          )}
          {error && <Notice error>{error}</Notice>}
          <div className="actions">
            <button
              className={kind === 'terminate' ? 'danger' : 'primary'}
              disabled={busy || (kind === 'assignment' && !candidates.data)}
            >
              {busy ? 'Saving…' : 'Confirm change'}
            </button>
            <button type="button" className="secondary" onClick={onCancel}>
              Cancel
            </button>
          </div>
        </fieldset>
      </form>
    </section>
  )
}
