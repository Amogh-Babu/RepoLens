# RepoLens: Living Document
## Shashank Giridharan, Austin Elenzano, Levi Lenin, Abhinav Damarla, Amogh Babu, Dylan Maring
## Team info
  - *Ingestion Engineer (Austin):* Implements downloading a public GitHub repository at a given commit while preventing any code from being executed. Also designs filtration of auto-generated files, and caching results based on repository information.
  - *Analysis Engineer (Shashank):* Implements the Python ᴀꜱᴛ parser for imports and symbol analysis, to effectively determine if imports belong to the same or external libraries.
  - *Graph Engineer (Amogh):* Backend design for the initial dependency graph schema. Also in charge of storing files, modules, imports, and other symbols in the graph database. 
  - *Search Engineer (Abhinav):* Creates the Python ᴀᴘɪ for searching filenames, symbols and comments. Also designs query ranking order, reading order suggestion, other logic.
  - *Frontend Engineer (Levi):* Builds the React application, including a file explorer, interactive dependency graph, and search bar, with intuitive links to the code itself.
  - *Product Manager & Evaluation Lead (Dylan):* Sets up milestones and progress reporting. Keeps this document/ʀᴇᴀᴅᴍᴇ updated. During testing phases, also in charge of writing test plans, handling deployment, and evaluation with test participants.
