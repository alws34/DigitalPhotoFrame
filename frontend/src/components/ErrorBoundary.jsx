import { Component } from 'react';

/**
 * Simple error boundary that catches render-phase errors in its subtree and
 * displays a plain fallback instead of crashing the whole app.
 *
 * Usage:
 *   <ErrorBoundary>
 *     <SomePage />
 *   </ErrorBoundary>
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, message: '' };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, message: error?.message || 'Unknown error' };
  }

  componentDidCatch(error, info) {
    console.error('[ErrorBoundary] Uncaught error:', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '4rem 2rem',
            color: 'var(--text-secondary)',
            textAlign: 'center',
            gap: '1rem',
          }}
        >
          <h2 style={{ color: 'var(--danger)', margin: 0 }}>Something went wrong</h2>
          <p style={{ margin: 0, fontSize: '0.9rem' }}>{this.state.message}</p>
          <button
            onClick={() => this.setState({ hasError: false, message: '' })}
            style={{ marginTop: '0.5rem' }}
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
