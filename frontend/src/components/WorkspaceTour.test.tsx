import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type {TourStep} from './WorkspaceTour.tsx';
import {WorkspaceTour} from './WorkspaceTour.tsx';

const STEPS: TourStep[] = [
  {target: null, title: 'Welcome', body: <p>Hello.</p>},
  {target: 'search', title: 'Search', body: <p>Type here.</p>},
  {target: 'map', title: 'Map', body: <p>Boxes and arrows.</p>},
];

function renderTour() {
  const onClose = vi.fn();
  render(
    <>
      <div data-tour="search">search</div>
      <div data-tour="map">map</div>
      <WorkspaceTour steps={STEPS} onClose={onClose} />
    </>,
  );
  return {onClose};
}

describe('WorkspaceTour', () => {
  it('walks forward and back through the steps', async () => {
    const user = userEvent.setup();
    renderTour();

    const dialog = screen.getByRole('dialog', {name: 'Welcome'});
    expect(dialog).toHaveTextContent('1 of 3');
    expect(
      screen.queryByRole('button', {name: 'Back'}),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', {name: 'Next'}));
    expect(screen.getByRole('dialog', {name: 'Search'})).toHaveTextContent(
      '2 of 3',
    );

    await user.click(screen.getByRole('button', {name: 'Back'}));
    expect(screen.getByRole('dialog', {name: 'Welcome'})).toBeInTheDocument();
  });

  it('closes with Done on the last step', async () => {
    const user = userEvent.setup();
    const {onClose} = renderTour();

    await user.click(screen.getByRole('button', {name: 'Next'}));
    await user.click(screen.getByRole('button', {name: 'Next'}));
    expect(screen.getByRole('dialog', {name: 'Map'})).toBeInTheDocument();
    await user.click(screen.getByRole('button', {name: 'Done'}));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('can be skipped, or closed with Escape', async () => {
    const user = userEvent.setup();
    const {onClose} = renderTour();

    await user.click(screen.getByRole('button', {name: 'Skip tour'}));
    await user.keyboard('{Escape}');

    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('moves focus to the card so keyboard users start there', () => {
    renderTour();

    expect(screen.getByRole('dialog', {name: 'Welcome'})).toHaveFocus();
  });
});
