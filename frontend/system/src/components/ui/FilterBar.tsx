interface Props {
  items: { key: string; label: string; count?: number }[]
  active: string
  onSelect: (key: string) => void
}

export function FilterBar({ items, active, onSelect }: Props) {
  return (
    <div className="filter-bar">
      {items.map(item => (
        <button
          key={item.key}
          className={`filter-btn${active === item.key ? ' active' : ''}`}
          onClick={() => onSelect(item.key)}
        >
          {item.label}{item.count != null ? ` (${item.count})` : ''}
        </button>
      ))}
    </div>
  )
}
