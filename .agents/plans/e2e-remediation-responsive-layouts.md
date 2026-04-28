# Feature: Repair Responsive Shell and Workspace Layouts

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

This workstream fixes the mobile and tablet layout failures documented in [.planning/E2E_REPORT_2026-04-28.md](.planning/E2E_REPORT_2026-04-28.md). Desktop is acceptable, but the app shell and editing workspaces are currently too desktop-first: the persistent 256px sidebar remains visible on small viewports, the Author workspace flips into a two-column layout too early, and the Shadow comparison view keeps a three-column desktop arrangement on narrow widths.

The goal is not to redesign the product visually. The goal is to make all major flows usable at `375x812`, `768x1024`, and `1440x900` while preserving the established visual language and existing component structure.

## User Story

As an editor using Bond on a tablet or smaller laptop  
I want the workspace to reflow into a readable, navigable layout  
So that I can run Author and Shadow flows without being forced onto a desktop viewport

## Problem Statement

The E2E report attributes the responsive failure mainly to `frontend/src/app/page.tsx`, but the codebase shows a broader root cause:

- [frontend/src/app/layout.tsx](frontend/src/app/layout.tsx) always renders a persistent sidebar.
- [frontend/src/components/Sidebar.tsx](frontend/src/components/Sidebar.tsx) fixes the sidebar to `w-64` at every viewport.
- [frontend/src/app/page.tsx](frontend/src/app/page.tsx) switches to `md:flex-row`, which means iPad portrait already gets the desktop split.
- [frontend/src/components/ShadowPanel.tsx](frontend/src/components/ShadowPanel.tsx) keeps a desktop three-pane layout at every width.

The result is compounded compression, not a single isolated breakpoint bug.

## Solution Statement

Make the app shell mobile-first and delay desktop-specific layouts until larger breakpoints:

1. Convert the sidebar into an overlay drawer below `lg`, keeping it persistent only on desktop widths.
2. Keep Author stacked vertically until `lg`, not `md`, so tablets retain full-width content.
3. Reflow the Shadow comparison view below `lg` into a single-column reading workflow with the annotation list promoted to a top section instead of a permanent left rail.
4. Adjust toolbars, banners, and action rows to wrap cleanly instead of assuming wide horizontal space.

This approach fixes the actual width pressure without introducing a new design system or frontend dependency.

## Feature Metadata

**Feature Type**: Enhancement / Bug Fix  
**Estimated Complexity**: Medium-High  
**Primary Systems Affected**: Root layout shell, sidebar, Author workspace, Shadow workspace, stage/checkpoint/editor UI  
**Dependencies**: Next.js App Router, Tailwind CSS v4 utility variants, existing shadcn/ui primitives

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `.planning/E2E_REPORT_2026-04-28.md` (lines 17-29, 228-254, 312-315, 343-347)
  - Why: Documents the viewport sizes tested, observed failures, and recommended fix ordering.
- `frontend/src/app/layout.tsx` (lines 17-38)
  - Why: Root app shell always renders a persistent sidebar and header.
- `frontend/src/components/Sidebar.tsx` (lines 8-47)
  - Why: Sidebar is a fixed-width desktop panel today.
- `frontend/src/app/page.tsx` (lines 6-22)
  - Why: Author workspace flips to horizontal layout at `md`, which is too early.
- `frontend/src/components/ChatInterface.tsx` (lines 39-94)
  - Why: Message list and composer sizing need narrow-width adjustments.
- `frontend/src/components/CheckpointPanel.tsx` (lines 63-244)
  - Why: Action rows, feedback form, and warning panels currently assume wide horizontal space.
- `frontend/src/components/StageProgress.tsx` (lines 16-99)
  - Why: Stage indicator row needs to remain legible under constrained width.
- `frontend/src/components/EditorPane.tsx` (lines 55-77)
  - Why: Markdown toolbar and editor container need wrapping/overflow adjustments.
- `frontend/src/components/ShadowPanel.tsx` (lines 122-311)
  - Why: Current Shadow comparison view is permanently three-column and desktop-first.