### Project artifacts
  - ***GitHub repo:*** [Amogh-Babu/RepoLens](https://github.com/Amogh-Babu/RepoLens)
  - *Task tracker:* [GitHub Issues](https://github.com/Amogh-Babu/RepoLens/issues) 
  - *Pitch slides:* [Slides](https://docs.google.com/presentation/d/1lyTGd5yCl5d6p6VrLaf48r3ta-7MyBIR/edit?usp=sharing&ouid=105870811458408920199&rtpof=true&sd=true)
  - *Deployed demo:* **ᴛᴏᴅᴏ**
***Communication:*** Meet Tu/Th, 1:30–2:20 ᴘᴍ. Use WhatsApp. Manage code and assign tasks through GitHub issues and ᴘʀs (*merge to main requires teammate review*). Documentation here\!
## Product description
RepoLens is a web app that helps users understand GitHub repositories by creating an interactive visual dependency map and recommending readings for specific features. A new contributor can search for key terms, read related files, and follow links to the source code. The map and digestible recommendations will steer users to relevant code.
***Goal:*** Help coders who are new to a team or open-source project, by showing *how files are related* and *where to start*. (*Ex:* Studying app’s login workflow? Learn authentication path, related services, and the user model the framework depends on.) RepoLens suggests and justifies an order to study these files in, showing details like import dependencies.
***Current practice:*** Established code nav, vis, and onboarding methods include ʀᴇᴀᴅᴍᴇ files, repo-wide searches, and manual code inspections. GitHub lets a user locate symbol definitions and usage. *Prior art:* Sourcegraph gives greater search and nav options, including between repos. CodeBoarding has interactive code structure maps using static analysis and ʟʟᴍs.
***Novelty:*** We narrow our scope to onboarding assistance for a specified feature in a large repo, helping choose file analysis order and develop reading/studying techniques. Search returns a list of files by relevance to the topic, info on dependencies, a suggested reading order, and reasoning. Better for gathering info and context than other tools’ brief, black-box explanations.
***Effectiveness and evidence of value:*** To test the output reading orders, we conduct a user study with classmates in weeks 7–8. Participants will complete two tasks on unfamiliar repos, one with prior tools (e.g. GitHub code search, manual inspection) and one with RepoLens. We will quantify *identification time* (seconds to reach the right file/dependencies) and *path efficiency* (number of irrelevant files before reaching the goal) against the baseline, then survey users about feature comprehension and cognitive load, to see if speed and understanding increase.
***Technical approach and scope:*** Our ᴍᴠᴘ takes a public Git repo ᴜʀʟ and analyzes a chosen commit. A built-in Python ᴀꜱᴛ parses the project’s imports and symbol names through a language-neutral analyzer interface. A resolver decides if each import is an internal/external library. Store these symbols and artifacts in a graph database. A Python ᴀᴘɪ feeds the frontend with a file explorer, an interactive graph, and a search bar to query the repo (*e.g. for specific filenames, symbols*). An algorithm finds the priority ranking for each file and justifies each suggestion. The output reading order is a suggestion, not the repo’s order of execution. Cached data is determined based on the given ᴜʀʟ and chosen commit. We will implement ingestion, parsing, graph schemas, and a general-use ᴀᴘɪ in weeks 1–2; implement and iterate on the codebase analyzer, mapping, search feature, and source data linking in weeks 3–6; and conduct user evaluation, error cleanup, and deployment in weeks 7–9. Git history and broader summaries are stretch goals. Potential challenges include handling cross-layout imports, synchronizing and creating graphs, and ᴜɪ design.
### Major features
1.  *Repository ingestion by ᴜʀʟ and commit (P0)*: When the user provides a public Git repository ᴜʀʟ and a specific commit, RepoLens should process it without executing the code. All auto-generated files are removed from the analysis, and important information is cached.
2.  *Python import and symbol extraction (P0)*: For each file in the codebase, the analysis will classify all imports as internal or external libraries, and create a list of symbols.
3.  *Interactive dependency map (P0)*: The ᴜɪ will allow for easier file browsing, displaying an interactive graph of all the files, grouped by module names and similarity.
4.  *Feature search with ranked reading list (P0)*: Users can enter keywords, and RepoLens will query the codebase for the term, looking at filenames, symbols, class members, imports, docstrings, and comments. The frontend will display the highest priority results first.
5.  *Source code links (P1)*: Each file/symbol contains a link to the exact file in the repository.
6.  *Proper processing of unsupported inputs (P1)*: Invalid inputs (e.g. large, non-public, non-Python codebases; invalid ᴜʀʟs) will provide explanatory and actionable error messages instead of crashing the app.
### Test plan
  - *Test-automation infrastructure*
      - Frontend: Vitest with React Testing Library. Test files sit next to the code they test and use a mock ᴀᴘɪ, so they need no backend.
      - Backend: pytest. Tests live in backend/tests and cover search, the graph store and the ᴀᴘɪ routes.
  - *Justification*
      - pytest is the standard Python test tool: tests are plain functions with assert, and it works with FastAPI's test client.
      - Vitest uses the same Vite setup as the app (*no extra config*), and React Testing Library tests the ᴜɪ the way a user sees it.
  - *How to add a test*
      - *Backend:* Add backend/tests/test\_\<feature\>.py with test\_\* functions; run python -m pytest in backend/.
      - *Frontend:* Add \<Name\>.test.tsx next to the component; run npm test in frontend/.
  - *CI service and how it is linked:* GitHub Actions. GitHub automatically runs the workflow files committed in .github/workflows/ (frontend.yml, backend.yml and release.yml), so no other account or setup is needed. Results show as checks on each pull request.
  - *Why GitHub Actions:* Our code is already on GitHub, it is free for public repositories, and unlike Travis CI or CircleCI it needs no separate account.
  - *Tests run in ᴄɪ*
      - Frontend: lint, format check, typecheck, all Vitest tests and the build
      - Backend: all pytest tests on the pinned Python 3.12 with locked dependencies, plus a compatibility run on 3.11 (the minimum) and 3.14
      - Image: build the Docker image, run the backend tests inside it, and smoke-test the running container
  - *What triggers ᴄɪ:* Opening/updating a ᴘʀ, or pushing to main, when the change touches frontend/ or backend/. Workflows can also be run by hand from the Actions tab. The release workflow runs on every push to main and on ᴘʀs that change the image; on main it also publishes the image to the GitHub Container Registry.
### Stretch goals
  - Support a second language (P2)
  - Support other Git hosts *e.g. GitLab* (P2)
  - Private repos via GitHub sign-in (P2)
  - Git history for version analysis (P2)
  - Generated-text file summaries (P2)
### Use cases
1.  **Analyze a public repository by ᴜʀʟ and commit** *(Merged with cases 5, 6)*
    1.  *Actors*
        1.  A new contributor (*e.g. student, ᴏꜱꜱ newcomer*) using RepoLens in a browser
        2.  GitHub, which hosts the repository snapshot and the RepoLens backend, which manages ingestion, analysis and graph storage
    2.  *Trigger:* The user enters a repo ᴜʀʟ (optionally with commit branch or tag) and hits Analyze.
    3.  *Preconditions*
        1.  The user has a browser and working internet connection.
        2.  The repo is publicly hosted on github.com and contains Python source files.
        3.  After filtering, the repo contains ≤ 1,000 Python files (the ᴍᴠᴘ limit).
        4.  GitHub can be reached.
    4.  *Postconditions*
        1.  Repo is analyzed at resolved commit ꜱʜᴀ; result is cached under (repository, ꜱʜᴀ) for 24 hr.
        2.  Graph store has every analyzed file, module, import (marked as in-/external) and symbol.
        3.  The user sees the file explorer, the dependency map, the search bar, and a summary that lists analyzed files excluded and files that could not be parsed.
        4.  No code from the repository is executed.
    5.  *Steps*
        1.  The user enters a repository ᴜʀʟ and may optionally enter a commit branch or tag.
        2.  Frontend matches it against github.com/\<owner\>/\<repo\> and enables Analyze button.
        3.  The user presses Analyze. The frontend displays a progress indicator.
        4.  The backend looks up (repository, commit) in the cache. Finds no entry.
        5.  Backend resolves requested commit to ꜱʜᴀ. If no commit given, use head of default branch.
        6.  The backend downloads a source snapshot at that ꜱʜᴀ from GitHub as files and it does not run any repository code, hooks, or build scripts.
        7.  The backend removes auto-generated and vendored files (e.g. generated protobuf modules, build output, node\_modules, \_\_pycache\_\_), counting them as excluded.
        8.  Backend parses each Python file left with the ᴀꜱᴛ parser, extracting imports and symbols.
        9.  The resolver classifies each import as internal if it resolves to a file in the repository or external if it is part of the library or a third‑party package.
        10. Backend stores the files, modules, imports, symbols in the graph store, cached for 24 hr.
        11. The frontend swaps the progress bar for the explorer, map, search, and summary.
    6.  *Extensions and variations*
        1.  2a. If the ᴜʀʟ ends with a trailing slash, .git suffix, or /tree/\<branch\> path, the frontend normalizes it to the base repo ᴜʀʟ. Uses the branch as requested commit.
        2.  4a. If there is a cache hit for (repository, ꜱʜᴀ), steps 6–10 are skipped. The result loads from the cache. The summary indicates the age of the cached analysis.
        3.  4b. If another user is already analyzing the (repository, ꜱʜᴀ), this request joins the running analysis instead of starting a new one.
        4.  5a. If the user supplied a branch or tag, the backend resolves it to a ꜱʜᴀ and the summary displays that ꜱʜᴀ so the analysis is reproducible.
        5.  8a. If a file has a syntax error, it is marked as unparsed, still appears in the explorer with no dependency edges, and is counted in the summary. Analysis of remaining files continues.
        6.  9a. If an import can’t be resolved as internal or as a known library (*e.g. a dynamic/relative import pointing outside the repo*), mark it as unresolved and show it in the file’s detail panel.
        7.  3a. If the user hits Cancel or closes the tab, backend discards results and caches nothing.
    7.  *Exceptions*
        1.  Unsupported ᴜʀʟ/host: Frontend blocks submission, shows expected format example, and sends nothing to backend. State remains unchanged. The input is preserved for editing.
        2.  Repo not found or private: The backend reports that the repo does not exist or is not public. It states that this version of RepoLens supports public GitHub repos and other Git hosts are planned. State remains unchanged, nothing is cached; the input is preserved.
        3.  Commit, branch or tag not found: The backend reports which reference failed and offers to analyze the default branch. Nothing is cached.
        4.  No Python files after filtering: The backend explains that RepoLens supports only Python repositories, in this version. Nothing is cached.
        5.  \> 1,000 files: Rejects repo, reports file count / limit, suggests smaller repo. Nothing cached.
        6.  GitHub rate-limited: The backend discards the partial download and returns an error with a Retry button. State: nothing cached.
        7.  Unexpected analysis failure or timeout: The backend discards graph data so that no half-analyzed repository is cached, and the frontend shows a generic error with a Retry button. State: nothing cached, details logged for the team.
2.  **Search for a feature and get a ranked reading list** *(Merged with case 4)*
    1.  *Actors*
        1.  New contributor trying to learn how one feature (e.g. authentication) works
        2.  RepoLens backend (search and ranking over the cached graph)
    2.  *Trigger:* The user types a keyword or phrase into the search bar and presses Search.
    3.  *Preconditions*
        1.  Use Case 1 completed for loaded (repository, ꜱʜᴀ); cached analysis has not expired.
        2.  The explorer, the map, and the search bar are visible.
    4.  *Postconditions*
        1.  Show a ranked reading list. Each entry has position, file path, rank rationale, link to source.
        2.  Files that match the query are highlighted on the map and other files are dimmed.
        3.  Stored graph and cache are unchanged. List reflects the loaded commit.
    5.  *Steps*
        1.  The user enters and submits a query (e.g. "authentication") with the search bar.
        2.  The frontend trims the query and sends it to the backend with (repository, ꜱʜᴀ).
        3.  The backend matches it against file names, symbols, class members, imports, docstrings and comments in the graph.
        4.  Backend ranks matching files by query relevance and role in dependency graph, so files other results depend on are suggested earlier. Result is reading (*not execution*) order.
        5.  For each file, the backend generates a one-line reason that cites evidence (for example "defines login\_user; imported by 4 other matching files").
        6.  Backend returns ordered list targeting response within 1 second for repository.
        7.  Frontend renders reading list with highest-priority files
        8.  Frontend highlights matching files on the dependency map. Dims the rest.
        9.  The user reads the list and selects an entry to inspect it *(→ Use Case 3)*.
    6.  *Extensions and variations*
        1.  1a. User enters words: Treated as separate terms. Files matching more terms rank higher. Filler words (e.g. “where”, “do”, “the”) are ignored, so a plain question searches only its topic words.
        2.  1b. User submits a query before previous results return: Frontend ignores late response from earlier query so list always matches latest query.
        3.  1c. User clears search bar: Reading list closes, highlighting clears, map view reverts.
        4.  3a. Query matches no files: Frontend shows "No files match '\<query\>'" with suggestions (try a word, function, or class name). Map keeps default view.
        5.  6a. \> 20 files match: frontend shows first 20 and a Show more control that loads 20 more.
        6.  7a. User expands entry reason to see every matching symbol/import/comment in that file.
    7.  *Exceptions*
        1.  Whitespace-only query: Don’t send request; show “enter keyword” hint. State: unchanged.
        2.  Query \> 200 chars: Frontend rejects it with message stating limit. Previous results kept.
        3.  Cached analysis expired/evicted: Backend reports so; frontend shows Reanalyze with ᴜʀʟ and commit *(Use Case 1)*. Current view stays onscreen. No results shown for the new query.
        4.  Backend error or no response within 5 seconds: Frontend shows error banner with Retry button. State: previous results and highlighting are. The stored graph is unaffected.
3.  **Explore the dependency map and open a file’s source** *(Merged with case 4)*
    1.  *Actors*
        1.  New contributor trying to understand how files in a repo relate to each other
        2.  GitHub (serves the source file the user opens)
    2.  *Trigger*: The user clicks a module group, a file in the map or explorer, or a reading list entry.
    3.  *Preconditions*
        1.  Use Case 1 has finished for the loaded repository and ꜱʜᴀ and the analysis is still cached.
        2.  The map is rendered. Search results *(Use Case 2)*. May not be present.
    4.  *Postconditions*
        1.  The selected file is highlighted, with the files that it imports and that import it.
        2.  A detail panel shows the file’s path, module, symbols, internal imports, external libraries and the files that import it.
        3.  The file’s source is opened in a browser tab at the analyzed commit on github.com.
        4.  The RepoLens tab retains its repo, results, and selection so the user can keep exploring.
    5.  *Steps*
        1.  The user sees the dependency map with files grouped into collapsed module nodes.
        2.  User clicks a module node. It expands to show its files and import edges between them.
        3.  User clicks file node. Frontend marks file selected, highlights its dependencies/dependents, dims unrelated nodes. (*External libraries are listed in the detail panel, not shown as nodes.*)
        4.  The detail panel opens with the file’s path, module, symbols, internal imports, external libraries and an "imported by" list.
        5.  The user clicks "Open source" in the panel.
        6.  The browser opens github.com/\<owner\>/\<repo\>/blob/\<ꜱʜᴀ\>/\<path\> in a new tab, pinned to the commit that was analyzed.
        7.  The user returns to the RepoLens tab. Selection, expanded modules & results are still there.
    6.  *Extensions and variations*
        1.  1a. The user zooms, pans, or drags nodes: A Reset view button restores the default layout.
        2.  3a. User selects file from explorer tree: Map expands its module, pans to node, selects it.
        3.  3b. The user selects the file from a reading list entry: the same selection. The panel shows the file’s position and reason from the list with a "Next in reading order" button.
        4.  5a. Clicks file in panel’s “imports”/“imported by” list: Selection moves there; panel updates.
        5.  6a. User clicks symbol in panel: Opened GitHub link includes line № of symbol’s definition.
    7.  *Exceptions*
        1.  Selected file unparsed due to syntax error: Panel warns dependency info’s unavailable, lists no imports; still provides source link. State: the selection. The file has no edges on the map.
        2.  Selected file has no imports nor importers: Panel says so; map shows node alone. No error.
        3.  Map can’t render in 2 seconds / browser can’t draw it: Frontend falls back to explorer and list view with a message; every file stays selectable and linkable. State: analysis data intact.
        4.  Browser blocks tab: Frontend shows the ᴜʀʟ as a directly clickable link. State: unchanged.
        5.  GitHub returns 404 (*repo deleted/privated, commit was removed*): GitHub’s error page shows in the tab. RepoLens can’t detect this in advance, so the panel always displays the path. Commit ꜱʜᴀ so user can find the file another way. State: RepoLens tab unaffected.
        6.  Cached analysis expires while user explores: Next selection says “analysis expired”, with Reanalyze button *(Use Case 1)*. Current map stays visible but read-only until reanalysis.
### Non-functional requirements
1.  *Performance–latency:* Support a Python repo up to 1,000 files (*≈ 100,000 lines of code*) and complete initial ingestion, symbol parsing, and dependency construction in 3 minutes. Afterward, the codebase state is cached, search results should appear in 1 second, and the graph should render in 2. Verify this by running RepoLens multiple times on repositories of increasing sizes, ensuring that the initial and cached processes are at the baseline.
2.  *Security–privacy:* RepoLens must only conduct code analysis through static parsing, using ᴀꜱᴛs, but never actually run code from the inputted repos. Also, never store credentials or personal information, and store cached repos for only 24 hours. We will review our code to ensure we never call exec or import on analyzed files; submit a test repo with malicious code that would access internal data if executed, and ensure no such side effects occur; and reject all malformed/unsupported ᴜʀʟs, with clear error messages.
3.  *Usability–accuracy*: A new user can intuit all features (*like symbol/feature search, reading list, file nav*) in 2 minutes. The system should classify internal, external, and other dependencies 95% of the time, and handle syntax errors without crashing or other failures. We’ll validate by conducting user surveys/studies, timing users on how long it takes them to pick up the system. We will also run the parser on broken code to ensure no errors are raised.
### External requirements
1.  *Robustness:* Anticipate invalid input (malformed ᴜʀʟs, unsupported hosts, non-Python codebases, empty or large repos), handle it without crashing, and tell the user how to resolve the issue. Maintain a list of potential error cases, write tests for them, and ensure the backend returns an organized error report.
2.  *Accessibility:* Anyone will be able to open the final project on any device with a modern browser and internet connection, no account creation or app installation required.
3.  *Development:* Our ʀᴇᴀᴅᴍᴇ will have extensive setup and development instructions, sufficient for a new dev to build and run the system locally. Include dependency requirements, server setup, and architecture documentation. A Docker image runs the whole app with one command (docker compose up), and dependency versions are locked.
4.  *Scope:* We have a ᴍᴠᴘ to build in nine weeks. It only covers Python repos. Version control analysis, broader summaries, and other language support are left as stretch goals. A modular design will let us work independently, for efficiency.
### Team process
*Tue:* meet to review work, discuss any issues, assign weekly tasks. *Thu:* check progress, discuss issues. Communicate using WhatsApp. Make important decisions in GitHub issues or this doc.
Use GitHub to manage code, assign tasks, and review changes to implement. Each task should have an owner and a list of things to do to complete it. Each member works on a different branch, and a teammate will review a pull request before merging.
Python’s ᴀꜱᴛ parser analyzes code without executing it. It and the host sit behind interfaces we can replace (*e.g. to add a language, or GitLab support*) without rewriting other components. FastAPI integrates front- and backend and offers ᴀᴘɪ docs. React drives ᴜɪ; Flow renders the graph. We will choose graph storage in the first week based on our queries and settings.
GitHub Actions tests and builds on the ᴘʀ stage. The ʀᴇᴀᴅᴍᴇ describes installing, execution, and the contribution process. A Docker image, built, tested and published by GitHub Actions, runs the whole app.
### Role choice rationale
  - *Austin*: Familiarity with GitHub will be useful for ingesting repos into the system. Will guarantee the safe transfer of necessary files to the rest of the system.
  - *Shashank:* Experience with Python and backend systems suits an analysis role. Can manage import and symbol extraction, parser testing, and backend integration.
  - *Amogh:* Familiarity with data structures is applicable in the graph role. Will use knowledge to organize the repo relationship and make it searchable and visible.
  - *Abhinav:* Interest in algorithms suits the search and reading-rec roles. This task involves developing ranking heuristics and evaluating its effectiveness.
  - *Levi:* Experience in frontend dev is appropriate for this role. Will use knowledge to present the backend’s analysis in a friendly ᴜɪ.
  - *Dylan:* Experience with project specification and technical writing suits a product management and evaluation role.
### Major issues
  - *Bad import analysis:* Projects use different structures, and incorrect relationships can confuse users. Must notify about unresolved imports and describe unsupported patterns.
  - *Uninformative maps or reading paths:* Viewing too many map entries can be overwhelming. Search results can refer to incorrect files. Must organize files in modules, display extra info needed, and explain recommendations. Test externally to help find confusing results early.
  - *Problems with GitHub or large repos:* Network issues, rate limiting, and large downloads can hinder analysis. Must handle timeouts, enforce repo size limits, cache results, and give useful error messages. Local test repos let us work in isolation from GitHub.
  - *Integration:* Components can have different identifiers or responses. Must agree on common formats early, discuss changes, and test the whole process from week 3.
### Risk assessment
1.  *Keyword search gives unhelpful lists (very likely, high-impact):* A graph is useless if queries produce the wrong set of files. Search only matches filenames, symbols, class members, imports, docstrings, comments; needs testing on actual repos. To gauge by week 4, Abhinav and Shashank will label the right set of files for some queries on three different repos, comparing results in terms of the precision of our top five against a basic grep filename baseline. \[*Measured: top-5 precision 0.263, up from 0.211, vs. grep’s 0.042.*\]
2.  *Import classification fails on real project layouts (likely, high-impact):* Source layouts, namespace packages, re-exports from init.py, and dynamic imports cannot be solved statically. We have only tried testing hand-crafted examples so far \[*updated with real repo tests*\]. We will generate test data sets for each source layout, and manually check real repos for an accuracy percentage before measuring week 7 against our 95% goal. A raised unresolved-import rate will mean we missed some patterns.
3.  *Parallel components don’t mesh (likely, high-impact):* Since each dev codes a module behind different interfaces, small issues like path format can break the pipeline. The OpenAPI schema is our source of truth; start any change by GitHub issue and teammate consensus. From the third week, we test our small repo end-to-end test via ᴄɪ. If the test fails or no GitHub issue exists about changing the schema, there is drift\!
4.  *GitHub limits or large repos break the time budget (likely, medium-impact):* Rate limit and repos near 1,000 files might pass 3 minutes. Rather than individual files, we will download one archive and limit the file size and timeouts, with cache depending on (repo, ꜱʜᴀ). Austin will benchmark ingestion speed for ever-bigger repos from week 4. If we fail, either parallelize parsing, reduce number of files, or use a token from server side via environment variable.
5.  *Map is too slow or cluttered (likely, medium-impact):* React can struggle with this many nodes. Start collapsed and with external libraries outside the graph. Levi will benchmark a max-file repo against the 2-second target by week 5. If it fails, use the explorer/list-view fallback.
### Project schedule
|  |  |
| :- | :- |
| **M1** (wk 2) 8⁄10    *Pipeline prototype* | *Austin:* Download by ꜱʜᴀ    *Shashank:* Parse sample repos    *Amogh:* SQLite schema, save/load    *Abhinav:* Search output format, basic matching    *Levi:* Screen prototypes |
| **M2** (wk 3) 5⁄10    *One use case, end-to-end* | *Austin:* File filtering and size limits    *Shashank:* Relative imports, unparsable files    *Amogh:* Graph, file-detail endpoints    *Abhinav:* Ranked results with reasons    *Levi:* Real repo in explorer and map |
| **M3** (wk 4) 6⁄10    *First public version* | *Austin:* Cache reuse    *Shashank:* Import verification    *Amogh:* Module groups, source links    *Abhinav:* Reading paths    *Levi:* File panel, GitHub links    *Dylan:* Walkthrough with outside students |
| **M4** (wk 6) 8⁄10    *ᴍᴠᴘ checklist* | *Austin:* Error, cache\-expiry tests    *Shashank:* Real-repo accuracy, syntax-error checks    *Amogh:* Graph, source link validation    *Abhinav:* Comment search, no-result handling, ranking checks    *Levi:* Loading, empty, error screens; map benchmark    *Dylan:* Acceptance checklist |
| **M5** (wk 7–8) 8⁄10    *Study complete* | Measure timings, accuracy; fix issues    *Dylan:* Comparison study, ʀᴇᴀᴅᴍᴇ build test |
| **M6** (wk 9) 5⁄10    *Release* | *Austin, Shashank:* Final tests, limitations    *Amogh, Abhinav:* Interface docs, final tests    *Levi:* Test deployed interface    *Dylan:* Confirm public ᴜʀʟ, finish docs |

### Test plan and bugs
Cover reliability, import/ranking accuracy, safe ingestion, invalid input, timing targets, etc.
  - *Unit:* Each owner writes tests for their own component. GitHub Actions runs them on every pull request. A ᴘʀ with a failing check is not merged.
  - *System:* Test the pipeline on two small hand-written reference repos and larger public repos of known size and results, including exceptions in use-cases (private, no Python, \> 1,000 files, rate limited, cache expired). The malicious test repo ensures nothing analyzed is executed. Measure time to ingest, search, and render up to 1,000 files. For each reference repo, write down the expected imports, symbols, and reading order by hand before the first run, then compare with output. So far, ᴄɪ checks search and the ᴀᴘɪ against two small hand-built references; other system tests start once ingestion and the analyzer are built.
  - *Usability:* Unaffiliated students test the product in week 4, trying to perform one task set independently. In weeks 7–8, participants do two tasks with GitHub search and two with RepoLens. Measure *time spent to reach the right file* and *number of irrelevant files opened*; also survey. In week 8, a participant clones and builds the project using the ʀᴇᴀᴅᴍᴇ.
Bugs are reported in GitHub Issues, labeled by component affected, with a description of the problem, reproduction steps, triggering repo, and commit hash.
### Documentation plan
The ʀᴇᴀᴅᴍᴇ describes setup, testing, usage, and contribution (*validated with week 8 outside reviewer*). A small dev guide in the repo notes architecture and code conventions, referenced to this document. FastAPI auto-generates the ᴀᴘɪ documentation. The app itself includes error messages, searching hints, and a small user guide on the landing page.
## Software architecture\[image\]
Client-server system with a pipeline backend. React client talks to a FastAPI backend over ʀᴇꜱᴛ, which analyzes a repo once (ingest, parse, resolve, store for later requests). Each stage sits behind an interface for modularity/extensibility.
### Components
  - *Web client:* ᴜɪ state for file explorer, interactive dependency map, search bar, ranked reading list, file detail panel, and GitHub source links.
  - *API layer:* FastAPI service that validates input, starts analyses, routes requests, and converts every failure into one structured error report. In the Docker image it also serves the built frontend from the same origin, with the ᴀᴘɪ under /api.
  - *Ingestion service:* Resolves branch or tag to a commit ꜱʜᴀ; downloads snapshot *without running repo code*; removes generated/vendored files; enforces 1,000-file limit.
  - *Analysis service:* Parses each file into imports (*classed as in-/external / unresolved*) & symbols, plus class members, docstrings and comments.
  - *Graph store:* Persists files, symbols, imports, and edges; answers neighbor/lookup queries.
  - *Search and ranking service:* Matches a query against filenames, symbols, class members, imports, docstrings and comments, ranks the results and writes a one-line reason for each file.
  - *Cache manager:* Keys results by (repository, ꜱʜᴀ), expires them after 24 hours and merges duplicate in-flight requests for the same key.
### Interfaces
Client to ᴀᴘɪ (ʀᴇꜱᴛ/ᴊꜱᴏɴ). All errors use the shape {code, message, hint}. A malformed analysis id gets 404 ANALYSIS\_NOT\_FOUND.
  - **POST /analyses with {url, ref?}:** Starts/reuses {analysisId, sha, status}.
  - **GET /analyses/{id}:** Status, progress, summary (files analyzed, excluded, unparsed)
  - **GET /analyses/{id}/graph:** Module groups, file nodes and import edges
  - **GET /analyses/{id}/files/{path}:** Detail panel data (symbols, internal and external imports, importers, source link)
  - **GET /analyses/{id}/search?q=:** Ranked reading list with a reason for each file
  - **GET /health:** {status: "ok"} while the graph store responds; used by the Docker health check
Between backend components, only GraphStore touches the database.
  - **RepoSource:** fetch(owner, repo, ref) returns Snapshot(sha, files). (*The ᴍᴠᴘ has only GitHubSource. Git hosts like GitLab can be added without changing other components.*)
  - **LanguageAnalyzer:** analyze(file) returns FileAnalysis(imports, symbols, members, comments, parse\_ok). The ᴍᴠᴘ has only PythonAnalyzer. FileAnalysis holds only plain records (imports, symbols, members, comments), so no ᴀꜱᴛ types leave the analyzer.
  - **ImportResolver:** classify(import, file, repoIndex) returns {kind, target}, where kind is internal, external, or unresolved.
  - **GraphStore:** save(analysis), get\_graph(id), get\_file(id, path)
  - **SearchService:** search(id, query) returns a list of RankedFile(path, score, reason) and reads only from GraphStore.
  - **Cache:** get(repo, ꜱʜᴀ), put(…), evict\_expired(). ᴀᴘɪ layer checks it before ingestion.
### Data
All data lives in one SQLite database (*single file, no separate server*). The dependency graph is the File rows plus the internal Import rows, which act as edges. Tables are STRICT, with CHECK constraints on columns that have a fixed set of values. A database from another schema version is rebuilt, since it is only a 24-hour cache. In Docker the file sits on a volume, so analyses survive restarts.
  - **Analysis:** id, repo, sha, status, created\_at, expires\_at, counts (analyzed, excluded, unparsed)
  - **File:** id, analysis\_id, path, module, parsed, line\_count
  - **Symbol:** id, file\_id, name, kind (function, class, variable), line
  - **Import:** id, file\_id, raw\_name, kind (internal, external, unresolved), target\_file\_id, target\_package
  - **Comment:** id, file\_id, line, text, kind (comment, docstring)
  - **Member:** id, file\_id, owner, name, kind (method, attribute), line
  - ***Not stored:**** repo source code (delete snapshot after parsing; view source on GitHub); credentials; user data. Delete rows after expires\_at. Don’t save partial/failed analyses.*
### Assumptions
  - Input is a public, Python-only Git repo on GitHub with ≤ 1,000 files after filtering.
  - *Static analysis of import structure is sufficient.* Runtime behavior is out of our scope.
  - Keyword matching over names, symbols, comments is good enough for feature search.
  - One backend instance, so a local SQLite file works as both store and cache.
  - Analysis is a one-time cost (target 3 minutes); all later steps read stored data in seconds.
### Architecture decisions and alternatives
1.  *SQLite instead of a dedicated graph ᴅʙ.*** **No setup; easy to test; one-hop queries (imports and importers) meet our timing targets. GraphStore lets us swap backends later.  
    *Alternative:* Neo4j. *Pros:* Multi-hop queries (within 3 imports of a file) are simple; graph algorithms are built in. *Cons:* Separate server to run, deploy, secure; harder for new devs to set up locally; heavy for graphs ≤ 1,000 files. Our queries are mostly one-hop.
2.  *Python ᴀꜱᴛ behind a LanguageAnalyzer interface.*** **In the standard library; accurate for Python. Set up this way, an extra language needs a new analyzer, not a rewrite.  
    *Alternative:* Tree-sitter for all parsing. *Pros:* One approach covers many langs. Tolerates syntax errors better. *Cons:* Heavier dependency; nodes less convenient than Python's typed ᴀꜱᴛ; import resolution still needs lang-specific rules, so it saves less than it seems.
## Software design
### Shared types
  - **RepoLensError**: Every failure is raised as this. Carries data on how and why the failure exists, like the error code. Shared across the whole codebase.
  - **Data types** (Snapshot, SourceFile, FileAnalysis, ImportRecord, SymbolRecord, ResolvedImport, RankedFile)**:** Passed between components for modularity. Holds plain data (no ᴀꜱᴛ nodes), so parser can change without touching other components.
### Backend layout
backend/repolens/  
├─ api/ FastAPI routes, request validation, error handling, production server  
├─ pipeline/ orchestrates one analysis from start to finish  
├─ ingestion/ repository download, filtering, limits  
├─ analysis/ parsing, import classification  
├─ graph/ SQLite persistence, graph queries  
├─ search/ matching, ranking, reason text  
├─ cache/ (repository, ꜱʜᴀ) cache, expiry, in-flight merging  
└─ common/ shared data types, error model
#### api (ᴀᴘɪ layer)
  - **Routes: **Defines the 5 endpoints (POST /analyses, GET /analyses/{id}, /graph, /files/{path}, /search). Contains no logic, only delegates to the proper service.
  - **URLValidator: **Checks input against github.com/\<owner\>/\<repo\> (or other supported platforms) and normalizes it. Run before any network calls.
  - **QueryValidator: **Trims searches; rejects empty, large, and whitespace-only input.
  - **ErrorHandler: **A FastAPI exception handler; takes an error, creates a RepoLensError.
#### pipeline (orchestration)
  - **AnalysisPipeline**: Runs one analysis in this order: cache lookup, resolve hash, download snapshot, filter, parse, handle imports, store/cache. Reports status continuously; failure at any stage discards partial data. Deletes snapshot when done.
  - **AnalysisStatus: **Tracks any queued, running, completed, or failed analysis. Read with an ᴀᴘɪ, GET /analyses/{id}.
#### ingestion (file ingestion)
  - **RepoSource:** Interface holding the data about a repo. You can get a snapshot of the codebase from an instance of this. (Designed as interface to support future Git hosts.)
  - **GitHubSource: **Implements RepoSource. Takes a branch/tag, matches it to a commit hash, and downloads the code at that hash. Never runs or builds that code. Enforces timeouts and size caps. Throws RepoLensError (e.g. rate limits, 404s).
  - **FileFilter: **Removes auto-generated files; keeps only necessary files in the snapshot.
  - **SizeGuard: **Enforces the 1,000-Python-file limit after filter by raising RepoLensError.
  - **SnapshotCleaner: **Deletes snapshot directory after a completion (success or error).
#### analysis
  - **LanguageAnalyzer: **Interface, for potential future language support.
  - **PythonAnalyzer: **Implements LanguageAnalyzer for Python, using the built-in ast module. Extracts imports, nested functions, classes, variables, class members, docstrings, comments. Any error marks the parse as false so that one bad file doesn’t halt analysis. Never runs any code.
  - **RepoIndex: **Built once per analysis. Maps module names and paths to files, to maximize lookup speed.
  - **ImportResolver: **Analyzes imports and marks if it is internal, external, or otherwise.
  - **StdlibCatalog:** List of standard module imports (to know if imports are external).
#### graph
  - **GraphStore: **This interface saves repo data post-analysis to the database.
  - **SqliteGraphStore: **Implements GraphStore on a single file. Write the analysis in one process, so that a failed analysis doesn’t lead to partial data.
  - **Schema/Migrations: **Defines schema tables: Analysis, File, Symbol, Import, Comment, Member. No migrations: a version mismatch rebuilds the database.
  - **ModuleGrouper: **Groups files into module nodes by proximity for a smaller map view.
#### search
  - **SearchService: **Interface lists RankedFile types, reading from GraphStore.
  - **QueryParser: **Splits a query into tokens, so multi-word queries can match on files.
  - **Matcher: **Finds response files by filename, symbol name, class member, import name, docstrings, or comments.
  - **Ranker: **Ranks candidate files based on the match with the query, and also accounts for each file’s position in the dependency graph. Produces a reading order.
  - **ReasonBuilder: **Justifies each result in one line, citing evidence. Gives a full match list.
#### cache (cache manager)
  - **Cache: **Stores past results, logged by (repo, ꜱʜᴀ). Treats expired entries as a cache miss. Logs any corrupted or unavailable data as a miss.
  - **Registry: **Keeps a map of running analyses on the same repo/ꜱʜᴀ.
  - **ExpiryJob: **Scheduled clearing, calling evict\_expired() on repo data cached for \> 24 hr.
### Frontend layout
frontend/src/  
├─ api/ typed ʀᴇꜱᴛ client  
├─ state/ app state (analysis, selection, search)  
├─ components/ ᴜɪ pieces  
└─ pages/ landing page, analysis page
  - **ApiClient: **Wraps ᴀᴘɪ endpoints; handles errors. Can cancel in-flight requests.
  - **AnalysisStore: **Holds the client’s status, including current repo, ꜱʜᴀ, analysis status, summary, selected file, module, and search results.
  - **RepoInputForm: **ᴜʀʟ input, which validates the ᴜʀʟ format before enabling analysis.
  - **ProgressIndicator: **Shows the current stage of analysis, with a cancel button.
  - **SummaryBar: **Shows files analyzed, excluded, and to-be-analyzed.
  - **FileExplorer: **A tree view of the analyzed files. Selecting a file syncs the map.
  - **DependencyMap: **Flow graph with module nodes that expand on click. Highlights selected files’ dependencies; dims unrelated nodes. Hands off to ListFallback.
  - **ListFallback: **Explorer and list view used when the map cannot render in 2 seconds.
  - **SearchBar: **Trims input or filters invalid queries.
  - **ReadingList: **Ranked results by position, path and reason. Provides a source link, and is limited to 20 results with a show more option.
  - **FileDetailPanel: **Shows path, module, symbols, internal/external imports and other information about the file. Provides a link to the source code.
  - **ErrorBanner: **Displays the message and hint from any structured/expected error.
## Coding guidelines
[*Google Python Style Guide*](https://google.github.io/styleguide/pyguide)*:* Enforce by *autolinter*, applied periodically, that parses each source file into an ᴀꜱᴛ to check for violations (e.g. naming convention, docstring presence, import ordering, function complexity).
[*Google TypeScript Style Guide*](https://google.github.io/styleguide/tsguide)*:* Clear rules on divisive code-review choices (e.g. named exports; const and let instead of var; avoid the any type). Enforce by running *ESLint* (parses each source file into an ᴀꜱᴛ to check for violations) and *Prettier* (configured to match guide's formatting) in GitHub Actions against every ᴘʀ; don’t merge failing code.
