import type {DependencyGraph} from '../api/types.ts';
import {neighborhood, subgraph} from './subgraph.ts';

const GRAPH: DependencyGraph = {
  modules: [
    {id: '.', name: '(root)', filePaths: ['manage.py']},
    {id: 'app', name: 'app', filePaths: ['app/views.py', 'app/db.py']},
    {
      id: 'app/auth',
      name: 'auth',
      filePaths: ['app/auth/service.py', 'app/auth/tokens.py'],
    },
  ],
  files: [
    {path: 'manage.py', module: '.', parsed: true, lineCount: 1},
    {path: 'app/views.py', module: 'app', parsed: true, lineCount: 1},
    {path: 'app/db.py', module: 'app', parsed: true, lineCount: 1},
    {
      path: 'app/auth/service.py',
      module: 'app/auth',
      parsed: true,
      lineCount: 1,
    },
    {
      path: 'app/auth/tokens.py',
      module: 'app/auth',
      parsed: false,
      lineCount: 1,
    },
  ],
  edges: [
    {source: 'manage.py', target: 'app/views.py'},
    {source: 'app/views.py', target: 'app/auth/service.py'},
    {source: 'app/views.py', target: 'app/auth/tokens.py'},
    {source: 'app/views.py', target: 'app/db.py'},
    {source: 'app/auth/service.py', target: 'app/auth/tokens.py'},
    {source: 'app/auth/service.py', target: 'app/db.py'},
  ],
};

describe('neighborhood', () => {
  it('is a file plus the files it imports and the files that import it', () => {
    expect([...neighborhood(GRAPH, 'app/auth/service.py')].sort()).toEqual([
      'app/auth/service.py',
      'app/auth/tokens.py',
      'app/db.py',
      'app/views.py',
    ]);
  });
});

describe('subgraph', () => {
  const keep = neighborhood(GRAPH, 'app/auth/service.py');

  it('keeps the kept files, their modules and the imports between them', () => {
    const part = subgraph(GRAPH, keep);

    expect(part.files.map(file => file.path).sort()).toEqual([...keep].sort());
    expect(part.modules).toEqual([
      {id: 'app', name: 'app', filePaths: ['app/views.py', 'app/db.py']},
      {
        id: 'app/auth',
        name: 'auth',
        filePaths: ['app/auth/service.py', 'app/auth/tokens.py'],
      },
    ]);
    expect(part.edges).toContainEqual({
      source: 'app/views.py',
      target: 'app/db.py',
    });
    expect(part.edges).toHaveLength(5);
  });

  it('keeps only the imports to and from the center when given one', () => {
    const part = subgraph(GRAPH, keep, 'app/auth/service.py');

    expect(part.edges).toEqual([
      {source: 'app/views.py', target: 'app/auth/service.py'},
      {source: 'app/auth/service.py', target: 'app/auth/tokens.py'},
      {source: 'app/auth/service.py', target: 'app/db.py'},
    ]);
  });
});
