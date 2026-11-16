# RepoLens

RepoLens is a web-based code exploration tool that helps onboarding developers get oriented in an unfamiliar codebase.

Given a public GitHub repository and a branch, tag, or commit, RepoLens statically analyzes the source, graphs file and module dependencies on an interactive map, and lists files related to a specific feature. You can quickly find entry points, trace code workflows, and understand file relationships without manually sifting through the directories.

RepoLens does not import, execute, or build code from analyzed repositories.

## Try RepoLens

Once RepoLens releases, you'll be able to access the tool online.

### Run locally with Docker

You can also run RepoLens locally with [Docker](https://docker.com). This means you don't need Python, Node.js, `make`, or a virtual environment. Depending on your operating system, you just need:

- **Windows, macOS:** Docker Desktop
- **Linux:** Docker Engine with the Docker Compose plugin

Next, from the repository root, run:

```bash
docker compose up --build
```

Then open **http://localhost:8000**. The first run may take a few minutes to build. If you need to cancel, press ` Ctrl ` + ` C `.

To run an image already published to GitHub Container Registry instead of building locally, run:

```bash
docker compose pull && docker compose up
```

Analyses are kept in a Docker volume and expire after 24 hours. To raise GitHub's anonymous API rate limit, you can set a personal token in your shell before starting RepoLens:

```bash
GITHUB_TOKEN=your_token_here docker compose up
```

The API health endpoint is available at http://localhost:8000/api/health.

### Using RepoLens

Open **http://localhost:8000** (or **http://localhost:5173** when running the development servers below).

In the web application, paste a GitHub repository URL (for example, https://github.com/pallets/click). Optionally, you can choose a branch, tag, or commit SHA. Then press **Analyze**. When analysis is finished, there will be a summary, file explorer, and interactive dependency map.

You can search for a task, feature, or question, like "serializer" or "where is a signature checked?". RepoLens will search file paths, module-level symbols, class members, imports, docstrings, and comments. You'll get a ranked reading list with a short explanation and the reasoning behind each result.

Search results are reflected on the map. Selecting a file highlights its direct dependencies and dependents, helping you explore and narrow a large repository down to the code relevant to your task.

To inspect a file, select it to open its detail panel. You'll see the file path and module, parsed symbols, imports, and files that import it. Press **Open Source on GitHub** to open the file at the exact commit you're analyzing. Symbol links will point you to the corresponding line.

## Contributing

Interested in improving RepoLens?

- Start with [docs/DEVELOPERS.md](https://github.com/Amogh-Babu/RepoLens/tree/main/docs/DEVELOPERS.md) for architecture, setup, tests, benchmarks, and guidance for extending the analyzer.
- Discuss bugs and proposed changes at the [issue tracker](https://github.com/Amogh-Babu/RepoLens/issues).
