import { titleCase } from '../../lib/utils'

interface GlassTagProps {
  text: string
  category?: string
  active?: boolean
  color?: string
  onClick?: (text: string) => void
}

export function GlassTag({ text, category, active, color, onClick }: GlassTagProps) {
  const classNames = [
    'glass-tag',
    category ? 'tag-' + category : '',
    active ? 'active' : '',
  ]
    .filter(Boolean)
    .join(' ')

  const handleClick = onClick
    ? (e: React.MouseEvent) => {
        e.stopPropagation()
        onClick(text)
      }
    : undefined

  return (
    <span className={classNames} onClick={handleClick}>
      {color && (
        <span className="dot" style={{ background: color }} />
      )}
      {titleCase(text)}
    </span>
  )
}
