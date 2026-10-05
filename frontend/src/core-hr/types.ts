export type EmploymentType = 'REGULAR' | 'FIXED_TERM' | 'INTERN'
export type AssignmentStatus = 'ACTIVE' | 'ON_LEAVE' | 'SUSPENDED'
export type WorkTime = 'FULL_TIME' | 'PART_TIME'
export interface Reference {
  id: string
  code: string
  name: string
  is_active: boolean
  country_code?: string
  business_unit_id?: string
  description?: string | null
  city?: string | null
  address_line?: string | null
}
export const resources = {
  'legal-employers': 'Legal employers',
  'business-units': 'Business units',
  departments: 'Departments',
  jobs: 'Jobs',
  grades: 'Grades',
  locations: 'Locations',
} as const
export type Resource = keyof typeof resources
export type References = Record<Resource, Reference[]>
export interface Person {
  id: string
  person_number: string
  first_name: string
  last_name: string
  preferred_name: string | null
  personal_email: string | null
  phone: string | null
  date_of_birth: string | null
  is_active: boolean
}
export interface Relationship {
  id: string
  person_id: string
  legal_employer_id: string
  employment_type: EmploymentType
  start_date: string
  end_date: string | null
  termination_reason: string | null
}
export interface Assignment {
  id: string
  assignment_number: string
  work_relationship_id: string
  start_date: string
  end_date: string | null
}
export interface VersionDetails {
  business_unit_id: string
  department_id: string
  job_id: string
  grade_id: string | null
  location_id: string
  manager_assignment_id: string | null
  status: AssignmentStatus
  work_time_type: WorkTime
}
export interface Version extends VersionDetails {
  id: string
  assignment_id: string
  effective_from: string
  effective_to: string | null
}
export interface Compensation {
  effective_from: string
  effective_to: string | null
  annual_base_salary: string
  currency: string
}
export interface Placement {
  work_relationship: Relationship
  relationship_status: string
  assignment: Assignment
  version: Version | null
  compensation: Compensation | null
  business_unit: Reference | null
  department: Reference | null
  job: Reference | null
  grade: Reference | null
  location: Reference | null
  manager: Person | null
  manager_assignment: Assignment | null
}
export interface Worker {
  person: Person
  as_of: string
  placements: Placement[]
}
export interface HireResult {
  person: Person
  work_relationship: Relationship
  assignment: Assignment
  version: Version
  compensation: Compensation
}
export const fullName = (person: Person) =>
  `${person.first_name} ${person.last_name}`
export const today = () => {
  const date = new Date()
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
export const label = (value?: string | null) =>
  value
    ? value
        .toLowerCase()
        .replaceAll('_', ' ')
        .replace(/^./, (c) => c.toUpperCase())
    : 'Not provided'
// Format the decimal text without conversion to a floating-point number.
export const salary = (amount: string, currency: string) =>
  `${currency} ${amount.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}`
