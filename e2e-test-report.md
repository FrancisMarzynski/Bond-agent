# E2E Test Report

Data: 2026-04-28
Projekt: `Bond-agent`
Lokalne URL:
- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
Narzędzia:
- `agent-browser 0.26.0`
- `uv run uvicorn bond.api.main:app --reload --port 8000`
- `npm run dev`

## Executive Summary

- Journeys tested: 5
- Screenshot files changed in this run: 53
- Screenshot files currently present under `e2e-screenshots/`: 79
- Issues found during runtime testing: 4
- Issues fixed during this run: 3
- Remaining runtime issue: 1
- Additional code-analysis findings kept open: 3

This run covered:
- corpus ingest and validation flows
- duplicate warning in Author mode
- full Author HITL flow through CP1, CP2, and metadata save
- full Shadow HITL flow including reject -> rerun -> approve
- responsive validation across mobile, tablet, and desktop

Two important regressions were reproduced and fixed in the same run:
- CP1 reject payload mismatch (`note` vs `feedback`)
- Author draft streaming contamination (tokens from non-writer nodes and multi-attempt writer output)

A third issue was found and fixed during responsive verification:
- mobile Author editor layout in `@uiw/react-md-editor` live mode

## Environment and Preflight

- Platform check: `Darwin`
- Frontend detected and reachable
- `agent-browser` already installed; browser engine confirmed with `agent-browser install --with-deps`
- Backend health check passed via `GET /health`
- No authentication or sign-in flow is present in the application

Pre-test codebase research identified:
- UI routes: `/` (Author), `/shadow` (Shadow)
- data stores:
  - `./data/articles.db`
  - `./data/bond_metadata.db`
  - `./data/bond_checkpoints.db`
  - Chroma `bond_metadata_log_v1`
- likely risk areas:
  - CP1 reject payload contract mismatch
  - session/history mode metadata gap
  - over-eager stream recovery on `!response.ok`
  - file ingest success shown even when `chunks_added=0`

## Runtime Findings Summary

### Fixed During This Run

1. CP1 reject payload mismatch
- Severity: high
- Symptom: rejecting `checkpoint_1` with feedback did not meaningfully alter the structure on rerun
- Root cause: frontend sent only `feedback`; backend CP1 contract expects `note` and optional `edited_structure`
- Fix:
  - `frontend/src/components/CheckpointPanel.tsx:56`
  - `frontend/src/hooks/useStream.ts:607`
- Verification:
  - reproduced on thread `e74bcc41-40e1-4769-8c4f-7ebe2637560a`
  - after fix, CP1 rerun respected the feedback and changed the heading structure

2. Author draft streaming contamination
- Severity: high
- Symptom: editor showed concatenated intermediate output, including `<thinking>` artifacts and content from multiple writer attempts
- Root cause: frontend appended every SSE token into one `draft` buffer regardless of active node
- Fix:
  - parse `node_start` / `node_end` lifecycle
  - append tokens only while active node is `writer`
  - replace editor buffer with backend `draft` on `hitl_pause` for CP2
  - file: `frontend/src/hooks/useStream.ts:171`
- Verification:
  - on thread `c1847570-ca40-4251-a906-24a4ef54893d`, `/history` at CP1 showed `draft=""`
  - CP2 and completed UI no longer contained `<thinking>` or prompt artifacts
  - browser eval confirmed `hasThinking=false`, `hasPrompt=false`

3. Mobile Author editor live layout
- Severity: medium
- Symptom: mobile view compressed/overlaid markdown input and preview in Author mode
- Root cause: `@uiw/react-md-editor` uses absolute-positioned preview in `show-live` mode
- Fix:
  - mobile-only CSS override for `<640px`
  - file: `frontend/src/app/globals.css:134`
- Verification:
  - screenshots before fix: `responsive/01-author-mobile.png`, `responsive/07-author-mobile-after-fix.png`, `responsive/08-author-mobile-after-fix-reset.png`
  - final fixed state: `responsive/09-author-mobile-after-position-fix.png`