- `frontend/src/components/AnnotationList.tsx` (lines 23-124)
  - Why: Annotation rail is fixed-width and should become a responsive top section below desktop.
- `frontend/src/app/globals.css` (lines 119-125)
  - Why: Global base layer is minimal; any shell-wide overflow fixes must be compatible here.

### New Files to Create

- `frontend/src/components/SidebarDrawer.tsx`
  - Purpose: Mobile/tablet overlay shell for session history and corpus access below `lg`.
- `frontend/src/components/ShadowAnnotationsSection.tsx`
  - Purpose: Responsive annotation container that can render as a full-width top section below desktop without duplicating `AnnotationList` logic.

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- https://tailwindcss.com/docs/breakpoints
  - Specific section: Responsive design / breakpoint ranges
  - Why: Needed to choose correct breakpoints and avoid tablet receiving desktop layout prematurely.
- https://tailwindcss.com/docs/flex-direction
  - Specific section: Responsive design examples
  - Why: Confirms mobile-first flex direction transitions like `flex-col lg:flex-row`.
- https://tailwindcss.com/docs/overflow
  - Specific section: `overflow-*` utilities
  - Why: Needed to stop nested panes from clipping or creating unusable scroll traps.
- https://tailwindcss.com/docs/responsive-design
  - Specific section: Mobile-first approach
  - Why: Reinforces the correct layering strategy for this refactor.

### Patterns to Follow

**Preserve existing visual language**

- Keep the current neutral palette, spacing scale, and component primitives.
- Do not replace Button/Textarea/Card usage with raw HTML unless a component truly does not exist.

**Layout composition pattern**

- Existing pages already compose from small local components rather than giant monoliths; keep that approach when extracting responsive subcomponents.

**Border and overflow discipline**

- Current code uses `min-w-0`, `overflow-hidden`, and `shrink-0` deliberately. Preserve these semantics and only relax them where they currently create clipping on narrow viewports.

**Anti-patterns to avoid**

- Do not keep the persistent sidebar visible below desktop widths.
- Do not introduce a separate mobile-only route.
- Do not rebuild the editor or Shadow flow from scratch.

---

## IMPLEMENTATION PLAN

### Phase 1: Responsive App Shell

Fix the shell-level width pressure before touching page internals.

**Tasks:**

- Add a mobile/tablet sidebar drawer and a header trigger below `lg`.
- Keep the persistent sidebar only for desktop widths.
- Ensure root body/header/main containers still maintain full-height layout without double scrollbars.

### Phase 2: Author Workspace Reflow

Delay the desktop split and make the supporting UI wrap safely.

**Tasks:**

- Keep the Author page stacked until `lg`.
- Make stage progress, checkpoint actions, and editor toolbar wrap or stack gracefully.
- Preserve desktop behavior above `lg`.

### Phase 3: Shadow Workspace Reflow

Replace the always-on three-column view with a breakpoint-aware structure.

**Tasks:**

- Keep desktop three-column mode at `lg+`.
- Below `lg`, move annotations into a full-width top section.
- Stack original and corrected text panes vertically with independent scroll regions and usable min-heights.

### Phase 4: Manual E2E Revalidation

Confirm the affected flows work at the same viewport sizes documented in the report.

**Tasks:**

- Re-test `375x812`, `768x1024`, and `1440x900`.
- Confirm Author, Shadow, session history access, and corpus access remain usable.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### CREATE `frontend/src/components/SidebarDrawer.tsx`

- **IMPLEMENT**: Add an overlay sidebar/drawer component used below `lg` for session history and corpus status.
- **PATTERN**: Reuse the existing `Sidebar` content structure and `useSession()` interactions instead of inventing a second data source.
- **IMPORTS**: Existing `Button`, `Separator`, `CorpusStatusPanel`, `useSession`.
- **GOTCHA**: Do not duplicate session switching logic; call the same `newSession()` and `switchSession()` methods.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/components/Sidebar.tsx`

- **IMPLEMENT**: Split presentation into:
  - persistent desktop sidebar at `lg+`
  - shared content renderable inside the new drawer below `lg`
- **PATTERN**: Keep the current button/session list markup where possible.
- **GOTCHA**: Avoid diverging desktop and mobile sidebar content; use composition, not copy/paste.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/app/layout.tsx`

