interface ViewBottomProps {
  children: React.ReactNode
  className?: string
}

export function ViewBottom({ children, className }: ViewBottomProps) {
  return (
    <div className={`view-bottom${className ? ' ' + className : ''}`}>
      {children}
    </div>
  )
}

interface ActionButtonProps {
  emoji: string
  onClick: () => void
  label: string
  title?: string
}

export function ActionButton({ emoji, onClick, label, title }: ActionButtonProps) {
  return (
    <button
      className="view-action-btn"
      onClick={onClick}
      aria-label={label}
      title={title}
    >
      {emoji}
    </button>
  )
}