### Remaining Runtime Issue

1. Historical SQLite <-> Chroma metadata drift
- Severity: medium
- Symptom: duplicate-check metadata stores are still off by one after successful new saves
- Evidence:
  - final SQLite metadata count: `6`
  - final Chroma metadata count: `5`
  - new saves in this run did persist to both stores; the mismatch appears historical
- Impact: duplicate detection may miss some older published topics
- Recommended follow-up:
  - backfill missing Chroma embeddings from `data/bond_metadata.db`
  - add parity check tooling or startup/admin integrity command

### Additional Code-Analysis Findings Kept Open

1. Session mode is not part of stored session metadata
- Severity: medium
- Risk: restoring a saved session can open it in the wrong UI mode until history hydration finishes
- Relevant file: `frontend/src/hooks/useSession.ts:17`

2. Stream recovery treats all `!response.ok` responses as committed-disconnect recovery candidates
- Severity: medium
- Risk: real HTTP errors can incorrectly fall into recovery flow
- Relevant file: `frontend/src/hooks/useStream.ts:511`

3. File ingest can return `chunks_added=0`, but frontend still reports success
- Severity: medium
- Risk: user sees "Plik zaindeksowany" even when backend skipped parsing
- Relevant files:
  - `bond/api/routes/corpus.py:69`
  - `frontend/src/components/CorpusAddForm.tsx:201`

## Journey 1: Corpus / Baza Wiedzy

### Scope

- open corpus panel
- submit text ingest
- validate URL empty-state
- validate URL SSRF guard
- upload file
- validate Google Drive empty-state
- verify corpus counters and SQLite rows

### Baseline Before Corpus Actions

SQLite article count and chunk sum:

```sql
SELECT COUNT(*), COALESCE(SUM(chunk_count), 0) FROM corpus_articles;
```

Result before positive corpus actions:

```text
12|12
```

Metadata baseline before new Author save:

```sql
SELECT COUNT(*) FROM metadata_log;
```

Result:

```text
4
```

Chroma duplicate metadata baseline before new Author save:

```text
count= 3
```

### Steps and Outcomes

1. Opened `BAZA WIEDZY` and expanded add form
- Outcome: panel rendered correctly
- Screenshots:
  - `e2e-screenshots/corpus/01-corpus-expanded.png`
  - `e2e-screenshots/corpus/02-add-form-open.png`

2. Text ingest positive path
- Input title: `E2E corpus text 2026-04-28 18:10`
- Outcome: success banner shown; corpus counters incremented
- Screenshots:
  - `e2e-screenshots/corpus/03-text-form-filled.png`
  - `e2e-screenshots/corpus/04-text-submit-success.png`

SQLite validation after text ingest:

```sql
SELECT COUNT(*), COALESCE(SUM(chunk_count), 0) FROM corpus_articles;
```

Result:

```text
13|13
```

Newest inserted row later visible in final table state:

```text
c6e2547b-ec35-4d5c-98fb-07fd0b629d32|E2E corpus text 2026-04-28 18:10|own||1|2026-04-28T16:11:28.751316+00:00
```

3. URL ingest empty validation
- Action: opened URL tab and submitted empty input
- Outcome: inline validation `Podaj adres URL.`
- Screenshots:
  - `e2e-screenshots/corpus/05-link-tab-open.png`
  - `e2e-screenshots/corpus/06-link-empty-validation.png`

4. URL ingest SSRF negative path
- Input: `http://localhost:8000`
- Outcome: backend correctly rejected non-public host
- UI error:

```text
url host resolves to a non-public address: ::1
```

- Screenshot:
  - `e2e-screenshots/corpus/07-link-ssrf-validation.png`

5. File ingest positive path
- Uploaded file: `/tmp/bond-e2e-upload-20260428.txt` copied from project `README.md`
- Outcome: success banner shown; counters incremented by 1 article / 8 chunks
- Screenshots:
  - `e2e-screenshots/corpus/08-file-tab-open.png`
  - `e2e-screenshots/corpus/09-file-selected.png`
  - `e2e-screenshots/corpus/10-file-submit-success.png`

