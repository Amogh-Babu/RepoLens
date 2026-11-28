
# RepoLens User Guide
 
RepoLens is a web app that helps you get oriented in an unfamiliar Python project. You give it a GitHub link, and it reads the project's code, draws a map of how the files connect, and helps you find the files that matter for your task. You don't need to click through folders one by one.
 
RepoLens only works with **public Python repositories**. It reads the code but never runs it, so it's safe to use on projects you don't yet trust.
 
---
 
## What You'll Need
 
RepoLens runs on your own computer using Docker. You don't need to install Python or Node.js. Install the right tool for your system:
 
- **Windows or macOS:** [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- **Linux:** Docker Engine with the Docker Compose plugin
Open Docker and make sure it's running before you continue.
 
---
 
## Part 1: Starting RepoLens
 
1. Download or clone the RepoLens project folder to your computer.
2. Open a terminal inside the RepoLens folder.
   - **Windows:** open the folder in File Explorer, click the address bar, type `cmd`, and press Enter.
   - **macOS or Linux:** open Terminal and use `cd` to move into the folder.
3. Type the following command and press Enter:
```bash
docker compose up --build
```
 
4. The first time, this can take a few minutes. Wait until the terminal stops printing new lines. Later starts take only a few seconds.
5. Open your web browser and go to **http://localhost:8000**.
To stop RepoLens, go back to the terminal and press **Ctrl+C**.
 
> **Tip:** Analyses are saved for 24 hours, so you can restart RepoLens without losing recent results.
 
### Optional: Using a GitHub Token
 
GitHub limits how many requests an anonymous user can make to its service each hour (60). If you analyze many repositories, you can raise that limit with a personal GitHub token. Set it before you start RepoLens:
 
```bash
GITHUB_TOKEN=your_token_here docker compose up
```
 
You can skip this step for normal use.
 
---
 
## Part 2: Analyzing a Repository
 
1. In the RepoLens web page, paste the link to a public Python repository. For example:
   - `https://github.com/pallets/click`
   - `https://github.com/pallets/itsdangerous`
2. If you want a specific version of the project, you can optionally enter a **branch**, **tag**, or **commit SHA**. If you're not sure, leave this blank to use the default version.
3. Click **Analyze**.
4. RepoLens works through several stages: resolving, downloading, filtering, parsing, classifying, indexing, and storing. Watch the stage indicator as it moves along.
When it finishes, you'll see three things:
 
    - **Summary bar:** how many files were analyzed, how many were excluded (such as generated or vendored files), and how many couldn't be read.
    - **File explorer:** the project's folders and files, shown as a tree.
    - **Dependency map:** a diagram of how the Python modules import one another.
---
 
## Part 3: Reading the Dependency Map
 
The dependency map shows which files depend on which. Each box is a module, and arrows show imports.
 
- **Expand a module:** click a collapsed module box to see the files inside it.
- **Select a file:** click a file to highlight the files it depends on and the files that depend on it. This makes it easy to see what a file is connected to.
The map is most useful for answering "what is this file connected to?" and "where does this code fit in the project?"
 
---
 
## Part 4: Searching for What You Need
 
The search bar lets you describe your task in your own words. You don't need to know the exact function or file name.
 
Examples of questions you can type:
 
- `serializer`
- `where is a signature checked?`
- `where do I start if I'm working on production?`
RepoLens searches file paths, class and function names, members, and imports. It combines keyword matches with a local search model to find related code even when the words don't match exactly. Weak semantic matches are omitted, so a search can return no results even when relevant code exists; try more specific terms or identifiers. Files that could not be parsed may also be missing searchable content. All searching happens on your computer. Your repository text is not sent to any outside service.
 
After you search, RepoLens shows:
 
- A **ranked reading list** with a short explanation for each result.
- **Highlighted results on the dependency map**, so you can see where the matching files sit in the project.
---
 
## Part 5: Using the Recommended Reading Order
 
The reading list is the fastest way to learn a project. It shows the files most relevant to your search, in a suggested order to read them.

The list highlights **Read first** dependencies and a possible **Edit here** starting point. **Tests to run** suggests test files that import that starting point; these are separate from search matches and the reading tour. Other matches remain available under **Other matches**. These suggestions are based on static imports and search scores, not guarantees; verify that they fit your task. Up to 20 related tests are shown.
 
Use the filter to choose what you're looking for:
 
- **Overall topic:** a high-level view of the project.
- **Implementation:** the files where the main work happens.
- **Configuration:** the files that set up how the project runs.
- **Tests and examples:** files that show how the code is meant to be used.
By default, test and example paths are excluded from search matches; choose **Tests and examples** to include them. The filter also changes how results are ranked.
 
---
 
## Part 6: Viewing File Details
 
Click any file to open its **detail panel**. The panel shows:
 
- The file's path and module name
- The functions, classes, and variables defined in the file
- Other project files it imports
- Other project files that import it
- Outside libraries it uses
To read the actual code, click **Open source on GitHub**. This opens the file on GitHub at the exact version RepoLens analyzed. If you click a function or class name, it takes you to that line.
 
---
 
## Known Limitations
 
RepoLens is an early prototype, so keep these in mind:
 
- **Repository size:** RepoLens handles up to about 1,000 files. Larger projects may be slow or incomplete.
- **Analysis time:** the search indexing step is the slowest. Large projects can take several minutes.
- **Imports:** projects that change how Python imports work (for example, through unusual path changes or dynamic imports) may have some internal imports marked as external.
- **Search without the model:** if the search model can't load, RepoLens still completes the analysis, but search uses keywords only.
- **Results can be wrong:** RepoLens is a helper for reading code. It doesn't prove a project is secure or correct. Always check the source code yourself.
---
 
## Troubleshooting
 
- **The page doesn't load at http://localhost:8000:** make sure Docker is running, then check that the terminal still shows RepoLens running. If it has stopped, run `docker compose up --build` again.
- **The first start is very slow:** this is normal. The first build can take a few minutes.
- **Analysis fails for a repository:** make sure the link is to a **public** repository and that the project is written in **Python**.
- **Analysis hits GitHub limits:** wait an hour, or set a `GITHUB_TOKEN` as described above.
- **Old results are gone:** analyses expire after 24 hours. Analyze the repository again.
---
 
## Quick Reference
 
| Task | What to do |
|---|---|
| Start RepoLens | `docker compose up --build`, then open http://localhost:8000 |
| Stop RepoLens | Press Ctrl+C in the terminal |
| Analyze a project | Paste a public Python GitHub link and click **Analyze** |
| Search | Type a task or question in the search bar |
| See suggested reading | Use the reading list and its filter |
| See file details | Click a file, then **Open source on GitHub** to read the code |
 
