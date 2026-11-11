import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {SearchHelp} from './SearchHelp.tsx';

describe('SearchHelp', () => {
  it('opens an explanation of matching, ranking and order', async () => {
    const user = userEvent.setup();
    render(<SearchHelp />);
    const toggle = screen.getByRole('button', {name: 'How search works'});
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(
      screen.queryByRole('region', {name: 'How search works'}),
    ).not.toBeInTheDocument();

    await user.click(toggle);

    const panel = screen.getByRole('region', {name: 'How search works'});
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    for (const heading of [
      'What it looks at',
      'How results are ranked',
      'What the order means',
      'Tips',
    ]) {
      expect(panel).toHaveTextContent(heading);
    }
    expect(panel).toHaveTextContent(/docstrings and comments/);
  });

  it('closes with Got it, Escape, or a click elsewhere', async () => {
    const user = userEvent.setup();
    render(
      <>
        <SearchHelp />
        <p>elsewhere</p>
      </>,
    );
    const toggle = screen.getByRole('button', {name: 'How search works'});

    await user.click(toggle);
    await user.click(screen.getByRole('button', {name: 'Got it'}));
    expect(toggle).toHaveAttribute('aria-expanded', 'false');

    await user.click(toggle);
    await user.keyboard('{Escape}');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');

    await user.click(toggle);
    await user.click(screen.getByText('elsewhere'));
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });
});