SQLite validation after file ingest:

```sql
SELECT COUNT(*), COALESCE(SUM(chunk_count), 0) FROM corpus_articles;
```

Result:

```text
14|21
```

Newest row:

```text
1c222d7d-2897-4711-bfeb-13be46814a54|bond-e2e-upload-20260428|own||8|2026-04-28T16:13:12.426091+00:00
```

6. Google Drive empty validation
- Action: opened Drive tab and submitted empty input
- Outcome: inline validation `Podaj ID folderu Google Drive.`
- Screenshots:
  - `e2e-screenshots/corpus/11-drive-tab-open.png`
  - `e2e-screenshots/corpus/12-drive-empty-validation.png`

7. Closed add form
- Outcome: layout remained stable
- Screenshot:
  - `e2e-screenshots/corpus/13-add-form-closed.png`

### Journey Assessment

- Positive text ingest: passed
- Positive file ingest: passed
- URL empty validation: passed
- URL SSRF protection: passed
- Drive empty validation: passed
- No runtime JS/browser errors were reported during final verified corpus steps

## Journey 2: Author Duplicate Warning

### Scope

- submit a known duplicate topic
- verify duplicate warning pause
- validate persisted paused history
- confirm no metadata save occurs before continuation

### Test Input

Topic:

```text
Detached runtime browser validation 20260428-122101
```

Thread id:

```text
d7525088-227f-4c3f-a06a-581869702275
```

### Steps and Outcomes

1. Started Author flow with duplicate topic
- Screenshot:
  - `e2e-screenshots/author/01-duplicate-topic-filled.png`

2. Duplicate warning displayed
- Outcome: warning pause rendered instead of continuing silently
- Screenshot:
  - `e2e-screenshots/author/02-duplicate-warning.png`

3. History validation

```bash
curl http://localhost:8000/api/chat/history/d7525088-227f-4c3f-a06a-581869702275
```

Observed:
- `session_status="paused"`
- `pending_node="duplicate_check"`
- `can_resume=true`
- duplicate warning payload present

4. Metadata validation

```sql
SELECT COUNT(*) FROM metadata_log WHERE thread_id='d7525088-227f-4c3f-a06a-581869702275';
```

Result:

```text
0
```

5. Continued despite warning
- Outcome: flow resumed, but the default non-sessioned browser run later ended on `about:blank`
- Interpretation: browser harness/session persistence issue, not a product regression
- Screenshot:
  - `e2e-screenshots/author/03-author-after-duplicate-continue.png`

### Journey Assessment

- Duplicate detection: passed
- Duplicate HITL pause persistence: passed
- Pre-save metadata safety: passed

## Journey 3: Author Full Flow, CP1 Payload Bug, and Metadata Save

### Scope

- run unique Author topic
- reach CP1
- reject CP1 with feedback
- reproduce frontend/backend payload mismatch
- patch frontend
- rerun CP1 and verify structure changes
- continue to CP2 and save metadata

### Test Input

Thread id:

```text
e74bcc41-40e1-4769-8c4f-7ebe2637560a
```

Topic:

```text
Temat: E2E author unique flow 2026-04-28 18:18
Słowa kluczowe: detached runtime, recovery SSE, walidacja E2E, frontend recovery
```

### Steps and Outcomes

1. Started unique Author session
- Screenshots:
  - `e2e-screenshots/author/06-author-session-home.png`
  - `e2e-screenshots/author/07-unique-topic-filled.png`
  - `e2e-screenshots/author/08-author-streaming.png`

2. Reached CP1
- Screenshot:
  - `e2e-screenshots/author/09-checkpoint1-paused.png`

3. Reproduced CP1 reject bug
- Action: rejected CP1 with structural feedback
- Screenshots:
  - `e2e-screenshots/author/10-checkpoint1-reject-form.png`
  - `e2e-screenshots/author/11-checkpoint1-feedback-filled.png`
  - `e2e-screenshots/author/12-checkpoint1-after-reject.png`
