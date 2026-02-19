import { Footer } from './Footer'

interface PageShellProps {
  title: string
  subtitle?: React.ReactNode
  children: React.ReactNode
  hideFooter?: boolean
}

export function PageShell({ title, subtitle, children, hideFooter }: PageShellProps) {
  return (
    <>
      <div className="page-header">
        <h1 className="page-title">{title}</h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
      </div>
      <div className="page-body">
        {children}
      </div>
      {!hideFooter && <Footer />}
    </>
  )
}
