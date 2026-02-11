import { Link } from 'react-router-dom'

export function Footer() {
  return (
    <footer style={{
      marginTop: 'var(--space-16)',
      paddingTop: 'var(--space-4)',
      borderTop: '1px solid var(--border)',
      fontSize: 'var(--text-xs)',
      color: 'var(--muted)',
      textAlign: 'center',
      paddingBottom: 'var(--space-8)',
    }}>
      <a href="https://github.com/LAEH/MADphotos" style={{ color: 'var(--muted)', textDecoration: 'none' }}>
        LAEH/MADphotos
      </a>
      {' \u00B7 '}
      <Link to="/dashboard" style={{ color: 'var(--muted)', textDecoration: 'none' }}>State</Link>
      {' \u00B7 '}
      <Link to="/journal" style={{ color: 'var(--muted)', textDecoration: 'none' }}>Journal</Link>
    </footer>
  )
}