- **IMPLEMENT**: Render persistent sidebar only on desktop and add a mobile/tablet drawer trigger in the header below `lg`.
- **IMPLEMENT**: Keep the main workspace full-width below `lg`.
- **PATTERN**: Preserve the existing header + `SessionProvider` + `ErrorBoundary` shell.
- **GOTCHA**: Do not break `h-screen` / `overflow-hidden` assumptions used by child panes.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/app/page.tsx`

- **IMPLEMENT**: Change the Author layout breakpoint from `md:flex-row` to `lg:flex-row`.
- **IMPLEMENT**: Revisit width constraints so the chat pane stays full-width below `lg` and only gains a fixed proportion on desktop.
- **PATTERN**: Keep `ChatInterface`, `CheckpointPanel`, and `EditorPane` as composed children.
- **GOTCHA**: Preserve `min-h-0`, `min-w-0`, and pane scroll behavior after the breakpoint shift.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/components/StageProgress.tsx`

- **IMPLEMENT**: Allow the progress row to wrap or scroll gracefully on narrow widths.
- **IMPLEMENT**: Ensure reconnect/system-alert banners do not overflow or compress step labels into illegible states.
- **PATTERN**: Reuse the current iconography and status color semantics.
- **GOTCHA**: Do not reduce the banners to a height where text becomes clipped.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/components/ChatInterface.tsx`

- **IMPLEMENT**: Adjust message bubble widths and composer row behavior for narrow widths.
- **IMPLEMENT**: Ensure the composer can stack or stretch without forcing horizontal overflow.
- **PATTERN**: Keep the current user/assistant bubble semantics and retry button behavior.
- **GOTCHA**: Do not regress desktop line length or message alignment.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/components/CheckpointPanel.tsx`

- **IMPLEMENT**: Make warning rows, action rows, and feedback submission stack cleanly below `lg`.
- **IMPLEMENT**: Ensure approve/reject buttons remain reachable without horizontal scrolling.
- **PATTERN**: Preserve current checkpoint-specific labels and logic.
- **GOTCHA**: Keep duplicate-check warnings visually distinct from standard checkpoints.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/components/EditorPane.tsx`

- **IMPLEMENT**: Let the toolbar wrap and keep actions visible on narrow widths.
- **IMPLEMENT**: Ensure the editor container still fills available height without clipping the preview.
- **PATTERN**: Preserve the dynamic `@uiw/react-md-editor` import and current preview/live switching.
- **GOTCHA**: Do not introduce body-level scrolling by removing `overflow-hidden` blindly.
- **VALIDATE**: `cd frontend && npm run lint`

### CREATE `frontend/src/components/ShadowAnnotationsSection.tsx`

- **IMPLEMENT**: Extract a wrapper that can render annotations as a full-width top section below desktop while reusing `AnnotationList` behavior and actions.
- **PATTERN**: Reuse `AnnotationList` content and click handlers instead of duplicating annotation card logic.
- **IMPORTS**: Existing `AnnotationList`, `Button`, `Badge` only as needed.
- **GOTCHA**: Keep annotation click-to-scroll behavior unchanged.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/components/AnnotationList.tsx`

- **IMPLEMENT**: Make the component flexible enough to render as:
  - fixed-width left rail on desktop
  - full-width top section below desktop
