import { Footer } from './Footer'

interface PageShellProps {
  title: string
  subtitle?: React.ReactNode
  children: React.ReactNode
}

export function PageShell({ title, subtitle, children }: PageShellProps) {
  return (
    <>
      <div className="page-header">
        <h1 className="page-title">{title}</h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
      </div>
      <div className="page-body">
        {children}
      </div>
      <Footer />
    </>
  )
}
