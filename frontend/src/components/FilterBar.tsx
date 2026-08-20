/**
 * FilterBar — barra de filtros com categoria, prioridade e intervalo de datas.
 */

import type { EmailCategory, PriorityLevel, EmailFilters } from '../types/email'

interface FilterBarProps {
  filters: EmailFilters
  onFiltersChange: (filters: EmailFilters) => void
}

const CATEGORIES: { value: EmailCategory; label: string }[] = [
  { value: 'Urgent', label: 'Urgente' },
  { value: 'Personal', label: 'Pessoal' },
  { value: 'Informative', label: 'Informativo' },
  { value: 'Spam', label: 'Spam' },
  { value: 'Promotional', label: 'Promocional' },
  { value: 'Transactional', label: 'Transacional' },
]

const PRIORITIES: { value: PriorityLevel; label: string }[] = [
  { value: 'High', label: 'Alta' },
  { value: 'Medium', label: 'Média' },
  { value: 'Low', label: 'Baixa' },
]

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

  const hasActiveFilters = filters.category || filters.priority || filters.date_from || filters.date_to

  const clearFilters = () => {
    onFiltersChange({})
  }

  return (
    <div className="filter-bar">
      <div className="filter-group">
        <label htmlFor="filter-category">Categoria</label>
        <select
          id="filter-category"
          value={filters.category || ''}
          onChange={handleCategoryChange}
        >
          <option value="">Todas</option>
          {CATEGORIES.map((cat) => (
            <option key={cat.value} value={cat.value}>
              {cat.label}
            </option>
          ))}
        </select>
      </div>

      <div className="filter-group">
        <label htmlFor="filter-priority">Prioridade</label>
        <select
          id="filter-priority"
          value={filters.priority || ''}
          onChange={handlePriorityChange}
        >
          <option value="">Todas</option>
          {PRIORITIES.map((pri) => (
            <option key={pri.value} value={pri.value}>
              {pri.label}
            </option>
          ))}
        </select>
      </div>

      <div className="filter-group">
        <label htmlFor="filter-date-from">De</label>
        <input
          id="filter-date-from"
          type="date"
          value={filters.date_from || ''}
          onChange={handleDateFromChange}
        />
      </div>

      <div className="filter-group">
        <label htmlFor="filter-date-to">Até</label>
        <input
          id="filter-date-to"
          type="date"
          value={filters.date_to || ''}
          onChange={handleDateToChange}
        />
      </div>

      {hasActiveFilters && (
        <div className="filter-group filter-clear">
          <button onClick={clearFilters} className="btn btn-sm btn-outline">
            ✕ Limpar filtros
          </button>
        </div>
      )}
    </div>
  )
}