- **PATTERN**: Keep current skeleton and card structure.
- **GOTCHA**: Do not hard-code `w-64` in the only render path.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/components/ShadowPanel.tsx`

- **IMPLEMENT**: Introduce breakpoint-aware layouts:
  - `lg+`: keep the current three-column comparison view
  - `<lg`: render annotations first, then stack original and corrected panes vertically
- **IMPLEMENT**: Keep the HITL action panel visible and readable on narrow widths.
- **IMPLEMENT**: Give stacked panes usable `min-h` values and independent scroll regions.
- **PATTERN**: Preserve current highlight-on-click and “Zastosuj” behaviors.
- **GOTCHA**: Do not lose the editable corrected-text area in the stacked layout.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/app/shadow/page.tsx`

- **IMPLEMENT**: Keep the page thin, but ensure any page-level wrapper needed for the responsive Shadow layout lives here instead of leaking global shell hacks into the root layout.
- **PATTERN**: Preserve the route as a simple Shadow entry point.
- **GOTCHA**: Avoid duplicating shell/header/sidebar logic already owned by `layout.tsx`.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/app/globals.css`

- **IMPLEMENT**: Add only the minimal global overflow/safe-area adjustments needed after shell changes.
- **PATTERN**: Keep theme variables and base layer intact.
- **GOTCHA**: Do not introduce global overrides that fight Tailwind utility classes in individual components.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE documentation/screenshots after implementation

- **IMPLEMENT**: Refresh the responsive screenshot set and update the E2E report only after the implementation is verified.
- **PATTERN**: Keep the artifact naming convention already used in `e2e-screenshots/responsive/`.
- **GOTCHA**: Do not mark responsive issues fixed until all three target viewport classes are re-tested.
- **VALIDATE**: `git diff -- .planning/E2E_REPORT_2026-04-28.md`

---

## TESTING STRATEGY

### Unit Tests

- No new frontend unit test harness is currently present in the repo. Do not introduce a new test stack in this workstream unless absolutely necessary.

### Integration Tests

- Validate with `npm run lint` and `npm run build`.
- Re-run the browser E2E checks at the same three viewport sizes documented in the report.

### Edge Cases

- Sidebar open/close while a session is streaming.
- Author page at exactly `768px` tablet portrait.
- Shadow comparison with many annotations and long replacement strings.
- Checkpoint panel with feedback field open on narrow screens.
- Editor toolbar visible on smaller laptop widths.

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style

- `cd frontend && npm run lint`

### Level 2: Build Validation

- `cd frontend && npm run build`

### Level 3: Manual Responsive Validation

1. Open the app at `375x812`.
2. Confirm the sidebar is hidden by default and reachable through a header trigger.
3. Confirm Author content uses the full viewport width and remains readable.
4. Open the app at `768x1024`.
5. Confirm Author remains stacked vertically and no longer uses the desktop split.
6. Open Shadow mode and confirm annotations/original/corrected panes are readable without horizontal squeeze.
7. Open the app at `1440x900`.
8. Confirm the desktop layout remains effectively unchanged.

### Level 4: Browser E2E Regression Check

- Reproduce the same screenshots listed in `.planning/E2E_REPORT_2026-04-28.md` for responsive validation.

---

## ACCEPTANCE CRITERIA

- [ ] Sidebar no longer steals permanent width on mobile and tablet.
- [ ] Author workspace stays stacked until desktop widths and is usable at `768x1024`.
- [ ] Shadow workspace is readable and actionable below `lg` without permanent three-column squeeze.
- [ ] Stage, checkpoint, and editor controls do not require horizontal scrolling on mobile/tablet.
- [ ] Desktop layout remains intact.
- [ ] `npm run lint` and `npm run build` both pass.
- [ ] Responsive screenshots can be re-captured without reproducing the original failures.

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Manual viewport checks completed
- [ ] No desktop regressions observed
- [ ] Acceptance criteria all met
- [ ] E2E artifacts refreshed after verification

---

## NOTES

- The root cause is broader than `frontend/src/app/page.tsx`; the persistent sidebar and Shadow desktop-first layout both contribute materially to the compression.
- Keep the solution mobile-first and incremental. This is a layout repair, not a redesign initiative.
- Avoid introducing a new UI dependency just to create a drawer; a light local overlay component is enough here.

**Confidence Score:** 8/10 for one-pass implementation success
