import type {ImportKind, SymbolInfo} from '../types.ts';

/** One file of a fixture repository, written as the analyzer would see it. */
export interface FixtureFile {
  path: string;
  parsed: boolean;
  lineCount: number;
  symbols: SymbolInfo[];
  imports: Array<{
    rawName: string;
    kind: ImportKind;
    targetPath?: string;
    targetPackage?: string;
  }>;
  comments: Array<{line: number; text: string}>;
}

/** A small, hand-written repository used by the mock API client. */
export interface FixtureRepo {
  repoUrl: string;
  sha: string;
  filesExcluded: number;
  files: FixtureFile[];
}

/**
 * A small Flask app with a login feature. Small enough to check by hand,
 * with each case the UI must handle: internal, external and unresolved
 * imports, an unparsed file, a file with no imports or importers, and
 * nested modules.
 */
export const FLASK_AUTH_REPO: FixtureRepo = {
  repoUrl: 'https://github.com/repolens-demo/flask-auth',
  sha: '3f9c2a1e7b4d8c6f0a5e2b9d1c4f7a8e6b3d0c2f',
  filesExcluded: 7,
  files: [
    {
      path: 'manage.py',
      parsed: true,
      lineCount: 24,
      symbols: [{name: 'main', kind: 'function', line: 9}],
      imports: [
        {rawName: 'click', kind: 'external', targetPackage: 'click'},
        {rawName: 'app', kind: 'internal', targetPath: 'app/__init__.py'},
      ],
      comments: [{line: 1, text: 'Command-line entry point for the app.'}],
    },
    {
      path: 'app/__init__.py',
      parsed: true,
      lineCount: 31,
      symbols: [{name: 'create_app', kind: 'function', line: 8}],
      imports: [
        {rawName: 'flask', kind: 'external', targetPackage: 'flask'},
        {rawName: 'app.config', kind: 'internal', targetPath: 'app/config.py'},
        {rawName: 'app.db', kind: 'internal', targetPath: 'app/db.py'},
        {rawName: 'app.routes', kind: 'internal', targetPath: 'app/routes.py'},
        {
          rawName: 'app.auth.views',
          kind: 'internal',
          targetPath: 'app/auth/views.py',
        },
      ],
      comments: [
        {line: 7, text: 'Application factory: registers the auth blueprint.'},
      ],
    },
    {
      path: 'app/config.py',
      parsed: true,
      lineCount: 18,
      symbols: [
        {name: 'Config', kind: 'class', line: 4},
        {name: 'SECRET_KEY', kind: 'variable', line: 5},
        {name: 'TOKEN_TTL_SECONDS', kind: 'variable', line: 6},
      ],
      imports: [{rawName: 'os', kind: 'external', targetPackage: 'os'}],
      comments: [{line: 3, text: 'Settings read from environment variables.'}],
    },
    {
      path: 'app/db.py',
      parsed: true,
      lineCount: 42,
      symbols: [
        {name: 'get_db', kind: 'function', line: 10},
        {name: 'init_db', kind: 'function', line: 24},
      ],
      imports: [
        {rawName: 'sqlite3', kind: 'external', targetPackage: 'sqlite3'},
      ],
      comments: [{line: 9, text: 'One SQLite connection per request.'}],
    },
    {
      path: 'app/routes.py',
      parsed: true,
      lineCount: 37,
      symbols: [
        {name: 'index', kind: 'function', line: 8},
        {name: 'dashboard', kind: 'function', line: 15},
      ],
      imports: [
        {rawName: 'flask', kind: 'external', targetPackage: 'flask'},
        {
          rawName: 'app.auth.service',
          kind: 'internal',
          targetPath: 'app/auth/service.py',
        },
      ],
      comments: [{line: 14, text: 'Dashboard requires a logged-in user.'}],
    },
    {
      path: 'app/auth/__init__.py',
      parsed: true,
      lineCount: 1,
      symbols: [],
      imports: [],
      comments: [],
    },
    {
      path: 'app/auth/views.py',
      parsed: true,
      lineCount: 68,
      symbols: [
        {name: 'auth_bp', kind: 'variable', line: 7},
        {name: 'login', kind: 'function', line: 11},
        {name: 'logout', kind: 'function', line: 34},
        {name: 'register', kind: 'function', line: 42},
      ],
      imports: [
        {rawName: 'flask', kind: 'external', targetPackage: 'flask'},
        {
          rawName: 'app.auth.service',
          kind: 'internal',
          targetPath: 'app/auth/service.py',
        },
        {
          rawName: 'app.models.user',
          kind: 'internal',
          targetPath: 'app/models/user.py',
        },
      ],
      comments: [
        {line: 10, text: 'Login form: checks credentials, then sets a token.'},
      ],
    },
    {
      path: 'app/auth/service.py',
      parsed: true,
      lineCount: 54,
      symbols: [
        {name: 'authenticate', kind: 'function', line: 9},
        {name: 'login_user', kind: 'function', line: 22},
        {name: 'logout_user', kind: 'function', line: 36},
        {name: 'current_user', kind: 'function', line: 44},
      ],
      imports: [
        {
          rawName: 'app.models.user',
          kind: 'internal',
          targetPath: 'app/models/user.py',
        },
        {
          rawName: 'app.auth.tokens',
          kind: 'internal',
          targetPath: 'app/auth/tokens.py',
        },
      ],
      comments: [
        {line: 8, text: 'Authentication logic shared by views and routes.'},
      ],
    },
    {
      path: 'app/auth/tokens.py',
      parsed: true,
      lineCount: 33,
      symbols: [
        {name: 'create_token', kind: 'function', line: 8},
        {name: 'verify_token', kind: 'function', line: 19},
      ],
      imports: [
        {rawName: 'jwt', kind: 'external', targetPackage: 'jwt'},
        {rawName: 'app.config', kind: 'internal', targetPath: 'app/config.py'},
      ],
      comments: [{line: 7, text: 'Signed session tokens for login.'}],
    },
    {
      path: 'app/models/__init__.py',
      parsed: true,
      lineCount: 1,
      symbols: [],
      imports: [],
      comments: [],
    },
    {
      path: 'app/models/user.py',
      parsed: true,
      lineCount: 47,
      symbols: [
        {name: 'User', kind: 'class', line: 9},
        {name: 'hash_password', kind: 'function', line: 30},
        {name: 'check_password', kind: 'function', line: 38},
      ],
      imports: [
        {
          rawName: 'werkzeug.security',
          kind: 'external',
          targetPackage: 'werkzeug',
        },
        {rawName: 'app.db', kind: 'internal', targetPath: 'app/db.py'},
      ],
      comments: [{line: 8, text: 'User model with password hashing.'}],
    },
    {
      path: 'app/utils/strings.py',
      parsed: true,
      lineCount: 12,
      symbols: [{name: 'slugify', kind: 'function', line: 4}],
      imports: [{rawName: 're', kind: 'external', targetPackage: 're'}],
      comments: [],
    },
    {
      path: 'app/utils/broken.py',
      parsed: false,
      lineCount: 9,
      symbols: [],
      imports: [],
      comments: [],
    },
    {
      path: 'app/legacy.py',
      parsed: true,
      lineCount: 15,
      symbols: [{name: 'load_plugins', kind: 'function', line: 6}],
      imports: [{rawName: 'plugins.loader', kind: 'unresolved'}],
      comments: [{line: 5, text: 'Old plugin system; not used by login.'}],
    },
    {
      path: 'tests/test_auth.py',
      parsed: true,
      lineCount: 58,
      symbols: [
        {name: 'test_login_success', kind: 'function', line: 8},
        {name: 'test_login_bad_password', kind: 'function', line: 21},
        {name: 'test_logout', kind: 'function', line: 35},
      ],
      imports: [
        {rawName: 'pytest', kind: 'external', targetPackage: 'pytest'},
        {
          rawName: 'app.auth.service',
          kind: 'internal',
          targetPath: 'app/auth/service.py',
        },
      ],
      comments: [{line: 1, text: 'Tests for login and logout.'}],
    },
  ],
};