- Observed:
  - backend `cp1_iterations` advanced
  - `heading_structure` remained effectively unchanged
  - irrelevant sections stayed in place

4. Implemented fix
- `CheckpointPanel` now sends `note` on CP1 reject
- `resumeStream` supports optional `editedStructure` and `note`

5. Retested CP1 after fix
- Screenshots:
  - `e2e-screenshots/author/14-checkpoint1-reject-form-after-reload.png`
  - `e2e-screenshots/author/15-checkpoint1-after-fix-success.png`
- Outcome:
  - `cp1_iterations=2`
  - heading structure changed to a simplified 3-section outline
  - removed sections requested in feedback were no longer present

6. Continued to CP2
- Screenshot:
  - `e2e-screenshots/author/16-checkpoint2-paused.png`

7. Saved to metadata store
- Screenshot:
  - `e2e-screenshots/author/17-author-completed.png`

SQLite metadata validation:

```sql
SELECT id, thread_id, topic, published_date
FROM metadata_log
WHERE thread_id='e74bcc41-40e1-4769-8c4f-7ebe2637560a'
ORDER BY id DESC;
```

Observed row during the run:

```text
5|e74bcc41-40e1-4769-8c4f-7ebe2637560a|Temat: E2E author unique flow 2026-04-28 18:18\nSłowa kluczowe: detached runtime, recovery SSE, walidacja E2E, frontend recovery|2026-04-28T16:42:54.866964+00:00
```

Chroma validation during the run:
- collection count advanced from `3` to `4`
- `thread_id` present in duplicate metadata collection

### Journey Assessment

- Author CP1 pause: passed
- CP1 reject behavior before fix: failed and reproduced
- CP1 reject behavior after fix: passed
- CP2 pause and save: passed
- Metadata save to SQLite and Chroma: passed for newly created topic

## Journey 4: Author Streaming Cleanup Re-Test

### Scope

- rerun Author from a clean stable browser session after streaming fix
- verify CP1 has no polluted `draft`
- verify CP2 editor contains clean final draft
- save metadata and validate final persistence

### Test Input

Thread id:

```text
c1847570-ca40-4251-a906-24a4ef54893d
```

Topic:

```text
Temat: E2E author streaming cleanup 2026-04-28 19:05
Słowa kluczowe: streaming draft, checkpoint CP2, frontend SSE, cleanup tokenów
```

### Steps and Outcomes

1. Started clean stable Author run
- Screenshots:
  - `e2e-screenshots/author/18-streaming-cleanup-topic-filled.png`
  - `e2e-screenshots/author/19-streaming-cleanup-during-run.png`

2. Verified CP1 history had empty draft

```bash
curl http://localhost:8000/api/chat/history/c1847570-ca40-4251-a906-24a4ef54893d
```

Observed at CP1:
- `session_status="paused"`
- `pending_node="checkpoint_1"`
- `draft=""`

- Screenshot:
  - `e2e-screenshots/author/20-streaming-cleanup-checkpoint1.png`

3. Approved CP1 and waited for writer / CP2
- Intermediate browser text showed only article content, not research/prompt text

4. Verified CP2 clean draft

History inspection:
- `draft_len=4406`
- `has_thinking=false`
- `has_prompt_marker=false`
- `has_research_header=false`

Browser eval:
- `hasPrompt=false`
- `hasThinking=false`

- Screenshot:
  - `e2e-screenshots/author/21-streaming-cleanup-checkpoint2-clean.png`

5. Saved final Author result
- Screenshot:
  - `e2e-screenshots/author/22-streaming-cleanup-completed-clean.png`

SQLite metadata validation:

```sql
SELECT id, thread_id, substr(topic,1,80), published_date
FROM metadata_log
WHERE thread_id='c1847570-ca40-4251-a906-24a4ef54893d'
ORDER BY id DESC;
```

Result:

```text
6|c1847570-ca40-4251-a906-24a4ef54893d|Temat: E2E author streaming cleanup 2026-04-28 19:05
Słowa kluczowe: streaming d|2026-04-28T16:49:26.494396+00:00
```

