import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {useState} from 'react';
import type {RepoTarget} from '../utils/repoInput.ts';
import type {RepoInputValue} from './RepoInputForm.tsx';
import {RepoInputForm} from './RepoInputForm.tsx';

/** Renders the form with its own state, like LandingPage does. */
function renderForm(onSubmit: (target: RepoTarget) => void = () => {}) {
  function Harness() {
    const [value, setValue] = useState<RepoInputValue>({url: '', ref: ''});
    return (
      <RepoInputForm value={value} onChange={setValue} onSubmit={onSubmit} />
    );
  }
  render(<Harness />);
  return {
    urlInput: screen.getByLabelText('GitHub repository URL'),
    refInput: screen.getByLabelText(/Branch, tag or commit/),
    analyzeButton: screen.getByRole('button', {name: 'Analyze'}),
  };
}

describe('RepoInputForm', () => {
  it('enables Analyze only for a valid URL', async () => {
    const user = userEvent.setup();
    const {urlInput, analyzeButton} = renderForm();

    expect(analyzeButton).toBeDisabled();
    await user.type(urlInput, 'https://github.com/pallets/flask');

    expect(analyzeButton).toBeEnabled();
  });

  it('submits the normalized URL and ref', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    const {urlInput, refInput, analyzeButton} = renderForm(onSubmit);

    await user.type(urlInput, 'github.com/pallets/flask.git/');
    await user.type(refInput, 'main');
    await user.click(analyzeButton);

    expect(onSubmit).toHaveBeenCalledWith({
      url: 'https://github.com/pallets/flask',
      owner: 'pallets',
      repo: 'flask',
      ref: 'main',
    });
  });

  it('does not show a format error while the user is still typing', async () => {
    const user = userEvent.setup();
    const {urlInput} = renderForm();

    await user.type(urlInput, 'https://git');

    expect(screen.queryByText(/Enter a GitHub repository URL/)).toBeNull();
    expect(urlInput).not.toHaveAttribute('aria-invalid', 'true');
  });

  it('shows the expected format after the user leaves the field', async () => {
    const user = userEvent.setup();
    const {urlInput} = renderForm();

    await user.type(urlInput, 'not a url');
    await user.tab();

    expect(
      screen.getByText(/for example https:\/\/github.com\/owner\/repo/),
    ).toBeInTheDocument();
    expect(urlInput).toHaveAttribute('aria-invalid', 'true');
  });

  it('explains that other Git hosts are planned when one is pasted', async () => {
    const user = userEvent.setup();
    const {urlInput, analyzeButton} = renderForm();

    await user.click(urlInput);
    await user.paste('https://gitlab.com/group/project');

    expect(screen.getByText(/GitLab is planned/)).toBeInTheDocument();
    expect(analyzeButton).toBeDisabled();
  });

  it('shows the branch it took from a /tree/ URL', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    const {urlInput, analyzeButton} = renderForm(onSubmit);

    await user.type(urlInput, 'https://github.com/o/r/tree/dev');

    expect(screen.getByText(/from the URL/)).toHaveTextContent(
      'Using dev from the URL.',
    );
    await user.click(analyzeButton);
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ref: 'dev'}),
    );
  });

  it('flags an invalid ref and blocks submission', async () => {
    const user = userEvent.setup();
    const {urlInput, refInput, analyzeButton} = renderForm();

    await user.type(urlInput, 'https://github.com/o/r');
    await user.type(refInput, 'bad ref');

    expect(screen.getByText(/not a valid branch/)).toBeInTheDocument();
    expect(refInput).toHaveAttribute('aria-invalid', 'true');
    expect(analyzeButton).toBeDisabled();
  });
});
