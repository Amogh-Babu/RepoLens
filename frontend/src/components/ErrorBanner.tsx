import type {ReactNode} from 'react';
import type {ErrorDescription} from '../api/describeError.ts';
import './ErrorBanner.css';

interface ErrorBannerProps {
  error: ErrorDescription;
  /** Shown as a Retry button when the error is retryable. */
  onRetry?: () => void;
  onDismiss?: () => void;
  /** Extra actions, such as "Analyze the default branch". */
  children?: ReactNode;
}

/** Shows the title, message and hint of an error, with actions. */
export function ErrorBanner({
  error,
  onRetry,
  onDismiss,
  children,
}: ErrorBannerProps) {
  const showRetry = error.retryable && onRetry !== undefined;
  return (
    <div className="error-banner" role="alert">
      <p className="error-banner__title">{error.title}</p>
      <p className="error-banner__message">{error.message}</p>
      {error.hint && <p className="error-banner__hint">{error.hint}</p>}
      {(showRetry || children || onDismiss) && (
        <div className="error-banner__actions">
          {showRetry && (
            <button type="button" className="button" onClick={onRetry}>
              Retry
            </button>
          )}
          {children}
          {onDismiss && (
            <button
              type="button"
              className="button button--quiet"
              onClick={onDismiss}
            >
              Dismiss
            </button>
          )}
        </div>
      )}
    </div>
  );
}
