// ESLint config enforcing the Google TypeScript Style Guide where a lint rule
// can check it. Formatting is left to Prettier (see .prettierrc.json).
// https://google.github.io/styleguide/tsguide.html

import js from '@eslint/js';
import prettier from 'eslint-config-prettier';
import importX from 'eslint-plugin-import-x';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import {defineConfig, globalIgnores} from 'eslint/config';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default defineConfig([
  globalIgnores(['dist', 'coverage']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat['recommended-latest'],
      reactRefresh.configs.vite,
    ],
    plugins: {'import-x': importX},
    languageOptions: {
      ecmaVersion: 2023,
      globals: globals.browser,
    },
    rules: {
      // Variables: const and let only, never var.
      'no-var': 'error',
      'prefer-const': 'error',
      eqeqeq: ['error', 'always', {null: 'ignore'}],

      // Types: no any, no non-null assertions, type-only imports marked.
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-non-null-assertion': 'error',
      '@typescript-eslint/consistent-type-imports': 'error',
      '@typescript-eslint/no-unused-vars': [
        'error',
        {argsIgnorePattern: '^_', varsIgnorePattern: '^_'},
      ],

      // Naming: UpperCamelCase for types and components, lowerCamelCase for
      // values, CONSTANT_CASE allowed for module-level constants.
      '@typescript-eslint/naming-convention': [
        'error',
        {selector: 'default', format: ['camelCase']},
        {selector: 'import', format: null},
        {
          selector: 'variable',
          format: ['camelCase', 'PascalCase', 'UPPER_CASE'],
        },
        {selector: 'function', format: ['camelCase', 'PascalCase']},
        {
          selector: 'parameter',
          format: ['camelCase'],
          leadingUnderscore: 'allow',
        },
        {selector: 'typeLike', format: ['PascalCase']},
        {selector: 'enumMember', format: ['UPPER_CASE']},
        {selector: 'objectLiteralProperty', format: null},
        {selector: 'typeProperty', format: null},
      ],

      // Modules: named exports only, ordered imports.
      'import-x/no-default-export': 'error',
      'import-x/no-duplicates': 'error',
      'import-x/order': [
        'error',
        {
          groups: ['builtin', 'external', 'internal', 'parent', 'sibling'],
          'newlines-between': 'never',
          alphabetize: {order: 'asc', caseInsensitive: true},
        },
      ],
    },
  },
  {
    // Node-side config files.
    files: ['*.config.{js,ts}'],
    languageOptions: {globals: globals.node},
  },
  {
    files: ['eslint.config.js'],
    extends: [js.configs.recommended],
    languageOptions: {globals: globals.node},
  },
  prettier,
]);
