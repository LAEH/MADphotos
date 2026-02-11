interface CardProps {
  title?: string
  children: React.ReactNode
  className?: string
}

export function Card({ title, children, className }: CardProps) {
  return (
    <div className={`sys-card${className ? ' ' + className : ''}`}>
      {title && <div className="sys-card-title">{title}</div>}
      {children}
    </div>
  )
}