Chroma validation:

```text
count= 5
ids: ['c1847570-ca40-4251-a906-24a4ef54893d']
```

Final history snapshot:
- `session_status="completed"`
- `pending_node=None`
- persisted draft length `4406`

### Journey Assessment

- CP1 editor contamination: fixed
- CP2 editor contamination: fixed
- `<thinking>` artifact in final editor: fixed
- final Author metadata persistence: passed

## Journey 5: Shadow Full HITL Flow

### Scope

- submit raw source text
- reach `shadow_checkpoint`
- inspect annotations and corrected text
- reject with feedback
- verify second iteration
- approve final result

### Test Input

Thread id:

```text
48bf34fb-da28-4344-a906-19ea403a2665
```

Source text:

```text
To jest bardzo innowacyjne rozwiązanie, które całkowicie zmienia sposób projektowania instalacji elektrycznych. Dzięki niemu wszystko działa szybciej, lepiej i bardziej nowocześnie. Firmy mogą bez problemu wdrażać BIM, poprawiać komunikację i osiągać świetne rezultaty bez większego wysiłku. To po prostu przyszłość branży i warto z niej korzystać jak najszybciej.
```

### Steps and Outcomes

1. Opened Shadow route and entered input
- Screenshots:
  - `e2e-screenshots/shadow/01-shadow-home.png`
  - `e2e-screenshots/shadow/02-shadow-input-filled.png`

2. Submitted for analysis
- Screenshot:
  - `e2e-screenshots/shadow/03-shadow-streaming.png`

3. Reached `shadow_checkpoint`
- History validation:
  - `session_status="paused"`
  - `pending_node="shadow_checkpoint"`
  - `annotations=4`
  - corrected text length on first pass: `326`
- Screenshot:
  - `e2e-screenshots/shadow/04-shadow-checkpoint-paused.png`

4. Interacted with annotation list
- Selected annotation card and verified synced highlight in original text
- Screenshot:
  - `e2e-screenshots/shadow/05-shadow-annotation-selected.png`

5. Rejected with feedback
- Feedback:

```text
Dodaj bardziej techniczny ton i usuń sformułowanie 'bez zwłoki'.
```

- Screenshot:
  - `e2e-screenshots/shadow/06-shadow-reject-feedback-filled.png`

6. Verified second iteration
- History validation:
  - `session_status="paused"`
  - `pending_node="shadow_checkpoint"`
  - `iteration=1`
  - `annotations=4`
  - corrected text length on second pass: `367`
- Screenshot:
  - `e2e-screenshots/shadow/07-shadow-after-reject-rerun.png`

7. Approved final Shadow result
- Final history:
  - `session_status="completed"`
  - `pending_node=None`
  - `annotations=4`
  - `shadowCorrectedText` length `367`
- Screenshot:
  - `e2e-screenshots/shadow/08-shadow-completed.png`

### Journey Assessment

- Shadow initial analysis: passed
- Annotation rendering and selection: passed
- Shadow reject -> rerun loop: passed
- Shadow approve/complete path: passed
- No final browser `errors` output in Shadow session

## Journey 6: Responsive Validation

### Scope

- revisit major Author and Shadow screens in three viewport classes
- capture screenshots
- check for overflow, clipping, layout collapse, and touch-target issues

### Viewports

- Mobile: `375x812`
- Tablet: `768x1024`
- Desktop: `1440x900`

### Screenshots

- Author:
  - `e2e-screenshots/responsive/01-author-mobile.png`
  - `e2e-screenshots/responsive/02-author-tablet.png`
  - `e2e-screenshots/responsive/03-author-desktop.png`
  - `e2e-screenshots/responsive/07-author-mobile-after-fix.png`
  - `e2e-screenshots/responsive/08-author-mobile-after-fix-reset.png`
  - `e2e-screenshots/responsive/09-author-mobile-after-position-fix.png`
