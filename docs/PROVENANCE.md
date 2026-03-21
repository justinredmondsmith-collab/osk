# Provenance

This file records where Osk material came from and how copied or adapted
content should be tracked.

## Current Status

- Osk is a public spin-off repository related to
  `justinredmondsmith-collab/tiny-elite-answer`.
- The repository now contains original Osk runtime scaffolding plus selected
  adapted runtime logic from `bodycam-summarizer` for local Whisper/Ollama
  adapter work.
- The design/specification work was developed by the same maintainer and then
  split into this standalone repository.

## Licensing Intent

- Unless a file says otherwise, code in this repository is intended to be
  licensed as `AGPL-3.0-only`.
- When importing material from another repository, confirm that the maintainer
  has the right to relicense or continue licensing that material under
  `AGPL-3.0-only` before merging it here.

## Recording Future Transplants

When code, prompts, templates, tests, or substantial documentation are copied
or adapted into Osk from another source, add an entry here with:

- Date
- Source repository or upstream project
- Source path(s)
- Commit SHA or release tag when available
- Destination path(s)
- License or rights basis
- Short description of modifications

## Initial Relationship Record

- Related predecessor repository:
  `https://github.com/justinredmondsmith-collab/tiny-elite-answer`
- Planned transplant area:
  `bodycam-summarizer`
- Planned reuse:
  Whisper transcription, vision analysis, summarization, and related patterns
  after attribution and licensing review

## Recorded Adaptations

- Date: 2026-03-21
- Source repository: local `bodycam-summarizer`
- Source path(s):
  - `src/bodycam_summarizer/transcriber.py`
  - `src/bodycam_summarizer/whisper_runtime.py`
  - `src/bodycam_summarizer/cv_worker.py`
- Source commit: `01602a4dcdf52099dc75c19e977f7ed10ae478e0`
- Destination path(s):
  - `src/osk/transcriber.py`
  - `src/osk/whisper_runtime.py`
  - `src/osk/vision_engine.py`
  - `tests/test_transcriber.py`
  - `tests/test_whisper_runtime.py`
  - `tests/test_vision_engine.py`
- License or rights basis:
  Maintainer-authored predecessor code adapted within related repositories and
  continued here under Osk's intended `AGPL-3.0-only` licensing model.
- Modifications:
  Adapted transcript cleanup heuristics, Whisper profile fallback logic, and
  Ollama request/response handling into Osk's contract-first worker/adapter
  interfaces. Removed bodycam/session-specific behavior and preserved mocked
  tests instead of direct runtime transplant.
