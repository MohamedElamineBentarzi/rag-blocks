# rag-blocks Studio

A visual, n8n-style builder for rag-blocks pipelines. Drag blocks onto a canvas,
connect them by their **data contracts** (only compatible ports connect, with
instant feedback), configure each from an auto-generated form, and **export the
exact JSON `load_spec()` loads**.

It is **optional** and fully **static**: no server, no runtime Python. A build
script introspects the component registry into a manifest the app reads.

```
studio/
  tools/build_manifest.py   # registry -> app/public/blocks.json (run when components change)
  app/                      # the Vite + React + @xyflow/react static app
```

## Run it

```bash
# 1. Generate the block manifest from the installed library (once, and whenever
#    you add/change a component):
python studio/tools/build_manifest.py

# 2. Start the app:
cd studio/app
npm install
npm run dev            # http://localhost:5173
```

`npm run manifest` (from `studio/app`) re-runs step 1.

## Use it

- **Drag** blocks from the left palette onto the canvas (or click them).
- **Connect** an output port to an input port. A connection only forms when the
  contract types match (`Document` → `Document`, `Chunk[]` → `Chunk[]`, …);
  incompatible ports are refused and dimmed while you drag.
- Representation blocks (embedder / sparse / lexical) fan into the **ChunkIndex**
  node, which feeds the retriever — mirroring how a real `ChunkIndex` is wired.
- **Configure** the selected block on the right; read its **Info** tab for the
  docstring and every parameter.
- **Export spec** downloads `pipeline.json`. Load it back in Python:

  ```python
  import rag_blocks as rk
  rag = rk.PipelineBuilder().build(rk.load_spec("pipeline.json"))
  ```

- **Import** re-opens a saved `pipeline.json` onto the canvas.

## What it deliberately doesn't do (v1)

- Composite retrievers (`fusion`/`hyde`/`multi-query`) can't be expressed in a
  flat spec, so they appear disabled with the reason.
- No live "run this pipeline" preview and no server-side validation — those need
  an optional Python bridge that isn't part of the static v1.

Secrets never enter the exported spec (§7.4): credential fields are shown as
password inputs and dropped on export; the environment supplies them.
