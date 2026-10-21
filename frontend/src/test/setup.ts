// Runs before every test file. Adds DOM matchers such as toBeInTheDocument().
import '@testing-library/jest-dom/vitest';

// jsdom has no layout engine. React Flow needs these to measure nodes; see
// https://reactflow.dev/learn/advanced-use/testing
class ResizeObserverStub {
  private readonly callback: ResizeObserverCallback;

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }

  observe(target: Element) {
    const element = target as HTMLElement;
    const contentRect = {
      width: element.offsetWidth,
      height: element.offsetHeight,
    } as DOMRectReadOnly;
    this.callback(
      [{target, contentRect} as ResizeObserverEntry],
      this as unknown as ResizeObserver,
    );
  }

  unobserve() {}

  disconnect() {}
}

class DOMMatrixReadOnlyStub {
  readonly m22: number;

  constructor(transform?: string) {
    const scale = /scale\(([\d.]+)\)/.exec(transform ?? '')?.[1];
    this.m22 = scale === undefined ? 1 : Number(scale);
  }
}

globalThis.ResizeObserver ??= ResizeObserverStub as typeof ResizeObserver;
globalThis.DOMMatrixReadOnly ??=
  DOMMatrixReadOnlyStub as unknown as typeof DOMMatrixReadOnly;

// Edge labels measure their text.
Object.defineProperty(SVGElement.prototype, 'getBBox', {
  value: () => ({x: 0, y: 0, width: 0, height: 0}),
  configurable: true,
});

Object.defineProperties(HTMLElement.prototype, {
  offsetHeight: {
    get(this: HTMLElement) {
      return parseFloat(this.style.height) || 1;
    },
  },
  offsetWidth: {
    get(this: HTMLElement) {
      return parseFloat(this.style.width) || 1;
    },
  },
});
