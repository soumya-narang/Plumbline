# Deploying Plumbline

Two layers, both free. The static site is the durable one; the live container adds the real graph.

| Layer | What it gives | Host | Needs |
|---|---|---|---|
| Static site | The full incident replay from recorded snapshots, no server, always up | GitHub Pages | a public GitHub repository |
| Live container | The real FalkorDB graph, free-text questions, approvals, receipt verification | A Hugging Face Space (Docker) | a free Hugging Face account |

The page chooses by itself: if `api/meta` answers it runs live, otherwise it reads `web/data/`. The badge in the
header says which one you are looking at ("Live graph" or "Recorded snapshots").

## 1. Publish the repository

```bash
git remote add origin https://github.com/<you>/plumbline.git
git push -u origin main
```

Never commit `.env`. It is git-ignored; check `git status` before pushing.

## 2. Static site on GitHub Pages

1. In the repository, open Settings, then Pages, and set Source to **GitHub Actions**.
2. Push to `main`, or run the **Pages** workflow from the Actions tab.
3. The site appears at `https://<you>.github.io/plumbline/`.

`web/data/` is committed. Regenerate it whenever the data or the code that produces verdicts changes:

```bash
python -m plumbline load            # graph must be loaded first
python -m plumbline export-static   # rewrites web/data, deterministically
git add web/data && git commit -m "Refresh the static export"
```

Set `PLUMBLINE_REPO_URL` before exporting to show a "Source" link in the header.

## 3. Live container on a Hugging Face Space

The `Dockerfile` builds one image: FalkorDB (copied from the official image), the API and the UI. It runs as an
unprivileged user, listens on port 7860 and loads the graph from the committed data on every start, so no state
needs to survive a restart. First start takes about a minute.

1. Create a Space at <https://huggingface.co/new-space>: SDK **Docker**, hardware **CPU basic** (free), public.
2. Clone it next to this repository and copy the project in, using the Space README that carries the settings:

   ```bash
   git clone https://huggingface.co/spaces/<you>/plumbline plumbline-space
   git -C plumbline archive HEAD | tar -x -C plumbline-space
   cp plumbline/deploy/huggingface/README.md plumbline-space/README.md
   cd plumbline-space && git add -A && git commit -m "Deploy" && git push
   ```

3. Optional: under Settings, Variables and secrets, add `PLUMBLINE_REPO_URL`. To let a model choose the tools
   instead of the built-in planner, add secrets `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL` (any server that speaks
   the chat-completions tool-calling protocol). `LLM_MAX_ASKS_PER_HOUR` (default 60) caps model calls so a public
   Space cannot run up a bill; over the cap, questions fall back to the planner.

Free Spaces sleep after a period of inactivity and wake on the next visit. The static site has no such delay, so
link to both.

## Run the container locally

```bash
docker build -t plumbline .
docker run --rm -p 7860:7860 plumbline     # http://localhost:7860
```

## What to check after deploying

- The header badge reads "Live graph" on the Space and "Recorded snapshots" on Pages.
- Open `?start=12` and confirm the hypothetical-event banner and one reopened decision appear.
- On the Space, press "Re-derive and verify" on an EXPOSED row: it should say verified.
- Pin the FalkorDB image by digest before any submission build (see `docs/falkordb-engine.md`).
