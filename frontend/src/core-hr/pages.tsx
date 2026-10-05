import { useLoad } from '../components/useLoad'
import { useState } from 'react'
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom'
import { Badge, Facts, LoadState, Notice, PageTitle } from '../components/ui'
import type { CoreHrClient } from './api'
import type { References, Worker, Placement } from './types'
import { fullName, label, salary, today } from './types'
import { ChangeForm, HirePage } from './forms'
import type { ChangeKind } from './forms'
export function WorkerTable({
  workers,
  refs,
}: {
  workers: Worker[]
  refs: References
}) {
  return workers.length ? (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {[
              'Worker',
              'Legal employer',
              'Department / job',
              'Status',
              'Location',
            ].map((name) => (
              <th key={name}>{name}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {workers.flatMap((worker) =>
            (worker.placements.length ? worker.placements : [null]).map(
              (p, index) => (
                <tr key={`${worker.person.id}-${index}`}>
                  <td>
                    <Link
                      className="link font-semibold"
                      to={`/workers/${worker.person.id}?as_of=${worker.as_of}`}
                    >
                      {fullName(worker.person)}
                    </Link>
                    <div className="text-xs text-slate-500 mt-1">
                      {worker.person.person_number}
                    </div>
                  </td>
                  <td>
                    {refs['legal-employers'].find(
                      (row) =>
                        row.id === p?.work_relationship.legal_employer_id,
                    )?.name ?? '—'}
                  </td>
                  <td>
                    {p?.department?.name ?? '—'}
                    <div className="text-xs text-slate-500 mt-1">
                      {p?.job?.name ?? '—'}
                    </div>
                  </td>
                  <td>
                    <Badge>
                      {p
                        ? label(p.version?.status ?? p.relationship_status)
                        : 'No placement'}
                    </Badge>
                  </td>
                  <td>{p?.location?.name ?? '—'}</td>
                </tr>
              ),
            ),
          )}
        </tbody>
      </table>
    </div>
  ) : (
    <Notice>No workers match this view.</Notice>
  )
}
export function Dashboard({
  api,
  refs,
}: {
  api: CoreHrClient
  refs: References
}) {
  const date = today()
  const result = useLoad(() => api.workers(date), [api, date])
  return (
    <>
      <PageTitle
        title="Workforce overview"
        description={`Core HR · As of ${date}`}
      >
        <Link className="primary" to="/hire">
          Hire worker
        </Link>
      </PageTitle>
      <LoadState {...result} />
      {result.data && (
        <>
          <div className="stats">
            {[
              ['People', result.data.length],
              [
                'Current placements',
                result.data.reduce(
                  (sum, row) => sum + row.placements.length,
                  0,
                ),
              ],
              ['Departments', refs.departments.length],
              ['Jobs', refs.jobs.length],
              ['Locations', refs.locations.length],
              ['Legal employers', refs['legal-employers'].length],
            ].map(([name, count]) => (
              <section className="panel" key={name}>
                <p className="text-sm text-slate-500">{name}</p>
                <p className="mt-2 text-3xl font-semibold tracking-tight">
                  {count}
                </p>
              </section>
            ))}
          </div>
          <p className="hint">
            Counts include all fetched records. Reference counts include
            inactive records; placements reflect the selected date.
          </p>
          <section className="panel">
            <div className="flex items-center justify-between gap-3">
              <h2>Workforce at a glance</h2>
              <Link className="link text-sm" to="/workers">
                View all workers
              </Link>
            </div>
            <WorkerTable workers={result.data.slice(0, 5)} refs={refs} />
          </section>
        </>
      )}
    </>
  )
}
export function Directory({
  api,
  refs,
}: {
  api: CoreHrClient
  refs: References
}) {
  const [date, setDate] = useState(today())
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const result = useLoad(() => api.workers(date), [api, date])
  const filtered = result.data?.filter((worker) => {
    const haystack = [
      fullName(worker.person),
      worker.person.person_number,
      ...worker.placements.flatMap((p) => [
        p.department?.name,
        p.job?.name,
        p.location?.name,
        refs['legal-employers'].find(
          (r) => r.id === p.work_relationship.legal_employer_id,
        )?.name,
      ]),
    ]
      .join(' ')
      .toLowerCase()
    return (
      haystack.includes(query.toLowerCase()) &&
      (!status ||
        (status === 'NONE'
          ? !worker.placements.length
          : worker.placements.some((p) => p.version?.status === status)))
    )
  })
  return (
    <>
      <PageTitle
        title="Workers"
        description="Browse people and their employment assignments."
      >
        <Link className="primary" to="/hire">
          Hire worker
        </Link>
      </PageTitle>
      <section className="panel">
        <div className="form-grid mb-5">
          <label className="field">
            Search workers
            <input
              type="search"
              placeholder="Name, person number or organization"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <label className="field">
            As-of date
            <input
              type="date"
              required
              value={date}
              onInput={(e) => {
                if (e.currentTarget.value) setDate(e.currentTarget.value)
              }}
            />
          </label>
          <label className="field">
            Assignment status
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All statuses</option>
              {['ACTIVE', 'ON_LEAVE', 'SUSPENDED', 'NONE'].map((value) => (
                <option key={value} value={value}>
                  {value === 'NONE' ? 'No placement' : label(value)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <LoadState {...result} />
        {filtered && (
          <>
            <p className="hint">
              {filtered.length} of {result.data?.length} people · Search applies
              to the loaded directory.
            </p>
            <WorkerTable workers={filtered} refs={refs} />
          </>
        )}
      </section>
    </>
  )
}
export function PlacementDetails({
  placement: p,
  refs,
}: {
  placement: Placement
  refs?: References
}) {
  return (
    <>
      <Facts
        items={[
          [
            'Legal employer',
            refs?.['legal-employers'].find(
              (row) => row.id === p.work_relationship.legal_employer_id,
            )?.name ?? 'Not provided in this view',
          ],
          ['Employment type', label(p.work_relationship.employment_type)],
          ['Joining date', p.work_relationship.start_date],
          ['Employment end date', p.work_relationship.end_date ?? 'Open ended'],
          ['Assignment number', p.assignment.assignment_number],
          [
            'Assignment dates',
            `${p.assignment.start_date} to ${p.assignment.end_date ?? 'open ended'}`,
          ],
          ['Business unit', p.business_unit?.name],
          ['Department', p.department?.name],
          ['Job', p.job?.name],
          ['Grade', p.grade?.name],
          ['Location', p.location?.name],
          [
            'Manager',
            p.manager
              ? fullName(p.manager)
              : p.version?.manager_assignment_id
                ? 'Manager details are not available in this view'
                : 'No manager assigned',
          ],
          ['Work time', label(p.version?.work_time_type)],
          ['Assignment status', label(p.version?.status)],
          [
            'Assignment version dates',
            p.version
              ? `${p.version.effective_from} to ${p.version.effective_to ?? 'open ended'}`
              : 'Not available',
          ],
          [
            'Annual base salary',
            p.compensation
              ? salary(
                  p.compensation.annual_base_salary,
                  p.compensation.currency,
                )
              : 'Not available',
          ],
          [
            'Compensation dates',
            p.compensation
              ? `${p.compensation.effective_from} to ${p.compensation.effective_to ?? 'open ended'}`
              : 'Not available',
          ],
        ]}
      />
    </>
  )
}
export function WorkerDetail({
  api,
  refs,
  self = false,
}: {
  api: CoreHrClient
  refs?: References
  self?: boolean
}) {
  const { personId } = useParams()
  const [params, setParams] = useSearchParams()
  const initial = params.get('as_of')
  const date =
    initial && /^\d{4}-\d{2}-\d{2}$/.test(initial) ? initial : today()
  const location = useLocation()
  const [notice, setNotice] = useState(
    (location.state as { notice?: string } | null)?.notice ?? '',
  )
  const [action, setAction] = useState<{
    kind: ChangeKind
    placement: Placement
  } | null>(null)
  const [rehire, setRehire] = useState(false)
  const result = useLoad(async () => {
    const [worker, relationships] = await Promise.all([
      api.worker(self ? undefined : personId, date),
      !self && personId ? api.relationships(personId) : Promise.resolve([]),
    ])
    return { worker, relationships }
  }, [api, personId, date, self])
  function changeDate(next: string) {
    setParams({ as_of: next })
    setAction(null)
    setRehire(false)
    setNotice('')
  }
  function saved(next: string) {
    setAction(null)
    setRehire(false)
    setNotice('Change saved successfully.')
    setParams({ as_of: next })
    result.reload()
  }
  const person = result.data?.worker.person
  const canRehire =
    !self &&
    result.data &&
    !result.data.relationships.some((r) => !r.end_date || r.end_date >= today())
  if (rehire && refs && person)
    return (
      <HirePage
        api={api}
        refs={refs}
        personId={person.id}
        personName={fullName(person)}
        onDone={saved}
        onCancel={() => setRehire(false)}
      />
    )
  return (
    <>
      <PageTitle
        title={
          self ? 'My employment' : person ? fullName(person) : 'Worker details'
        }
        description={
          self
            ? 'Your personal and employment information.'
            : person?.person_number
        }
      >
        <label className="field">
          As-of date
          <input
            aria-label="As-of date"
            type="date"
            value={date}
            onInput={(e) => {
              if (e.currentTarget.value) changeDate(e.currentTarget.value)
            }}
          />
        </label>
        {canRehire && (
          <button className="primary self-end" onClick={() => setRehire(true)}>
            Rehire worker
          </button>
        )}
      </PageTitle>
      {!self && (
        <Link className="link text-sm" to="/workers">
          Back to workers
        </Link>
      )}
      {notice && <Notice>{notice}</Notice>}
      <LoadState {...result} />
      {result.data && person && (
        <div className="space-y-6 mt-5">
          <section className="panel">
            <div className="flex justify-between gap-3">
              <h2>Personal information</h2>
              <Badge>
                {person.is_active
                  ? 'Active person record'
                  : 'Inactive person record'}
              </Badge>
            </div>
            <Facts
              items={[
                ['Full name', fullName(person)],
                ['Person number', person.person_number],
                ['Preferred name', person.preferred_name],
                ['Personal email', person.personal_email],
                ['Phone', person.phone],
                ['Date of birth', person.date_of_birth],
              ]}
            />
          </section>
          {action && refs && (
            <ChangeForm
              key={`${action.kind}-${action.placement.assignment.id}`}
              api={api}
              refs={refs}
              personId={person.id}
              kind={action.kind}
              placement={action.placement}
              onDone={saved}
              onCancel={() => setAction(null)}
            />
          )}
          {result.data.worker.placements.length === 0 && (
            <Notice>
              No employment placement on {date}. Choose a date within an
              employment period to view assignment and compensation details.
            </Notice>
          )}
          {result.data.worker.placements.map((p) => (
            <section className="panel" key={p.assignment.id}>
              <div className="flex flex-wrap justify-between gap-3">
                <h2>Assignment · {p.assignment.assignment_number}</h2>
                <Badge>
                  {label(p.version?.status ?? p.relationship_status)}
                </Badge>
              </div>
              <PlacementDetails placement={p} refs={refs} />
              {!self &&
                !action &&
                !p.work_relationship.termination_reason &&
                (!p.work_relationship.end_date ||
                  p.work_relationship.end_date >= today()) && (
                  <div className="actions mt-5">
                    {(
                      [
                        'assignment',
                        'compensation',
                        'terminate',
                      ] as ChangeKind[]
                    ).map((kind) => (
                      <button
                        key={kind}
                        className={
                          kind === 'terminate' ? 'danger-outline' : 'secondary'
                        }
                        onClick={() => setAction({ kind, placement: p })}
                      >
                        {kind === 'assignment'
                          ? 'Change assignment'
                          : kind === 'compensation'
                            ? 'Change compensation'
                            : 'Terminate employment'}
                      </button>
                    ))}
                  </div>
                )}
            </section>
          ))}
          {!self && (
            <section className="panel">
              <h2>Employment episodes</h2>
              {result.data.relationships.length ? (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Legal employer</th>
                        <th>Type</th>
                        <th>Start date</th>
                        <th>End date</th>
                        <th>Reason</th>
                        <th>History</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.data.relationships.map((r) => (
                        <tr key={r.id}>
                          <td>
                            {refs?.['legal-employers'].find(
                              (row) => row.id === r.legal_employer_id,
                            )?.name ?? 'Not provided'}
                          </td>
                          <td>{label(r.employment_type)}</td>
                          <td>{r.start_date}</td>
                          <td>{r.end_date ?? 'Open ended'}</td>
                          <td>{r.termination_reason ?? '—'}</td>
                          <td>
                            <button
                              className="link"
                              onClick={() => changeDate(r.start_date)}
                            >
                              View at start
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="hint">No employment relationships recorded.</p>
              )}
              <p className="hint">
                As-of dates select employment history. Personal information and
                organization names show their current values.
              </p>
            </section>
          )}
        </div>
      )}
    </>
  )
}
