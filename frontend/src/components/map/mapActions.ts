import {createContext, useContext} from 'react';

/** What the custom map nodes can ask the map to do. */
export interface MapActions {
  selectFile: (path: string) => void;
  toggleModule: (moduleId: string, expanded?: boolean) => void;
}

export const MapActionsContext = createContext<MapActions | null>(null);

export function useMapActions(): MapActions {
  const actions = useContext(MapActionsContext);
  if (actions === null) {
    throw new Error('useMapActions must be used inside MapActionsContext');
  }
  return actions;
}