- Shadow:
  - `e2e-screenshots/responsive/04-shadow-mobile.png`
  - `e2e-screenshots/responsive/05-shadow-tablet.png`
  - `e2e-screenshots/responsive/06-shadow-desktop.png`

### Findings

1. Shadow layout remained stable across all tested breakpoints
- annotation list and original/corrected panes stayed readable
- no runtime browser errors in final session

2. Author layout had a mobile markdown editor issue
- fixed during this run
- final mobile screenshot after CSS remediation:
  - `e2e-screenshots/responsive/09-author-mobile-after-position-fix.png`

### Journey Assessment

- Mobile: passed after fix
- Tablet: passed
- Desktop: passed

## Database Validation Details

### `articles.db`

Final aggregate state:

```sql
SELECT COUNT(*), COALESCE(SUM(chunk_count), 0) FROM corpus_articles;
```

Result:

```text
14|21
```

Latest rows:

```sql
SELECT article_id, title, source_type, source_url, chunk_count, ingested_at
FROM corpus_articles
ORDER BY ingested_at DESC
LIMIT 3;
```

Result:

```text
1c222d7d-2897-4711-bfeb-13be46814a54|bond-e2e-upload-20260428|own||8|2026-04-28T16:13:12.426091+00:00
c6e2547b-ec35-4d5c-98fb-07fd0b629d32|E2E corpus text 2026-04-28 18:10|own||1|2026-04-28T16:11:28.751316+00:00
82e5d9d4-4399-4c41-9b3d-204fa30df4f6|bond-e2e-upload|own||1|2026-04-28T06:47:51.416709+00:00
```

### `bond_metadata.db`

Final aggregate state:

```sql
SELECT COUNT(*) FROM metadata_log;
```

Result:

```text
6
```

Latest rows:

```sql
SELECT id, thread_id, substr(topic,1,120), published_date
FROM metadata_log
ORDER BY id DESC
LIMIT 3;
```

Result:

```text
6|c1847570-ca40-4251-a906-24a4ef54893d|Temat: E2E author streaming cleanup 2026-04-28 19:05
Słowa kluczowe: streaming draft, checkpoint CP2, frontend SSE, clea|2026-04-28T16:49:26.494396+00:00
5|e74bcc41-40e1-4769-8c4f-7ebe2637560a|Temat: E2E author unique flow 2026-04-28 18:18\nSłowa kluczowe: detached runtime, recovery SSE, walidacja E2E, frontend |2026-04-28T16:42:54.866964+00:00
4|f004bd1e-5b5d-421c-93e2-ffb7e07fc834|Detached runtime browser validation 20260428-122101|2026-04-28T10:22:30.397435+00:00
```

### Chroma `bond_metadata_log_v1`

Final observed state:

```text
count= 5
```

Verification for new Author save:

```text
ids: ['c1847570-ca40-4251-a906-24a4ef54893d']
documents: ['Temat: E2E author streaming cleanup 2026-04-28 19:05\nSłowa kluczowe: streaming draft, checkpoint CP2, frontend SSE, cleanup tokenów']
```

## Lint / Verification Commands Run

- `npm run lint` after CP1 payload fix
- `npm run lint` after draft streaming cleanup fix
- `npm run lint` after responsive CSS fix

All lint runs completed successfully.

No backend `pytest` suite was rerun as part of this E2E pass.

## Screenshot Inventory For This Run

Note:
- the repository already contained older screenshot artifacts from previous validation work
- the list below contains the 53 screenshot files added or modified in this run

### Root

- `e2e-screenshots/00-initial-load.png`

### Corpus

- `e2e-screenshots/corpus/01-corpus-expanded.png`
- `e2e-screenshots/corpus/02-add-form-open.png`
- `e2e-screenshots/corpus/03-text-form-filled.png`
- `e2e-screenshots/corpus/04-text-submit-success.png`
- `e2e-screenshots/corpus/05-link-tab-open.png`
- `e2e-screenshots/corpus/06-link-empty-validation.png`
- `e2e-screenshots/corpus/07-link-ssrf-validation.png`
- `e2e-screenshots/corpus/08-file-tab-open.png`
- `e2e-screenshots/corpus/09-file-selected.png`
- `e2e-screenshots/corpus/10-file-submit-success.png`
- `e2e-screenshots/corpus/11-drive-tab-open.png`
- `e2e-screenshots/corpus/12-drive-empty-validation.png`
- `e2e-screenshots/corpus/13-add-form-closed.png`

