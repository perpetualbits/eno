# Session Summary — 2026-05-17

**Chat topic:** CARVE design discussion + project-management workflow.

This is the first session under the new project-wide workflow
conventions. The conventions are not in any document — they will be
added to the project's master instructions (project-wide directives)
so every chat inherits them.

---

## Files produced in this session

Three new files in `/mnt/user-data/outputs/`:

1. **`eno_project_index.md`** — the map. Lists every project document,
   its scope, and its status. This is the file every new chat should
   read first.

2. **`eno_decision_log.md`** — append-only log of load-bearing
   decisions made across all chats. Pre-populated with the decisions
   from this session. This is the file every new chat should read
   second.

3. **`spine_audio_dialect.md`** — the v0.1 sketch of the `audio`
   dialect. Defines bases, segments, trajectory templates, spaces,
   listeners, the polar wavelet reverb, and parameter quantization
   tables. Consumed by CARVE (which will be the next document) and
   by NERVE.

---

## What to do

### Step 1: upload the three files to project files

In the Claude UI, open the project's files panel and upload all three
markdown files. They become visible to every chat in the project.

After this, any new chat asking about CARVE, the audio dialect,
NERVE, or the polar wavelet reverb will have the context it needs.

### Step 2: add the project-wide conventions to the project's master instructions

The conventions are workflow rules, not document content. They belong
in the project's master instructions (the system-prompt-style text
that all chats inherit), not in any markdown file.

Recommended text to paste into the project's master instructions
(adapt to your wording as you see fit):

```
## Project-management workflow

Every chat in the Epsilon Null Operation project must follow these
conventions. They exist to keep the project coherent across chats.

1. At the start of each chat, read `eno_project_index.md` (the map of
   all project documents) and `eno_decision_log.md` (the load-bearing
   decisions made in other chats). These exist as project files.
   Identify which subsystem the chat is about and read that
   subsystem's documents.

2. One canonical document per subsystem. SMOLR has one document, smold
   has one, SPINE core has one, each dialect has its own, NERVE has
   one, CARVE has one. Cross-references between documents are named
   and explicit. Do not create parallel documents on the same topic.

3. Load-bearing decisions get an entry in `eno_decision_log.md` in
   the same session they are made. Reasoning stays in the subsystem
   documents; the log just summarizes what was decided and where to
   read. Decisions include: naming, format choices, architectural
   commitments, resolved open questions, scope changes.

4. New documents and major updates to existing ones are produced as
   files in `/mnt/user-data/outputs/`. The user uploads them to
   project files. Chats cannot write directly to project files; this
   is the only mechanism.

5. Every chat that produced or modified documents ends with a session
   summary file listing all files to upload and what each one
   changes. Do not assume the user remembers; produce the list
   explicitly.

6. When deferring a question, write it into `spine_open_questions.md`
   (for SPINE) or the relevant subsystem's open-questions section.
   Don't lose deferred questions in chat history.
```

Once this is in the master instructions, you no longer need to
explain the workflow to each new chat. They inherit it.

### Step 3: confirm before next work begins

Once steps 1 and 2 are done, future chats will:

- Open with the index and decision log visible.
- Know that CARVE is the next document to write.
- Know the audio dialect is the upstream-of-CARVE specification.
- Know the runtime is named NERVE.
- Know the polar wavelet reverb's approach 3 / global latency /
  point cloud decisions.
- Know that decisions get logged and that updates flow through
  uploaded files.

---

## What was decided in this session (also recorded in the decision log)

For ease of reference, here is the summary:

| Decision | Affects |
|----------|---------|
| Runtime is named NERVE | `spine_runtime_model.md` (top note now, rename later) |
| CARVE is the offline tool for audio trajectory templates (does not produce SPINE atoms directly) | `carve_design.md` (new, to be written), `spine_audio_dialect.md` |
| Binary SPINE format uses per-dialect dictionaries with per-stream pruning | resolves `spine_open_questions.md` §2.1, §2.2 |
| Audio dialect requires a parameter quantization table per type | `spine_audio_dialect.md`, `spine_dialect_template.md` (future field addition) |
| Polar wavelet reverb: approach 3 (separate direct path from precomputed reverb IR) | `spine_audio_dialect.md` |
| Polar wavelet reverb: pre-echoes via global audio latency L | `spine_audio_dialect.md`, `spine_runtime_model.md` (next update) |
| Polar wavelet reverb: point cloud + radial bucketing for 4k | `spine_audio_dialect.md` |
| CARVE's 3D scene representation shared between audio and graphics | `carve_design.md` (new) |
| IR interpolation across listener positions is permitted | `spine_audio_dialect.md` |
| Project-management workflow: index + decision log + session summaries | this session |

---

## What was NOT done in this session (deliberately)

These are next steps, not regressions:

- **`carve_design.md`** is not written. It is the obvious next
  document, but writing it after the audio dialect is the right order
  (CARVE produces audio dialect entities, so the dialect spec is
  upstream). Recommend writing it in the next CARVE chat.

- **`spine_runtime_model.md`** has not been updated for the NERVE
  name or for the audio latency L decision. Tagged for the next
  NERVE-focused chat. The current document still reads as "the
  runtime"; this is fine for now and consistent with the
  rename-later approach.

- **`spine_open_questions.md`** §2.1 and §2.2 have not been struck
  through in the actual file. The decision log records the
  resolution; formal cleanup of the open-questions document can wait
  until SPINE v0.4 (binary format implementation begins).

- **`spine_dialect_template.md`** has not been updated to add the
  parameter quantization table field. The audio dialect demonstrates
  the field; formal addition to the template is a small future PR.

None of these block CARVE design progress.

---

## Suggested smallest useful next step

Open a new chat focused on CARVE. The chat will:

1. Read `eno_project_index.md`, `eno_decision_log.md`,
   `spine_audio_dialect.md`.
2. Produce `carve_design.md` as a downloadable file.
3. Update the decision log with any new decisions.
4. Produce its own session summary.

The CARVE design document will cover: ML fitting pipeline shape,
node-graph UI, C struct definitions, 3D scene authoring, IR baker,
cyberpunk UI sketch, phase plan, risks. Probably 4–6 pages of
markdown.

Optional side path: open the NERVE chat instead and bring the runtime
model document up to date with the NERVE name and the audio latency
L addition. Quicker, lower-stakes, useful to do before the runtime
gets touched in any later chat.
