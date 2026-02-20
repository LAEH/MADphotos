import { Component } from 'react'
import type { ReactNode, ErrorInfo } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  private handleRetry = () => {
    this.setState({ hasError: false })
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback
      return (
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          justifyContent: 'center', height: '100vh', gap: 16,
          color: 'var(--text-muted, #888)', fontFamily: 'system-ui',
        }}>
          <p>Something went wrong.</p>
          <button
            onClick={this.handleRetry}
            style={{
              padding: '8px 20px', border: '1px solid currentColor',
              borderRadius: 8, background: 'none', color: 'inherit',
              cursor: 'pointer', fontSize: 14,
            }}
          >
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