### Author

- `e2e-screenshots/author/01-duplicate-topic-filled.png`
- `e2e-screenshots/author/02-duplicate-warning.png`
- `e2e-screenshots/author/03-author-after-duplicate-continue.png`
- `e2e-screenshots/author/04-checkpoint1-current.png`
- `e2e-screenshots/author/05-checkpoint1-restored.png`
- `e2e-screenshots/author/06-author-session-home.png`
- `e2e-screenshots/author/07-unique-topic-filled.png`
- `e2e-screenshots/author/08-author-streaming.png`
- `e2e-screenshots/author/09-checkpoint1-paused.png`
- `e2e-screenshots/author/10-checkpoint1-reject-form.png`
- `e2e-screenshots/author/11-checkpoint1-feedback-filled.png`
- `e2e-screenshots/author/12-checkpoint1-after-reject.png`
- `e2e-screenshots/author/13-checkpoint1-feedback-after-fix.png`
- `e2e-screenshots/author/14-checkpoint1-reject-form-after-reload.png`
- `e2e-screenshots/author/15-checkpoint1-after-fix-success.png`
- `e2e-screenshots/author/16-checkpoint2-paused.png`
- `e2e-screenshots/author/17-author-completed.png`
- `e2e-screenshots/author/18-streaming-cleanup-topic-filled.png`
- `e2e-screenshots/author/19-streaming-cleanup-during-run.png`
- `e2e-screenshots/author/20-streaming-cleanup-checkpoint1.png`
- `e2e-screenshots/author/21-streaming-cleanup-checkpoint2-clean.png`
- `e2e-screenshots/author/22-streaming-cleanup-completed-clean.png`

### Shadow

- `e2e-screenshots/shadow/01-shadow-home.png`
- `e2e-screenshots/shadow/02-shadow-input-filled.png`
- `e2e-screenshots/shadow/03-shadow-streaming.png`
- `e2e-screenshots/shadow/04-shadow-checkpoint-paused.png`
- `e2e-screenshots/shadow/05-shadow-annotation-selected.png`
- `e2e-screenshots/shadow/06-shadow-reject-feedback-filled.png`
- `e2e-screenshots/shadow/07-shadow-after-reject-rerun.png`
- `e2e-screenshots/shadow/08-shadow-completed.png`

### Responsive

- `e2e-screenshots/responsive/01-author-mobile.png`
- `e2e-screenshots/responsive/02-author-tablet.png`
- `e2e-screenshots/responsive/03-author-desktop.png`
- `e2e-screenshots/responsive/04-shadow-mobile.png`
- `e2e-screenshots/responsive/05-shadow-tablet.png`
- `e2e-screenshots/responsive/06-shadow-desktop.png`
- `e2e-screenshots/responsive/07-author-mobile-after-fix.png`
- `e2e-screenshots/responsive/08-author-mobile-after-fix-reset.png`
- `e2e-screenshots/responsive/09-author-mobile-after-position-fix.png`

## Recommendations

1. Backfill and reconcile duplicate metadata between SQLite and Chroma
- this is the only runtime issue that remained after the end-to-end pass

2. Tighten stream error classification
- distinguish true committed disconnects from ordinary HTTP failures before entering recovery

3. Align file ingest success UI with backend payload semantics
- if `chunks_added=0`, show warning/error rather than success

4. Add a targeted test for CP1 reject payload
- protect the `note` contract from future regressions

5. Add a focused frontend test for Author draft streaming
- assert no token accumulation before `writer`
- assert CP2 editor is replaced by backend `draft`

6. Add a mobile visual regression around `EditorPane`
- the fix depends on vendor CSS behavior in `@uiw/react-md-editor`

