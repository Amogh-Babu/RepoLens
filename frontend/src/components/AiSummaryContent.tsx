import type {ReactNode} from 'react';

function renderInlineCode(text: string): ReactNode[] {
  return text
    .split(/(`[^`]+`)/g)
    .map((part, index) =>
      part.startsWith('`') && part.endsWith('`') && part.length > 2 ? (
        <code key={index}>{part.slice(1, -1)}</code>
      ) : (
        part
      ),
    );
}

/** Render model text as plain React text, with only backtick code styling. */
export function AiSummaryContent({text}: {text: string}) {
  const lines = text.split(/\r?\n/);
  const blocks: ReactNode[] = [];
  let listItems: string[] = [];
  const flushList = (keyPrefix: string) => {
    if (listItems.length === 0) return;
    blocks.push(
      <ul key={`${keyPrefix}-ul`} className="detail__ai-list">
        {listItems.map((item, index) => (
          <li key={index}>{renderInlineCode(item)}</li>
        ))}
      </ul>,
    );
    listItems = [];
  };
  lines.forEach((rawLine, index) => {
    const line = rawLine.trim();
    if (line === '') {
      flushList(`line-${index}`);
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      listItems.push(line.slice(2).trim());
    } else {
      flushList(`line-${index}`);
      blocks.push(
        <p key={`p-${index}`} className="detail__ai-paragraph">
          {renderInlineCode(line)}
        </p>,
      );
    }
  });
  flushList('end');
  return <div className="detail__ai-body">{blocks}</div>;
}
