import type {NodeProps} from '@xyflow/react';
import {Handle, Position} from '@xyflow/react';
import {useMapActions} from './mapActions.ts';
import type {MapNode} from './mapLayout.ts';

type NodePropsOf<K extends MapNode['type']> = NodeProps<
  Extract<MapNode, {type: K}>
>;

// Edges attach to invisible handles: importers on the left of what they
// import, matching the left-to-right layout.
function Handles() {
  return (
    <>
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <Handle type="source" position={Position.Right} isConnectable={false} />
    </>
  );
}

/** A collapsed module. Activating it shows its files. */
export function ModuleNode({data}: NodePropsOf<'module'>) {
  const {toggleModule} = useMapActions();
  const fileCount = `${data.fileCount} ${data.fileCount === 1 ? 'file' : 'files'}`;
  return (
    <>
      <Handles />
      <button
        type="button"
        className="map-node__body"
        onClick={() => toggleModule(data.moduleId, true)}
        aria-label={`Module ${data.name}, ${fileCount}. Expand.`}
      >
        <span className="map-node__title">{data.name}</span>
        <span className="map-node__meta">{fileCount} ▸</span>
      </button>
    </>
  );
}

/** A file inside an expanded module. Activating it selects the file. */
export function FileNode({data}: NodePropsOf<'file'>) {
  const {selectFile} = useMapActions();
  return (
    <>
      <Handles />
      <button
        type="button"
        className="map-node__body"
        onClick={() => selectFile(data.path)}
        title={data.path}
        aria-label={`File ${data.path}${data.parsed ? '' : ', not parsed'}`}
      >
        <span className="map-node__title">{data.name}</span>
        {!data.parsed && <span className="map-node__badge">not parsed</span>}
      </button>
    </>
  );
}

/** The box around an expanded module's files, with a collapse control. */
export function ModuleGroupNode({data}: NodePropsOf<'moduleGroup'>) {
  const {toggleModule} = useMapActions();
  return (
    <button
      type="button"
      className="map-group__header"
      onClick={() => toggleModule(data.moduleId, false)}
      aria-label={`Module ${data.name}. Collapse.`}
    >
      ▾ {data.name}
    </button>
  );
}
