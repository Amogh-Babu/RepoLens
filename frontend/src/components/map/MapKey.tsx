import type {ReactNode} from 'react';

interface MapKeyProps {
  id: string;
  onClose: () => void;
}

/**
 * What the map's boxes, colors and lines mean (user test feedback). The
 * box samples carry the same classes as the map's nodes, so the key always
 * matches what the map draws.
 */
export function MapKey({id, onClose}: MapKeyProps) {
  return (
    <section id={id} className="map-key" aria-label="Map key">
      <div className="map-key__header">
        <h2 className="map-key__title">Key</h2>
        <button
          type="button"
          className="map-key__close"
          onClick={onClose}
          aria-label="Hide the key"
          title="Hide the key"
        >
          ×
        </button>
      </div>
      <ul className="map-key__list">
        <Entry sample={<Box kind="module" />}>Folder. Click to open it.</Entry>
        <Entry sample={<Box kind="moduleGroup" />}>
          Open folder. Click its name to close it.
        </Entry>
        <Entry sample={<Box kind="file" />}>File</Entry>
        <Entry sample={<Box kind="file" state="selected" />}>
          Selected file
        </Entry>
        <Entry sample={<Box kind="file" state="related" />}>
          Imports or is imported by the selected file
        </Entry>
        <Entry sample={<Box kind="file" state="match" />}>
          Matches your search
        </Entry>
        <Entry sample={<Box kind="file" state="dimmed" />}>
          Not connected to the selection or search
        </Entry>
      </ul>
      <ul className="map-key__list">
        <Entry sample={<Line kind="plain" />}>
          Import. The arrow points to the file being imported.
        </Entry>
        <Entry sample={<Line kind="imports" />}>
          The selected file imports this
        </Entry>
        <Entry sample={<Line kind="imported-by" />}>
          This imports the selected file
        </Entry>
        <Entry sample={<span className="map-key__count">3</span>}>
          Number of imports along one line
        </Entry>
      </ul>
    </section>
  );
}

function Entry({sample, children}: {sample: ReactNode; children: ReactNode}) {
  return (
    <li className="map-key__entry">
      <span className="map-key__sample" aria-hidden="true">
        {sample}
      </span>
      <span>{children}</span>
    </li>
  );
}

function Box({
  kind,
  state,
}: {
  kind: 'module' | 'moduleGroup' | 'file';
  state?: 'selected' | 'related' | 'match' | 'dimmed';
}) {
  const className = [
    'map-key__box',
    `map-node--${kind}`,
    state === undefined ? '' : `map-node--${state}`,
  ].join(' ');
  return <span className={className.trim()} />;
}

function Line({kind}: {kind: 'plain' | 'imports' | 'imported-by'}) {
  return (
    <svg
      className={`map-key__line map-key__line--${kind}`}
      width="30"
      height="10"
      viewBox="0 0 30 10"
    >
      <line x1="0" y1="5" x2="22" y2="5" stroke="currentColor" />
      <path d="M21 1 L29 5 L21 9 Z" fill="currentColor" />
    </svg>
  );
}
