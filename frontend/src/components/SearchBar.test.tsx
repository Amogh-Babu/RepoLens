import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {SearchBar} from './SearchBar.tsx';

function renderBar(active = false) {
  const handlers = {onSearch: vi.fn(), onClear: vi.fn()};
  render(<SearchBar active={active} searching={false} {...handlers} />);
  return {
    ...handlers,
    input: screen.getByRole('searchbox', {name: 'Search this repository'}),
  };
}

describe('SearchBar', () => {
  it('submits the trimmed query', async () => {
    const user = userEvent.setup();
    const {onSearch, input} = renderBar();

    await user.type(input, '  login user {Enter}');

    expect(onSearch).toHaveBeenCalledWith('login user');
  });

  it('shows a hint instead of searching for whitespace', async () => {
    const user = userEvent.setup();
    const {onSearch, input} = renderBar();

    await user.type(input, '   ');
    await user.click(screen.getByRole('button', {name: 'Search'}));

    expect(onSearch).not.toHaveBeenCalled();
    expect(screen.getByText('Enter a keyword to search for.')).toBeVisible();
    expect(input).toHaveAttribute('aria-invalid', 'true');
  });

  it('rejects a query over 200 characters', async () => {
    const user = userEvent.setup();
    const {onSearch, input} = renderBar();

    await user.click(input);
    await user.paste('x'.repeat(201));
    await user.keyboard('{Enter}');

    expect(onSearch).not.toHaveBeenCalled();
    expect(screen.getByText(/limited to 200 characters/)).toBeVisible();
  });

  it('clears the search with the clear button', async () => {
    const user = userEvent.setup();
    const {onClear, input} = renderBar(true);
    await user.type(input, 'login');

    await user.click(screen.getByRole('button', {name: 'Clear search'}));

    expect(onClear).toHaveBeenCalled();
    expect(input).toHaveValue('');
  });

  it('clears the search when the box is emptied', async () => {
    const user = userEvent.setup();
    const {onClear, input} = renderBar(true);
    await user.type(input, 'ab');

    await user.clear(input);

    expect(onClear).toHaveBeenCalled();
  });
});
