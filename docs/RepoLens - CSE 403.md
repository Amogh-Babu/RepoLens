# **RepoLens: Project Proposal**

Members: Shashank Giridharan, Austin Elenzano, Levi Lenin, Abhinav Damarla, Amogh Babu, Dylan Maring

GitHub Link: [https\://github.com/Amogh-Babu/RepoLens](https://github.com/Amogh-Babu/RepoLens)

## **Team Info**

### **Roles**

* *Ingestion Engineer \- Austin Elenzano:* In charge of designing the downloading of a public GitHub repository at a given commit while preventing any code from being executed. Will also design filtration of auto-generated files, and caching results based on repository information.  
* *Analysis Engineer \- Shashank Giridharan:* Will implement the built-in Python AST parser for imports and symbol analysis, with the goal of making the system effectively determine if an import belongs to the same or external libraries.  
* *Graph Engineer \- Amogh Babu:* Works on the backend, designing the initial dependency graph schema. Also in charge of storing files, modules, imports, and other symbols in the graph database.   
* *Search Engineer \- Abhinav Damarla:* In charge of creating the Python API for searching the repository over filenames, symbols and comments. Also works on the query ranking order, reading order suggestion, and other logic.  
* *Frontend Engineer \- Levi Lenin:* Works on building the React application that includes a file explorer, interactive dependency graph, and search bar, with intuitive links to the code itself.  
* *Product Manager & Evaluation Lead \- Dylan Maring:* Sets up milestones and progress reporting, and keeps this document/README updated. During testing phases, also in charge of writing test plans, handling deployment, and evaluation with students.

### **Project artifacts**

* GitHub repository: [Github](https://github.com/Amogh-Babu/RepoLens)   
* Task tracker: TODO  
* Pitch slides: [Slides](https://docs.google.com/presentation/d/1lyTGd5yCl5d6p6VrLaf48r3ta-7MyBIR/edit?usp=sharing&ouid=105870811458408920199&rtpof=true&sd=true)   
* Deployed demo: TODO

### **Communication channels**

* *Team chat*: \*On Whatsapp\*  
* *Meeting time*: Tuesday, 1:30 to 2:20 pm: we will have our Team Meeting. Thursday, 1:30 to 2:20 pm: we will have our project meeting with the project manager.   
* *Code management:* Coding and task assignment will be organized through GitHub issues and pull requests. A pull request requires a review by another teammate to merge into main.   
* *Documentation*: This document gets collaboratively edited and updated as changes are made.

## **Product Description**

**Abstract**

RepoLens is a web-based application that helps users understand GitHub repositories by creating an interactive visual dependency map and recommending readings for specific features. A new contributor or amateur can search for key terms, read related files, and use the links to go to the source code. Our project team will consist of six people, and we intend to complete a minimum viable product within nine weeks. This MVP will specifically focus on Python repositories. RepoLens asserts that the combination of an informative dependency map and easily digestible recommendations will allow a new user to find all relevant code rapidly.

**Goal**

RepoLens is designed with the goal of helping coders, whether students or professionals, who are new to a specific project team or open-source project. It is focused on helping these users answer two questions, that being “How are these files related?” and “Where do I start?”. For example, the developer who uses this tool to study a login workflow on some application will learn about the authentication path, the related services, and the user model the framework depends on. RepoLens will then suggest the order in which these files should be studied, and justify this ordering. While not all aspects of the runtime behavior can be covered, things such as import dependencies will be marked.

**Current Practice**

Currently, README files, repository-wide searches, and manual code inspections are the methods of onboarding. GitHub allows a user to location the definition and all usage of symbols. An existing tool known as Sourcegraph provides greater search and navigation options, including between repositories. CodeBoarding, another existing tool, has interactive code structure maps, making use of static analysis and LLMs. The existence of these tools proves that a market for improved code navigation, visualization, and onboarding tools already exists. We differentiate ourselves by narrowing the scope of the problem, that being onboarding assistance that helps the user choose the order of file analysis, in relation to some feature. Thus, RepoLens can be more effective for users trying to onboard to make changes for one feature in large repositories.

**Novelty**

RepoLens is focused on individual features, rather than the entire repository. We develop reading/studying techniques for the user, specifically based on the part of the code they want to learn. A search gives users a list of the files based on their relevance to the topic, information about known dependencies, a suggested reading order, and reasoning. Users can now easily look into the code without having to rely on black-box or brief explanations, which are present in other tools. This process uses existing parsing and graphing mechanisms, with the core idea relying on the fact that describing an efficient reading process will be simpler for beginners, as compared to them gathering information and context on their own.

**Effectiveness and Evidence of Value**

Our primary target audience would be students and contributors who often have to pick up work in unknown repositories, such as company repos or open-source software. To test if RepoLen’s prescribed reading order is effective, we will conduct a user study with classmates in weeks 7-8. Participants will complete two tasks on unfamiliar Python repositories. The first is using standard tools, like GitHub code search and manual inspection, and the other using RepoLens. We will evaluate the effectiveness of the product against the baseline using two qualitative metrics. Time to identify, the number of seconds to reach the correct file/dependencies, and path efficiency, counting the number of irrelevant files before reaching the goal. We will conduct a survey after these tasks, asking about feature comprehension and cognitive load from the user. This will allow us to prove if our reading recommendations reduce time and improve comprehension.

**Technical Approach and Scope**

The MVP that the team will create by the end of project deadline will take a URL of a public Git repository, and will analyze a chosen commit. A built-in Python Abstract Syntax Tree, also known as an AST, will parse the imports and symbol names in the project through a language-neutral analyzer interface, so the parser can be replaced later without rewriting the app. A resolver will determine if any given import is internal or an external library. These symbols and artifacts will be stored in a graph database. A Python API will feed the frontend with a file explorer, an interactive graph, and a search bar. A user will be able to use this search bar to query the repo for any specific filenames, symbols, etc.. An algorithm will calculate the priority ranking for each file, giving reasons for each suggestion. The outputted reading order will be a suggestion, not the repository’s order of execution. Cached data will be determined based on the given URL and chosen commit. The team will implement the ingestion, parsing, graph schemas, and a general use API interface during weeks 1-2. From weeks 3-6, the team will work on implementing and iterating on the codebase analyzer, mapping, search feature, and source data linking. Finally, user evaluation, error cleanup, and deployment will be conducted during weeks 7-9. Git history and broader summaries will be considered as stretch goals. Some potential challenges will be handling cross-layout imports, synchronizing and creating graphs, and UI development for the best user experience.

### **Major features**

1. *Repository ingestion by URL and commit (P0)*: The user should be able to provide a public Git repository URL and a specific commit, and RepoLens should process it without execution of the code. All auto-generated files are removed from the analysis, and important information is cached.  
2. *Python import and symbol extraction (P0)*: For each file in the codebase, the analysis will classify all imports as internal or external libraries, and create a list of symbols.  
3. *Interactive dependency map (P0)*: The UI will allow for easier file browsing, displaying an interactive graph of all the files, grouped by module names and similarity.  
4. *Feature search with ranked reading list (P0)*: Users can enter keywords, and RepoLens will query the codebase for the term, looking at filenames, symbols, imports, and general comments. The frontend will display the highest priority results first.  
5. *Source code links (P1)*: Each file/symbol contains a link to the exact file in the repository  
6. *Proper processing of unsupported inputs (P1)*: Invalid inputs, like non-public, non-Python, large codebases, or invalid links, won’t crash the app and provide explanations on why the input is incorrect

### **Test Plan**

(Just bullet points for now, finalize tomorrow)

* Test-automation infrastructure  
  * Frontend  
    * ???  
  * Backend  
    * Pytest  
* Justification  
  * ???  
  * Pytest: Cleanest and simplest test interface for most python programs  
* How to add  
  * ???  
  * Backend: Create test\_name\_here.py file, put in test folder for your feature.  
* CI service  
  * GitHub Actions, is linked to project through GitHub and came pre-installed since our project is being built/stored in GitHub  
* Why this CI:  
  * Didn’t have to do any additional work to implement, less possible failure points and more manageable workload  
* Which tests executed in CI build  
  * Linters \+ Unit tests written per-feature  
* Which actions trigger a CI build?  
  * Pull, push, merge, etc.

### **Stretch goals**

1. Support for a second language (P2).  
2. Support for additional Git hosts such as GitLab (P2).  
3. Private repositories through GitHub sign-in (P2).  
4. Git history for version analysis (P2).  
5. Automatically generated file summaries as text (P2).

# **Use Cases**

1. **Case 1: Analyze a public repository by URL and commit (Merged with cases 5 and 6\)**  
   1. Actors:  
      1. Primary: A new contributor, such as a student or open-source newcomer, who uses RepoLens in a browser.  
      2. Secondary: GitHub, which hosts the repository snapshot and the RepoLens backend, which manages ingestion, analysis and graph storage.  
   2. Trigger:  
      1. The user types a GitHub repository URL optionally adds a commit branch or tag. Then clicks the Analyze button.  
   3. Preconditions:  
      1. The user has a browser and a working internet connection.  
      2. The repository is public hosted on github.com. Contains Python source files.  
      3. After filtering the repository contains no than 1,000 Python files, which is the MVP limit.  
      4. GitHub can be reached.  
   4. Postconditions (success scenario):  
      1. The repository is analyzed at a resolved commit SHA and the result is cached under (repository, SHA) for 24 hours.  
      2. The graph store contains every analyzed file, module, import (marked as internal or external) and symbol.  
      3. The user sees the file explorer, the dependency map, the search bar and a summary that lists files analyzed files excluded and files that could not be parsed.  
      4. No code from the repository is executed.  
   5. Steps (success scenario):  
      1. The user pastes a repository URL into the input field and may optionally enter a commit branch or tag.  
      2. The frontend checks that the URL matches the format https\://github.com/\<owner\>/\<repo\> and then enables the Analyze button.  
      3. The user clicks Analyze. The frontend displays a progress indicator that shows the stage.  
      4. The backend looks up (repository, commit) in the cache. Finds no entry.  
      5. The backend resolves the requested commit to a SHA. If no commit was supplied it uses the head of the default branch.  
      6. The backend downloads a source snapshot at that SHA from GitHub as files and it does not run any repository code, hooks or build scripts.  
      7. The backend removes auto-generated and vendored files—such as generated protobuf modules build output, node\_modules and \_\_pycache\_\_—and counts them as excluded.  
      8. The backend parses each remaining Python file with the Python AST parser, extracting imports and symbols.  
      9. The resolver classifies each import as internal if it resolves to a file in the repository or external if it is part of the library or a third‑party package.  
      10. The backend stores the files, modules, imports and symbols in the graph store. Caches the result for 24 hours.  
      11. The frontend replaces the progress indicator with the explorer, the map, the search bar and the summary.  
   6. Extensions and variations:  
      1. 2a. If the URL ends with a trailing slash, a.git suffix or a /tree/\<branch\> path the frontend normalizes it to the base repository URL. Uses the branch as the requested commit.  
      2. 4a. If there is a cache hit for (repository, SHA) steps 6 to 10 are skipped. The result loads from the cache. The summary indicates the age of the cached analysis.  
      3. 4b. If another user is already analyzing the repository, SHA) this request joins the running analysis instead of starting a new one.  
      4. 5a. If the user supplied a branch or tag the backend resolves it to a SHA and the summary displays that SHA so the analysis is reproducible.  
      5. 8a. If a file has a syntax error the file is marked as unparsed still appears in the explorer with no dependency edges and is counted in the summary. Analysis of the remaining files continues.  
      6. 9a. If an import cannot be resolved as internal or as a known library—such as a dynamic or relative import that points outside the repository—the import is marked as unresolved and shown in the file’s detail panel.  
      7. 3a. If the user clicks Cancel or closes the tab during analysis the backend discards results and caches nothing for that run.  
   7. Exceptions (failure conditions and scenarios):  
      1. URL or a host other than github.com: the frontend blocks submission shows the expected format with an example and sends nothing to the backend. The state remains unchanged. The input is preserved for editing.  
      2. Repository not found or private: the backend reports that the repository does not exist or is not public. It states that this version of RepoLens supports public GitHub repositories and that other Git hosts are planned. The state remains unchanged and nothing is cached; the input is preserved.  
      3. Commit, branch or tag not found: the backend reports which reference failed and offers to analyze the default branch. Nothing is cached.  
      4. No Python files after filtering: the backend explains that RepoLens supports only Python repositories, in this version. Nothing is cached.  
      5. Than 1,000 Python files: the backend rejects the repository reports the file count and the limit and suggests a smaller repository. Nothing is cached.  
      6. GitHub rate-limited: backend discards the partial download and returns an error with a Retry button. State: nothing cached.  
      7. Unexpected analysis failure or timeout: backend discards graph data so that no half-analyzed repository is cached and frontend shows a generic error with a Retry button. State: nothing cached details logged for the team.

2. **Case 2: Search for a feature and get a ranked reading list (Merged with case 4\)**  
   1. Actors:  
      1. Primary: New contributor trying to learn how one feature (for example authentication) works.  
      2. Secondary: RepoLens backend (search and ranking over the cached graph).  
   2. Trigger:  
      1. User types a keyword or phrase into the search bar and presses. Clicks Search.  
   3. Preconditions:  
      1. Use Case 1 completed for the loaded (repository, SHA) and cached analysis has not expired (24 hours).  
      2. The explorer, the map and the search bar are visible.  
   4. Postconditions (success scenario):  
      1. User sees a ranked reading list. Each entry shows position, file path, a reason for its rank and link to the source.  
      2. Files that match the query are highlighted on the map and other files are dimmed.  
      3. Stored graph and cache are unchanged. List reflects the loaded commit.  
   5. Steps (success scenario):  
      1. User types a query such as "authentication" into the search bar. Submits it.  
      2. Frontend trims the query. Sends it to backend with repository and SHA.  
      3. Backend matches the query against file names, symbols, imports and comments in graph.  
      4. Backend ranks matching files by relevance to query and by role in dependency graph so that files other results depend on are suggested earlier. Result is a reading order, not an execution order.  
      5. For each file backend generates one-line reason that cites evidence (for example "defines login\_user; imported by 4 other matching files").  
      6. Backend returns ordered list targeting response within 1 second for repository.  
      7. Frontend renders reading list with highest-priority files  
      8. Frontend highlights matching files on dependency map. Dims the rest.  
      9. User reads list and selects an entry to inspect it (continues in Use Case 3).  
   6. Extensions and variations:  
      1. 1a. User enters words: backend treats them as separate terms and files that match more terms rank higher.  
      2. 1b. User submits a query before previous results return: frontend ignores late response from earlier query so list always matches latest query.  
      3. 1c. User clears search bar: reading list closes highlighting is removed and map returns to default view.  
      4. 3a. Query matches no files: frontend shows "No files match '\<query\>'" with suggestions (try a word or a function or class name). Map keeps default view.  
      5. 6a. Than 20 files match: frontend shows 20 and a Show more control that loads the rest.  
      6. 7a. User expands an entrys reason to see every matching symbol, import or comment in that file.  
   7. Exceptions (failure conditions and scenarios):  
      1. whitespace-only query: frontend does not send request and shows inline hint to enter a keyword. State: unchanged, previous results kept.  
      2. Query longer than 200 characters: frontend rejects it with a message stating the limit. State: unchanged previous results kept.  
      3. Cached analysis expired or was evicted: backend reports analysis is no longer available and frontend offers Re-analyze with URL and commit (Use Case 1). State: current view stays on screen. No results are shown for new query.  
      4. Backend error or no response within 5 seconds: frontend shows error banner with Retry button. State: previous results and highlighting are. Stored graph is unaffected.

   

3. **Case 3: Explore the dependency map and open a file’s source (Merged with case 4\)**  
   1. Actors:  
      1. Primary: New contributor trying to understand how files in a repository relate to each other.  
      2. Secondary: GitHub (serves the source file the user opens).  
   2. Trigger:  
      1. The user clicks a module group or file on the dependency map or a file in the explorer or an entry in the reading list.  
   3. Preconditions:  
      1. Use Case 1 has finished for the loaded repository and SHA and the analysis is still cached.  
      2. The map is rendered. Search results (Use Case 2). May not be present.  
   4. Postconditions (success scenario):  
      1. The selected file is highlighted, with the files it imports and the files that import it.  
      2. A detail panel shows the file’s path, module, symbols, internal imports, external libraries and the files that import it.  
      3. The file’s source is opened in a browser tab at the analyzed commit on github.com.  
      4. The RepoLens tab retains its repository, search results and selection so the user can keep exploring.  
   5. Steps (success scenario):  
      1. The user sees the dependency map with files grouped into collapsed module nodes.  
      2. The user clicks a module node. It expands to show its files and the import edges between them.  
      3. The user clicks a file node.  
      4. The frontend marks the file as selected highlights its dependencies and dependents and dims unrelated nodes. External libraries are listed in the detail panel not shown as nodes.  
      5. The detail panel opens with the file’s path, module, symbols, internal imports, external libraries and an "imported by" list.  
      6. The user clicks "Open source" in the panel.  
      7. The browser opens https\://github.com/\<owner\>/\<repo\>/blob/\<SHA\>/\<path\> in a tab, pinned to the commit that was analyzed.  
      8. The user returns to the RepoLens tab. The selection, expanded modules and search results are still there.  
   6. Extensions and variations:  
      1. 1a. The user zooms, pans or drags nodes: the map. A Reset view button restores the default layout.  
      2. 3a. The user selects the file from the explorer tree instead: the map expands the file’s module, pans to the node and selects it.  
      3. 3b. The user selects the file from a reading list entry: the same selection. The panel shows the file’s position and reason from the list with a "Next in reading order" button.  
      4. 5a. The user clicks a file in the panel’s "imports" or "imported by" list: the selection moves to that file. The panel updates.  
      5. 6a. The user clicks a symbol in the panel: the opened GitHub link includes the line number of the symbol’s definition.  
   7. Exceptions (failure conditions and scenarios):  
      1. The selected file is not parsed because of a syntax error: the panel shows a warning that dependency information's unavailable lists no imports and still provides the source link. State: the selection. The file has no edges on the map.  
      2. The selected file has no imports and no importers: the panel states this plainly and the map shows the node alone. This is not treated as an error.  
      3. The map cannot render within the 2 second target or the browser cannot draw it: the frontend falls back to the explorer and a list view with a message and every file stays selectable and linkable. State: the analysis data is intact.  
      4. The browser blocks the tab: the frontend shows the source URL as a visible link the user can click directly. State: unchanged.  
      5. GitHub returns a 404 because the repository was deleted, made private or the commit was removed: GitHub’s error page appears in the tab. RepoLens cannot detect this in advance so the panel always displays the path. Commit SHA so the user can locate the file another way. State: the RepoLens tab is unaffected.  
      6. The cached analysis expires while the user was exploring: the next selection shows an "analysis expired" message, with Re-analyze (Use Case 1). The current map stays visible but read-only until the user re-analyzes.

# **Non-functional Requirements**

1. *Performance & Latency:* We set a baseline goal as RepoLens being able to take a Python repository up to 1000 files, equivalent to about 100,000 lines of code, and complete initial ingestion, symbol parsing, and dependency construction in 3 minutes. Once these initial processes have been completed, the codebase state is cached, and search results should appear in 1 second, with the graph rendering in 2 seconds. We would verify the completion of this requirement by running RepoLens multiple times on repositories of increasing sizes, up to 1,000 files, ensuring that the initial and cached processes are at the baseline  
2. *Security & Privacy:* To ensure security, RepoLens will only conduct code analysis through static parsing, using ASTs, but never actually run code from the inputted repositories. Additionally, the system will never store credentials or personal information, being restricted to public repositories. Cached repositories will only be stored for 24 hours to help with this goal, being deleted after this time. We will validate this requirement by reviewing the code of RepoLens, ensuring there are no calls to *exec* or *import* in regards to any analyzed files, and submitting a test repository with malicious code, that if executed, would access internal data, and ensure no side effects would happen. We would also test that all malformed URLs and hosts that this version does not support are rejected with a clear message.   
3. *Usability & Accuracy*: A new RepoLens user can intuitively pick up all the features provided, like symbol/feature search, reading list, and file navigation in 2 minutes. Additionally, the system itself should classify internal, external, and other dependencies 95% of the time, and also be able to handle syntax errors without crashing or other errors. We will validate by conducting user surveys/studies, timing a user on how long it takes for them to pick up the system. We will also run the parser on broken code to ensure no errors are raised.

# **External Requirements**

1. *Robustness:* RepoLens will anticipate invalid input and handle them without crashing. It will then alert the user what next steps are to solve the problem/issue with the input. This includes malformed, unsupported-host or non-Python codebase links, or empty or large repositories. We will maintain a list of potential error cases, write tests for them, and ensure the backend returns an organized error report.  
2. *Accessibility:* By the end of the project deadline, RepoLens will be accessible for anyone to open on a browser. No account creation or app installation will be required to use this tool. The user will be able to make use of RepoLens on any device with a modern browser and internet connection.  
3. *Development:* To ensure an easy build and development process, the codebase will include extensive setup and development instructions in the README, with the goal of a new developer being able to build and run the system locally with just this information, and without help from the team. This includes dependency requirements, server setup, documentation of the architecture, with a stretch goal of a containerized setup using Docker for very simple setup.  
4. *Scope:* The scope is limited to a MVP, tuned to what six people could feasibly build in nine weeks. Thus, RepoLens only covers Python repositories, with version control analysis, broader summaries, and different language support being left as stretch goals. We will achieve this MVP through designing the product modularly, so developers can work independently for maximum efficiency.

# **Team Process**

Our development will be done in one-week cycles. Every Tuesday, we will hold meetings where we will go through the work already done, talk about any issues, and divide tasks for the week. On Thursdays, we will hold meetings where we will check our progress and talk about any issues. We will communicate using WhatsApp and make important decisions in GitHub issues or in this document.

GitHub will be used for managing our code, assigning tasks, and reviewing any changes that we will be doing. Each task will have its owner and the list of things which should be done in order for it to be completed. Each member will work on a different branch and his or her pull request will be reviewed by a teammate before merging.

The reason we plan to use the built-in Python AST parser is that it allows us to analyze Python code without executing it. To avoid depending on it too heavily, the parser sits behind a LanguageAnalyzer interface and the repository host behind a RepoSource interface, so either can be replaced, for example to add a second language or GitLab support, without rewriting the rest of the system. FastAPI will integrate the frontend and the backend together and offer API documentation. React will enable browser-side capabilities while React Flow will help us design the dependency graph. The graph storage will be chosen in the first week depending on our queries and settings.

Tests for the backend and for important functionality of the frontend will be performed with the help of pytest. GitHub Actions will perform testing and building on the pull request stage. The README will describe installation, execution and contribution process. Docker will be an option until the basic features are implemented.

**Why we chose these roles**

Austin Elenzano: Austin’s familiarity with Github repositories will be useful in the ingestion of the repositories in the system. He will guarantee the transfer of the necessary files in a safe manner to the rest of the system.

Shashank Giridharan: Shashank’s knowledge in building Python applications and back-end systems is suitable for the role of analysis. He can utilize his knowledge in import extraction and symbol extraction, testing the parser and integration of its output with other components of the back-end.

Amogh Babu: Amogh’s familiarity with data structures is applicable in the role of graph. He will utilize his knowledge in organizing the repository relationship and making it searchable and visible.

Abhinav Damarla: Abhinav’s experience or interest in algorithms makes him suitable for the roles of search and reading recommendation. This task involves developing ranking heuristics and evaluating its effectiveness.

Levi Lenin: Levi’s experience in front-end development is appropriate for the role of front-end. He will utilize his knowledge in presenting the back-end’s analysis to the user through user-friendly interface.

Dylan Maring: Dylan’s experience in project planning will be suitable for the role of product management and evaluation.

This assignment is based on our present day assignment pattern. During the project kick off stage, each individual team member will be asked to confirm his/her expertise and interests in order to justify his/her role in the project.

**Major Issues**

Incorrect import analysis: There are different structures used in Python projects. Incorrect relationships can confuse users. We will test our tool against manual examples, notify about unresolved imports, and describe unsupported patterns.

Uninformative maps or reading paths: It can be difficult to navigate around too many entries in the map, or search results can refer to incorrect files. We will organize files in modules, display additional information if necessary, and provide explanations for recommendations. Testing will be performed externally to help us find confusing results early.

Problems with GitHub or large repositories: Network issues, rate limiting, and large file downloads can hinder the analysis process. We will implement timeout handling, enforce the limit on repositories, cache results, and send informative error messages. Test repositories locally will allow us to develop without connecting to GitHub.

Integration issues: Different components can have different identifiers or responses. We will agree on common formats early, discuss changes with our teammates, and perform testing of the entire process starting from week 3\.

#### **Risk Assessment**

1. **Risk 1:** Keyword search gives unhelpful reading lists (likelihood: high, impact: high): However, the usefulness of any correctly drawn graph becomes meaningless when searches such as “authentication” produce the wrong set of files. This search is limited to matching filenames, symbols, imports, and comments, and we have not yet tested it on actual repositories. In order to gauge this early on, Abhinav and Shashank will label the correct set of files for some queries on three different repos by week 4, and compare our results in terms of the precision of our top five against a basic grep filename baseline.  
2. **Risk 2:** Import classification fails on real project layouts (medium, high): Source layouts, namespaces packages, re-exports from init.py, and dynamic imports cannot be solved statically, and we have only tried to test some hand-crafted examples until now \[updated with real repository tests\]. We will generate test data sets for each source layout, and check manually some real repositories, so that we can come up with a percentage of accuracy before measuring week 7 against our 95% goal. An increase in the percentage of unresolved imports will mean that we missed some patterns.  
3. **Risk 3:** Parallel components don’t fit together (medium, high): Six different people code their own module behind five different interfaces, so even small issues, such as path formatting, may break the entire pipeline process. The FastAPI OpenAPI schema is considered to be the source of truth for our project, and any changes need to be initiated by creating a GitHub issue and gaining agreement from another team member. From the third week, we perform an end-to-end test of our small repository via CI. If the test fails or no GitHub issue exists about changing the schema, there is drift.  
4. **Risk 4:** GitHub limits or large repos break the time budget (medium, medium). Rate limiting and repos close to 1,000 files might go beyond the 3-minute ingestion limit. Rather than downloading files individually, we will just have to download one archive and limit the file size and timeouts, with cache depending on (repo, SHA). Austin will benchmark the speed of ingestion for bigger and bigger repos, starting week 4\. If we fail, we will either parallelize the parsing, cut down the number of files, or use a token from the server side via the environment variable.  
5. **Risk 5:** The map is too slow or cluttered (medium, medium): React can sometimes struggle with hundreds of nodes so what we will do to combat this is to start with collapsed module nodes and keep external libraries outside the graph initially. Levi will benchmark a 1,000-file repo against the 2-second target by week 5\. And then if it fails, we will use the previously described explorer and list-view fallback.  
   

**Project Schedule**

| Milestone | Tasks | Effort | Depends on |
| ----- | ----- | ----- | ----- |
| M1: Pipeline prototype (wk 2\) | Download by SHA (Austin); parse sample repos (Shashank); SQLite schema and save/load (Amogh); search output format and basic matching (Abhinav); screen prototypes (Levi) | 8 | Week 1 schema and input rules |
| M2: One use case end to end (wk 3\) | File filtering and size limits (Austin); relative imports and unparsable files (Shashank); graph and file-detail endpoints (Amogh); ranked results with reasons (Abhinav); real repo in explorer and map (Levi) | 5 | M1 |
| M3: First public version (wk 4\) | Cache reuse (Austin); import verification (Shashank); module groups and source links (Amogh); reading paths (Abhinav); file panel and GitHub links (Levi); walkthrough with outside students (Dylan) | 6 | M2 |
| M4: MVP checklist (wk 6\) | Error and cache-expiry tests (Austin); real-repo accuracy and syntax-error checks (Shashank); graph and source link validation (Amogh); comment search, no-result handling, ranking checks (Abhinav); loading, empty, and error screens plus map benchmark (Levi); acceptance checklist (Dylan) | 8 | M3 |
| M5: Study complete (wk 7-8) | Measure timings and accuracy and fix issues (all engineers); comparison study and README build test (Dylan) | 8 | M4 |
| M6: Release (wk 9\) | Final tests and limitations (Austin, Shashank); interface docs and final tests (Amogh, Abhinav); test deployed interface (Levi); confirm public URL and finish docs (Dylan) | 5 | M5 |

**Test Plan and Bugs**

We test what is required to be accurate or reliable in the product, which includes import accuracy, ranking accuracy, safe ingestion, invalid inputs handling, and time-related targets. There are clear measures for those, so the test of those parts ensures the coverage of requirements.

* **Unit testing**: Each owner creates pytest tests for the own component (import classification on fixtures, handling of broken files, URL validation, cache validity, ranking order). They are performed by GitHub Actions on each pull request; failing PRs will not be merged.  
* **System testing**: The whole pipeline is tested on two small hand-written reference repositories and on larger public repositories of known size and results, including the exceptions in use-cases (private repository, repository without Python files, more than 1,000 files in the repository, rate limit exceeded, cache is expired). The malicious test repository verifies that nothing from the analyzed repository is executed. We measure the time of ingestion, search, and rendering process up to 1,000 files. For each reference repository we write down the expected imports, symbols and reading order by hand before the first run, then compare them with the RepoLens output.  
* **Usability testing**: Unrelated students test the product in week 4, trying to perform one of tasks independently. In weeks 7-8 the participants complete two tasks using GitHub search and two using RepoLens. We measure the time spent to the right file and number of irrelevant files opened by the user; a survey is also included. In week 8, an unrelated person clones the repository and builds the project using the README.

The bugs are reported in the GitHub Issues, with the label according to the part affected, description of the problem, reproduction steps, triggering repository and commit hash.

**Documentation Plan**

Four aspects will be provided. The README contains information about setup, testing, usage, and contribution; it is confirmed by the week 8 outside reviewer test. A small developer guide in the repository contains information about architecture and code conventions that are referenced to this document rather than copied here. The API documentation is generated automatically by FastAPI. The user documentation is included in the application itself in the form of error messages and searching hints and in the form of a small user guide on the landing page. Dylan is responsible for documentation.

**Software architecture**

## **Overview**

RepoLens is a client-server system with a pipeline backend. A React client talks to a FastAPI backend over REST. The backend analyzes a repository once (ingest, parse, resolve, store) and serves every later request from the stored result. Each stage sits behind an interface, so the source host (GitHub) and the language (Python) can be replaced without rewriting the other components. The Software design section details the classes inside each component.

![][image1]

## **Components**

* **Web Client:** File explorer, interactive dependency map (React Flow), search bar, ranked reading list, file detail panel and links to GitHub source. Holds only UI state.  
* **API Layer:** FastAPI service that validates input, starts analyses, routes requests and converts every failure into one structured error report.  
* **Ingestion Service:** Resolves a branch or tag to a commit SHA, downloads a snapshot without running any repository code, removes generated and vendored files, and enforces the 1,000-file limit.  
* **Analysis Service:** Parses each file into imports and symbols, then classifies each import as internal, external or unresolved.  
* **Graph Store:** Persists files, symbols, imports and dependency edges, and answers neighbor and lookup queries.  
* **Search and Ranking Service:** Matches a query against filenames, symbols, imports and comments, ranks the results and writes a one-line reason for each file.  
* **Cache Manager:** Keys results by (repository, SHA), expires them after 24 hours and merges duplicate in-flight requests for the same key.

## **Interfaces**

Client to API (REST/JSON). Every error uses one shape: {code, message, hint}.

* **POST /analyses with {url, ref?}:** starts or reuses an analysis and returns {analysisId, sha, status}.  
* **GET /analyses/{id}:** status, progress stage and summary (files analyzed, excluded, unparsed).  
* **GET /analyses/{id}/graph:** module groups, file nodes and import edges.  
* **GET /analyses/{id}/files/{path}:** detail panel data (symbols, internal and external imports, importers, source link).  
* **GET /analyses/{id}/search?q=:** ranked reading list with a reason for each file.  
* 

Between backend components. Only GraphStore touches the database.

* **RepoSource:** fetch(owner, repo, ref) returns Snapshot(sha, files). The MVP has only GitHubSource. Other Git hosts such as GitLab can be added without changing other components.  
* **LanguageAnalyzer:** analyze(file) returns FileAnalysis(imports, symbols, comments, parse\_ok). The MVP has only PythonAnalyzer, built on the ast module. FileAnalysis holds only plain records (imports, symbols, comments), so no ast types leave the analyzer and replacing ast, for example with tree-sitter, changes one class.  
* **ImportResolver:** classify(import, file, repoIndex) returns {kind, target}, where kind is internal, external or unresolved.  
* **GraphStore:** save(analysis), get\_graph(id), get\_file(id, path).  
* **SearchService:** search(id, query) returns a list of RankedFile(path, score, reason) and reads only from GraphStore.  
* **Cache:** get(repo, sha), put(...), evict\_expired(). The API layer checks it before ingestion starts.

## **Data**

All data lives in one SQLite database (a single file, no separate server). The dependency graph is the File rows plus the internal Import rows, which act as edges.

* **Analysis:** id, repo, sha, status, created\_at, expires\_at, counts (analyzed, excluded, unparsed).  
* **File:** id, analysis\_id, path, module, parsed, line\_count.  
* **Symbol:** id, file\_id, name, kind (function, class, variable), line.  
* **Import:** id, file\_id, raw\_name, kind (internal, external, unresolved), target\_file\_id, target\_package.  
* **Comment:** id, file\_id, line, text.

Not stored: repository source code (the snapshot is deleted after parsing and source is viewed on GitHub), credentials and user data. Rows are deleted when expires\_at passes. Partial or failed analyses are never saved.

## **Assumptions**

* Input is a public Git repository, Python only, with at most 1,000 Python files after filtering. The MVP implements and tests GitHub URLs through GitHubSource, and no other component depends on the host.  
* **Static analysis is enough:** import structure approximates what to read first, and runtime behavior is out of scope.  
* Keyword matching over names, symbols and comments is good enough for feature search. This is our main product risk.  
* One backend instance, so a local SQLite file works as both store and cache.  
* Analysis is a one-time cost (target 3 minutes). Everything after it reads stored data (search under 1 second, graph render under 2 seconds).

## **Architecture decisions and alternatives**

1. ### **SQLite instead of a dedicated graph database.** We chose SQLite because it needs no setup, is easy to test, and one-hop queries (imports and importers) meet our timing targets. The GraphStore interface lets us swap the backend later.

   1. ### **Alternative: Neo4j.**

* **Pros:** Multi-hop queries (everything within 3 imports of a file) are simple, and graph algorithms are built in.  
* **Cons:** It is a separate server to run, deploy and secure, harder for new developers to set up locally, and heavy for graphs of at most 1,000 files. Our queries are mostly one-hop.

2. ### **Python ast behind a LanguageAnalyzer interface.** We chose ast because it is in the standard library and accurate for Python. Keeping it behind LanguageAnalyzer means a second language needs a new analyzer, not a rewrite, which addresses the feedback about over-reliance on Python's AST.	

   1. ### **Alternative: tree-sitter for all parsing.**

* **Pros:** One approach covers many languages, and it tolerates syntax errors better.  
* **Cons:** It is a heavier dependency, its nodes are less convenient than Python's typed AST, and import resolution still needs language-specific rules, so it saves less than it appears to.

**Software Design**

**Shared Types**

* **RepolensError**: Every failure is raised as this type. Carries data on how any why the failure exists, like the error code, and is shared across the entire codebase.  
* **Data Types:** (Snapshot, SourceFile, FileAnalysis, ImportRecord, SymbolRecord, ResolvedImport, RankedFile). These are datatypes that are passed between all components, allowing modularity. They hold only plain data and no ast nodes, so the parser can be replaced without touching other components.

**Backend Layout**

backend/repolens/  
├── api/          FastAPI routes, request validation, error handling  
├── pipeline/     orchestrates one analysis from start to finish  
├── ingestion/    repository download, filtering, limits  
├── analysis/     parsing and import classification  
├── graph/        SQLite persistence and graph queries  
├── search/       matching, ranking, reason text  
├── cache/        (repository, SHA) cache, expiry, in-flight merging  
└── common/       shared data types and the error model

#### **api (API Layer)**

* **Routes:** Defines the 5 endpoints (POST /analyses, GET /analyses/{id}, /graph, /files/{path}, /search). Doesn’t contain any logic and only delegates to the correct service.  
* **URLValidator:** Checks that the given input matches https\://github.com/\<owner\>/\<repo\> (or other supported version control platforms using git), and normalizes it. This runs before any network calls, and rejects any invalid or dangerous inputs.  
* **QueryValidator:** Trims search queries and rejects empty, large, and whitespace only inputs.  
* **ErrorHandler:** A FastAPI exception handler that takes any error and creates a RepolensError.

**Pipeline (orchestration)**

* **AnalysisPipeline**: Runs the process for one analysis in this order: Cache lookup, resolve hash, download snapshot, filter, parse, handle imports, store/cache. It will report the status continuously and discard partial data if a failure occurs at any stage. Finally, it deletes the snapshot after completion  
* **AnalysisStatus:** Tracks any queued, running, completed, or failed analysis. Read with an API, GET /analyses/{id}.

**Ingestion (file ingestion)**

* **RepoSource:** This is an interface which holds the data about a repository. You can get a snapshot of the codebase from an instance of this interface. We designed it as an interface to support potential future Git hosts.  
* **GitHubSource:** Implementation of RepoSource. Takes a branch or tag and matches it to a commit hash, and then downloads the code at that hash. It never runs or builds that code, and enforces timeouts and size caps for security. On error, it uses RepolensError, such as rate limits or 404s.   
* **FileFilter:** Removes any auto generated files, and keeps only necessary files in the snapshot.  
* **SizeGuard:** Enforces the 1000 Python file limit after filter, and raises RepolensError on a repo that is too large.  
* **SnapshotCleaner:** Deletes the snapshot directory after a completion (success or error).

**Analysis:**

* **LanguageAnalyzer:** This is an interface which is used to support potential future languages.  
* **PythonAnalyzer:** Implements LanguageAnalyzer with the Python language details, using the built-in ast module. It extracts imports, nested functions, classes, variables, and comments.  On any errors, it marks the parse as false instead of raising a full error, so one bad file doesn’t stop analysis. Again, it never runs any code.  
* **RepoIndex:** Built one time per analysis. It maps module names and paths to files, to maximize lookup speed.  
* **ImportResolver:** Analyzes imports and marks if it is internal, external, or otherwise.  
* **StdlibCatalog:** To know if imports are external, this file provides a list of standard module imports.

**Graph:**

* **GraphStore:** This interface saves repo data post-analysis to the database.  
* **SqliteGraphStore:** Implements GraphStore on a single file. It will write the analysis in one process, so failed analysis doesn’t lead to partial data.   
* **Schema/Migrations:** Defines schema tables, like Analysis, File, Symbol, Import, and Comment.  
* **ModuleGrouper:** Groups files into module nodes by proximity for a smaller map view.

**Search:**

* **SearchService:** This interface returns a list of RankedFile types, reading from GraphStore.  
* **QueryParser:** Split a query into tokens, so multi-word queries can match on files.  
* **Matcher:** Finds response files, matched against filenames, symbol names, import names, and comments.  
* **Ranker:** Ranks candidate files based on the match with the query, and also accounts for each file’s position in the dependency graph. Produces a reading order.  
* **ReasonBuilder:** Writes a one line reason for each result, citing evidence. Supplies a full match list.

**Cache (Cache Manager):**

* **Cache:** Stores past results, logged by (repo, SHA), and treats expired entries as a cache miss. Logs any corrupted or unavailable data as a miss and logs.  
* **Registry:** Keeps a map of running analyses on the same repo/SHA.  
* **ExpiryJob:** A scheduled clearing of the cache, calling evict\_expired() on any repo data which has existed in the cache for over 24 hours.

**FrontEnd Layout**

frontend/src/  
├── api/          typed REST client  
├── state/        app state (analysis, selection, search)  
├── components/   UI pieces  
└── pages/        landing page and analysis page

* **ApiClient:** Wraps the API endpoints and handles and returns errors. Supports canceling in-flight requests.  
* **AnalysisStore:** Holds the client’s status, including current repo, SHA, analysis status, summary, selected file, module, and search results.  
* **RepoInputForm:** URL input, which validates the URL format before enabling analysis.  
* **ProgressIndicator:** Shows the current stage of analysis, with a cancel button.  
* **SummaryBar:** Shows files analyzed, excluded, and to-be-analyzed.  
* **FileExplorer:** A tree view of the analyzed files. Selecting a file syncs the map.  
* **DependencyMap:** A flow graph with collapsed module nodes that expand when clicked. It highlights selected files dependencies/dependents and dims unrelated nodes. If it cannot render within 2-seconds, it hands off to ListFallback.  
* **ListFallback:** Explorer and list view used when the map cannot render.  
* **SearchBar:** Trims input or filters invalid queries.  
* **ReadingList:** Ranked results by position, path and reason. Provides a source link, and is limited to 20 results with a show more option.  
* **FileDetailPanel:** Shows path, module, symbols, internal/external imports and other information about the file. Provides a link to the source code.  
* **ErrorBanner:** Displays the message and hint from any structured/expected error.

**Coding Guideline**

The link below is the Google Python Style Guide. This guideline was selected for two reasons: First, it’s an industry standard coding guideline, though there are a few of those. Second, we chose Google’s guideline due to their reputation and the breadth of their influence on coding practices in general. We plan on enforcing the style guideline with an automated linter, built on Python’s ast library, that is applied to the code periodically. The linter parses each source file into an abstract syntax tree and walks the tree to check for violations such as naming conventions, docstring presence, import ordering, and function complexity.  
[https\://google.github.io/styleguide/pyguide.html](https://google.github.io/styleguide/pyguide.html) 

The link below is the Google TypeScript Style Guide, which applies to the React frontend. This guideline was selected for two reasons: First, it is an industry standard guideline for TypeScript, and it comes from the same company as the Google Python Style Guide we use for the backend, so both halves of the codebase follow one consistent set of conventions. Second, it gives clear rules on the choices that cause the most disagreement in code review, such as named exports instead of default exports, const and let instead of var, and avoiding the any type. We plan on enforcing the style guideline with ESLint and Prettier, both run in GitHub Actions on every pull request so that code that fails either check cannot be merged. ESLint parses each source file into an abstract syntax tree and walks the tree to check for violations such as naming conventions, unused variables, import ordering, and use of the any type, and Prettier is configured to match the guide's formatting.  
[https\://google.github.io/styleguide/tsguide.html](https://google.github.io/styleguide/tsguide.html)  


[image1]: <data:image/png;base64,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>