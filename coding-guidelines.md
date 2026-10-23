# Coding Guideline

## Python (Backend)

The link below is the Google Python Style Guide. This guideline was selected for two reasons: First, it’s an industry standard coding guideline, though there are a few of those. Second, we chose Google’s guideline due to their reputation and the breadth of their influence on coding practices in general. We plan on enforcing the style guideline with an automated linter, built on Python’s ast library, that is applied to the code periodically. The linter parses each source file into an abstract syntax tree and walks the tree to check for violations such as naming conventions, docstring presence, import ordering, and function complexity.

https://google.github.io/styleguide/pyguide.html

## TypeScript (Frontend)

The link below is the Google TypeScript Style Guide, which applies to the React frontend. This guideline was selected for two reasons: First, it is an industry standard guideline for TypeScript, and it comes from the same company as the Google Python Style Guide we use for the backend, so both halves of the codebase follow one consistent set of conventions. Second, it gives clear rules on the choices that cause the most disagreement in code review, such as named exports instead of default exports, const and let instead of var, and avoiding the any type. We plan on enforcing the style guideline with ESLint and Prettier, both run in GitHub Actions on every pull request so that code that fails either check cannot be merged. ESLint parses each source file into an abstract syntax tree and walks the tree to check for violations such as naming conventions, unused variables, import ordering, and use of the any type, and Prettier is configured to match the guide's formatting.

https://google.github.io/styleguide/tsguide.html
