import type { AssignmentStatus, EmploymentType, WorkTime } from './types'
const text = (data: FormData, name: string) =>
  String(data.get(name) ?? '').trim()
const optional = (data: FormData, name: string) => text(data, name) || null
export function versionPayload(data: FormData) {
  return {
    business_unit_id: text(data, 'business_unit_id'),
    department_id: text(data, 'department_id'),
    job_id: text(data, 'job_id'),
    grade_id: optional(data, 'grade_id'),
    location_id: text(data, 'location_id'),
    manager_assignment_id: optional(data, 'manager_assignment_id'),
    status: text(data, 'status') as AssignmentStatus,
    work_time_type: text(data, 'work_time_type') as WorkTime,
  }
}
export function compensationPayload(data: FormData) {
  const amount = text(data, 'annual_base_salary')
  if (!/^\d{1,12}(\.\d{1,2})?$/.test(amount))
    throw new Error(
      'Annual base salary must be a non-negative decimal with up to 12 whole digits and 2 decimal places.',
    )
  return {
    effective_from: text(data, 'effective_from'),
    annual_base_salary: amount,
    currency: text(data, 'currency').toUpperCase(),
  }
}
export function hirePayload(data: FormData, rehire = false) {
  const { annual_base_salary, currency } = compensationPayload(data)
  return {
    ...versionPayload(data),
    legal_employer_id: text(data, 'legal_employer_id'),
    employment_type: text(data, 'employment_type') as EmploymentType,
    joining_date: text(data, 'joining_date'),
    end_date: optional(data, 'end_date'),
    assignment_number: text(data, 'assignment_number'),
    annual_base_salary,
    currency,
    ...(!rehire
      ? {
          person: {
            person_number: text(data, 'person_number'),
            first_name: text(data, 'first_name'),
            last_name: text(data, 'last_name'),
            preferred_name: optional(data, 'preferred_name'),
            personal_email: optional(data, 'personal_email'),
            date_of_birth: optional(data, 'date_of_birth'),
            phone: optional(data, 'phone'),
          },
        }
      : {}),
  }
}
