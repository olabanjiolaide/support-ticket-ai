# Interactive workbench (0.19.0)

This release improves navigation and review interactions. It does not change category cutoffs, the sentence encoder, local language-model prompts or evidence validation. The site remains a Python/FastAPI app with local HTML/CSS/JavaScript assets and no new frontend dependencies.

## What to click

- **Message / Suggestion / Individual needs**: the sticky section bar jumps to and focuses the relevant area. These are navigation buttons, not hidden-page tabs; the full message and result remain available together. The state label reports the real prediction state, not fabricated progress.
- **Compact view / Comfortable view**: switch the spacing density. The density preference survives reload. Only theme and density preferences are stored in browser localStorage; this feature does not store customer text or reviews there.
- **Menu** on mobile: open the workspace drawer. It supports navigation links, outside-click dismissal, Escape, focus containment and focus return. The background becomes inert while the drawer is open. The existing mobile section selector remains available as a quick route switch.
- **Request / Context / Unclear**: choose a quick interpretation for a fragment with one click. These are ordinary radio controls synchronized with the full interpretation selector. Other roles, including obstacle, conditional, alternative, negated and resolved, remain in that selector.
- **Review next fragment**: the next-step banner focuses the next unreviewed interpretation. When current requests have no group, it directs you to create/assign a need instead. It also directs you to incomplete need details, clarification text or model-review confirmation before returning you to the summary. It never confirms a role, saves or resolves anything merely by navigating.
- **Inspect assigned evidence** on a need card: show only its assigned fragments and highlight that need. **All fragments** restores the complete evidence view. Filters change presentation only; saving still validates every source fragment and full-message coverage. An empty filter explains how to return and assign evidence.
- **Review progress** counts actual interpretation selections across all fragments, including those hidden by a filter. It does not mean the model understood the message correctly or the customer problem is resolved.

The heading and model controls are more compact, the composer/result hierarchy is clearer, and hover/press states provide feedback. Existing save/copy success messages also appear briefly as visual notifications; their original accessible status messages remain the source of announcements. Reduced-motion preferences disable decorative movement and smooth scrolling.

## Printing

The print view hides navigation, action buttons, repeated help/footer material and decorative panels, and uses a simpler stacked layout. At print time, visible textareas are mirrored as plain text so the source message can wrap fully; empty fields are labeled as empty rather than printing their placeholder as if it were an entered response. Temporary mirrors are removed after printing without changing the inputs. All source fragment cards are included even when an on-screen evidence filter is active. Printing does not run inference or save a record.

## Reading the submitted examples

The three submitted PDFs show a word-model abstention and semantic ORDER suggestions with the separate-request checkbox off/on. All show an unreviewed manual breakdown and no language-model proposal panel or generated draft. Those captures do not establish a failed Ollama run, completed grouped review or improved semantic accuracy. They may predate the proposal UI or reflect an older frontend; the files alone do not establish which.

After updating and refreshing, the **Propose needs with a local language model** panel should appear even when not configured. If it says proposals are not configured, follow [the local model setup](41-local-needs-proposals.md). Category suggestion and local proposal generation are separate operations.

## Validation

A dedicated real-browser checker exercises section focus, radio/selector synchronization, progress, selected-need filtering, density persistence, mobile menu/focus/Escape behavior, reduced motion, print-value cleanup and five viewport widths (320, 390, 768, 1024 and 1440px) in light/dark themes. It verifies that navigation/preferences do not save records. Existing composer, manual grouping and authored-model proposal workflows remain regression checks. The proposal UI checks use declared model stubs; they do not measure live language-model quality.
