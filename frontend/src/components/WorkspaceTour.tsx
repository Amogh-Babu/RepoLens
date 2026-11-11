import type {ReactNode} from 'react';
import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import './WorkspaceTour.css';

/** One stop on the tour: the area it points at and what to say there. */
export interface TourStep {
  /** `data-tour` value of the element to point at; null for a centered card. */
  target: string | null;
  title: string;
  body: ReactNode;
}

interface WorkspaceTourProps {
  steps: readonly TourStep[];
  /** Called when the tour is finished, skipped or closed with Escape. */
  onClose: () => void;
}

interface Box {
  top: number;
  left: number;
  width: number;
  height: number;
}

const GAP = 12;
const CARD_WIDTH = 340;
const MARGIN = 16;

/**
 * A short walkthrough of the workspace (user test feedback, #91). Each step
 * dims the page, outlines one area and explains it in a card beside it.
 */
export function WorkspaceTour({steps, onClose}: WorkspaceTourProps) {
  const [index, setIndex] = useState(0);
  const step = steps[index];
  const titleId = useId();
  const cardRef = useRef<HTMLDivElement>(null);
  const [target, setTarget] = useState<Box | null>(null);
  const [cardHeight, setCardHeight] = useState(0);

  const measure = useCallback(() => {
    const element =
      step?.target == null
        ? null
        : document.querySelector(`[data-tour="${step.target}"]`);
    if (element === null) {
      setTarget(null);
    } else {
      const rect = element.getBoundingClientRect();
      setTarget({
        top: rect.top,
        left: rect.left,
        width: rect.width,
        height: rect.height,
      });
    }
    setCardHeight(cardRef.current?.offsetHeight ?? 0);
  }, [step]);

  // Bring the area into view, then measure where it ended up on the next
  // frame, once scrolling and the card's new text have been laid out.
  useLayoutEffect(() => {
    if (step?.target != null) {
      document
        .querySelector(`[data-tour="${step.target}"]`)
        ?.scrollIntoView?.({block: 'nearest'});
    }
    const frame = requestAnimationFrame(measure);
    return () => cancelAnimationFrame(frame);
  }, [step, measure]);

  useEffect(() => {
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', measure, true);
    return () => {
      window.removeEventListener('resize', measure);
      window.removeEventListener('scroll', measure, true);
    };
  }, [measure]);

  useEffect(() => {
    cardRef.current?.focus();
  }, [index]);

  useEffect(() => {
    function handleKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  if (step === undefined) return null;
  const last = index === steps.length - 1;

  return (
    <div className="tour">
      {target === null ? (
        <div className="tour__backdrop" />
      ) : (
        <div
          className="tour__spotlight"
          style={{
            top: target.top - 4,
            left: target.left - 4,
            width: target.width + 8,
            height: target.height + 8,
          }}
        />
      )}
      <div
        ref={cardRef}
        className="tour__card"
        role="dialog"
        aria-labelledby={titleId}
        tabIndex={-1}
        style={cardPosition(target, cardHeight)}
      >
        <p className="tour__count">
          {index + 1} of {steps.length}
        </p>
        <h2 id={titleId} className="tour__title">
          {step.title}
        </h2>
        <div className="tour__body">{step.body}</div>
        <div className="tour__actions">
          <button
            type="button"
            className="button button--quiet"
            onClick={onClose}
          >
            {last ? 'Close' : 'Skip tour'}
          </button>
          <span className="tour__nav">
            {index > 0 && (
              <button
                type="button"
                className="button"
                onClick={() => setIndex(index - 1)}
              >
                Back
              </button>
            )}
            <button
              type="button"
              className="button button--primary"
              onClick={() => (last ? onClose() : setIndex(index + 1))}
            >
              {last ? 'Done' : 'Next'}
            </button>
          </span>
        </div>
      </div>
    </div>
  );
}

/**
 * Below the target if it fits, else above it, else inside its top edge
 * (for areas as tall as the screen, like the map). Centered without one.
 */
function cardPosition(target: Box | null, cardHeight: number) {
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const width = Math.min(CARD_WIDTH, viewportWidth - 2 * MARGIN);
  if (target === null) {
    return {
      width,
      left: (viewportWidth - width) / 2,
      top: Math.max(MARGIN, (viewportHeight - cardHeight) / 2),
    };
  }
  const left = Math.min(
    Math.max(MARGIN, target.left),
    viewportWidth - width - MARGIN,
  );
  const below = target.top + target.height + GAP;
  const above = target.top - GAP - cardHeight;
  let top: number;
  if (below + cardHeight <= viewportHeight - MARGIN) {
    top = below;
  } else if (above >= MARGIN) {
    top = above;
  } else {
    top = Math.max(MARGIN, target.top + GAP * 4);
  }
  return {width, left, top};
}
