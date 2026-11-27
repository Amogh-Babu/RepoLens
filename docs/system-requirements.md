# System requirements and resource limits

RepoLens runs as one process: the FastAPI backend, which also serves the
frontend. Almost all of its memory and CPU goes to **semantic indexing**, which
runs a small local embedding model (`BAAI/bge-small-en-v1.5` through FastEmbed
and ONNX Runtime) on the CPU. Optional AI summaries use a remote provider
when explicitly enabled; see the backend README for the data sent.

## Requirements

| | Minimum | Recommended |
| --- | --- | --- |
| CPU | 2 cores | 4 cores |
| Memory for RepoLens | 1 GB | 2 GB |
| Machine memory (with OS, Docker) | 2 GB | 4 GB |
| Browser | any current browser | any current browser |

With `REPOLENS_EMBEDDINGS_ENABLED=false`, 1 core and 512 MB for RepoLens are
enough. Search is then keyword-only and says so.

These figures come from the measurements below, not from a target. Wall times
were measured on Apple Silicon (arm64) in a Docker container limited to 4 CPUs
and 3.5 GB with no swap. Expect slower CPUs to take proportionally longer;
memory does not depend on CPU speed.

## Configuration

Set these in the environment (for example under `environment:` in
`compose.yaml`). Invalid values stop the server at startup with a message
naming the variable.

| Variable | Default | What it does |
| --- | --- | --- |
| `REPOLENS_EMBEDDINGS_ENABLED` | `true` | `false` skips semantic indexing; search is keyword-only. |
| `REPOLENS_EMBEDDING_THREADS` | At most `2` | ONNX Runtime threads, bounded by CPU affinity and container quota by default. |
| `REPOLENS_EMBEDDING_BATCH_SIZE` | `16` | Chunks per model call. Memory grows with this. |
| `REPOLENS_MAX_EMBEDDING_CHUNKS` | `10000` | Most chunks one analysis embeds. A bigger repository keeps its map and keyword search, and search reports that semantic matching was skipped. |
| `REPOLENS_MAX_CONCURRENT_ANALYSES` | `1` | Analyses that run at once; later ones wait in a queue. |

An analysis's response includes `semanticSearch: {status, chunks}` once it
completes, and every search response includes `semanticStatus`. Any status other
than `complete` (`empty`, `disabled`, `over_budget`, `failed`) means search
results are keyword-only.

The existing `REPOLENS_EMBED_THREADS` and `REPOLENS_EMBED_BATCH_SIZE`
settings remain supported. The longer names above take precedence.

## Why it used to need so much (#118)

Before these limits, analyzing numpy reached 3.0 GB resident memory (5.1 GB
virtual) and pyvmomi 1.9 GB, enough to be killed on a 4 GB machine. The causes,
in order of effect:

1. **FastEmbed's default batch of 256 chunks.** The model's working memory grows
   with the batch size times the square of the longest chunk in the batch, and
   ONNX Runtime keeps its largest allocation for the life of the process. On
   RepoLens's own 495 chunks, a batch of 256 took 75 s and 1.73 GB; a batch of
   32 took 20 s and 414 MB.
2. **One ONNX thread per visible core.** In a container, ONNX Runtime counts the
   host's cores, not the container's CPU quota, so it oversubscribes the CPU.
   Two threads did the same work in a third of the CPU time.
3. **Two analyses at once.** Each one ran its own full-size inference. Indexing
   pyvmomi and RepoLens together took 731 s and 3.3 GB, against 171 s run one
   after the other.

Cost follows the number and length of **chunks**, not the number of files:
pyvmomi has fewer files than RepoLens but its generated bindings hold about
9,500 class members. Parsing never took more than 17 s (numpy).

### Measured before and after

Same container, same pinned repositories (RepoLens `0c1bcea`, pyvmomi
`75a18fd`, numpy `85c4843`), default settings:

| Repository | Files | Chunks | Before: time / peak RSS / peak virtual | After |
| --- | ---: | ---: | --- | --- |
| RepoLens | 152 | 495 | 81 s / 1.75 GB / 3.9 GB | 13 s / 330 MB / 1.6 GB |
| pyvmomi | 112 | 1,929 | 96 s / 1.92 GB / 3.9 GB | 43 s / 357 MB / 1.5 GB |
| numpy | 774 | 6,552 | 638 s / 3.03 GB / 5.1 GB | 134 s / 576 MB / 1.7 GB |
| numpy, embeddings off | 774 | — | 16 s / 161 MB | 20 s / 173 MB |

Searching numpy went from 3.7 s to 0.2 s: vectors are now scored a few hundred
rows at a time with NumPy instead of all being loaded as Python floats.

Virtual size is reported separately because it is mostly address space that
ONNX Runtime and its threads reserve without using; resident memory (RSS) is
what the out-of-memory killer acts on.

## The dependency map

Laying out the map (Dagre) runs in a Web Worker, so it never freezes the page,
and a layout that runs past 10 seconds is stopped and the file list shown
instead. Before laying anything out, the map counts the boxes and import lines
it would draw. It draws at most **400 boxes and 1,000 lines**; a folder whose
opening would pass that stays closed and the map says why. A repository whose
map is too large even with every folder closed is shown as the file list.

Measured in Chromium (2 CPUs), the longest the page was blocked by opening one
folder went from 28.4 s to 0.33 s for numpy and from 2.8 s to 0.24 s for
pyvmomi. Panning and zooming for a minute showed no growth in DOM size or
JavaScript heap, before or after.

## Known limits

- The Safari freeze reported in #118 could not be reproduced safely, and was
  not reproduced: Playwright's WebKit build does not draw the map in a
  container, and it was not tested on a real Mac to avoid crashing it.
  Chromium did not degrade while panning and zooming.
- Repositories over `REPOLENS_MAX_EMBEDDING_CHUNKS` get no semantic index at
  all, rather than a partial one.
- Wall times above are from one machine; they are a guide, not a guarantee.
