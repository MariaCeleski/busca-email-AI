/**
 * Filter bar component with category, priority, and date range filters.
 */

import type { EmailCategory, PriorityLevel, EmailFilters } from '../types/email'

interface FilterBarProps {
  filters: EmailFilters
  onFiltersChange: (filters: EmailFilters) => void
}

const CATEGORIES: EmailCategory[] = [
  'Urgent',
  'Personal',
  'Informative',
  'Spam',
  'Promotional',
  'Transactional',
]

const PRIORITIES: PriorityLevel[] = ['High', 'Medium', 'Low']

export function FilterBar({ filters, onFiltersChange }: FilterBarProps) {
  const handleCategoryChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value as EmailCategory | ''
    onFiltersChange({ ...filters, category: value || undefined })
  }

  const handlePriorityChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value as PriorityLevel | ''
    onFiltersChange({ ...filters, priority: value || undefined })
  }

  const handleDateFromChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onFiltersChange({ ...filters, date_from: e.target.value || undefined })
  }

  const handleDateToChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onFiltersChange({ ...filters, date_to: e.target.value || undefined })
  }

  return (
    <div className="filter-bar">
      <div className="filter-group">
        <label htmlFor="filter-category">Category</label>
        <select
          id="filter-category"
          value={filters.category || ''}
          onChange={handleCategoryChange}
        >
          <option value="">All Categories</option>
          {CATEGORIES.map((cat) => (
            <option key={cat} value={cat}>
              {cat}
            </option>
          ))}
        </select>
      </div>

      <div className="filter-group">
        <label htmlFor="filter-priority">Priority</label>
        <select
          id="filter-priority"
          value={filters.priority || ''}
          onChange={handlePriorityChange}
        >
          <option value="">All Priorities</option>
          {PRIORITIES.map((pri) => (
            <option key={pri} value={pri}>
              {pri}
            </option>
          ))}
        </select>
      </div>

      <div className="filter-group">
        <label htmlFor="filter-date-from">From</label>
        <input
          id="filter-date-from"
          type="date"
          value={filters.date_from || ''}
          onChange={handleDateFromChange}
        />
      </div>

      <div className="filter-group">
        <label htmlFor="filter-date-to">To</label>
        <input
          id="filter-date-to"
          type="date"
          value={filters.date_to || ''}
          onChange={handleDateToChange}
        />
      </div>
    </div>
  )
}
