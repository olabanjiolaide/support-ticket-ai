# Review-first optimization

The current working constraint is the transition from AI proposals to a saved human review. Recent user walkthroughs showed restored proposals but incomplete adoption and review. This is a hypothesis about reviewer effort, not a measured performance result.

We compared three directions: simplify the review workflow, improve model understanding, or expand operations and reporting. The first direction addresses observed friction with the smallest change to the existing system. Reassess after measuring the complete workflow.

## This release

- The workflow panel offers a next action: adopt proposals, continue interpretation review, inspect and confirm needs, or explicitly save reviewed needs.
- Adoption only populates the editable draft. Confirmation still requires an explicit checkbox action; saving still requires an explicit action. Edits revoke model-draft confirmation.
- A category-reviewed open request with a saved unreviewed draft displays `Category reviewed · needs review pending` in details and request lists. Other category-reviewed open requests display `Category reviewed`, without claiming that all needs have been found.
- Overview's existing category-reviewed open count is labelled accordingly. It is not a count of completed needs reviews. Queue membership and handling permissions are unchanged.
- Print layout allows long containers to paginate, keeps individual evidence cards together where possible, and reduces padding. No fixed page-count guarantee applies.

## Measure before expanding

Use existing development scenarios to record generation wait, navigation time, correction time, save/reload success, and errors. Separate authored regression fixtures from live-model runs. Correctness requires reference assessment; a saved review is not proof of correctness. Bulk annotation remains paused.

Choose the next change using the largest observed source of delay or rework. If correction dominates, compare three model approaches on the same examples and runtime budget. If navigation dominates, compare three interaction approaches. Implement one selected improvement at a time. This release adds no telemetry and makes no claim of measured throughput or accuracy improvement.

## Local walkthrough

1. Generate proposals for `Cancel order A. Keep order B.`
2. Save the request with its needs draft; confirm the overall ORDER category.
3. Verify the pending-needs label in details and All requests.
4. Choose **Adopt proposals for review** in the workflow panel.
5. Inspect both needs and their original evidence. Use **Inspect and confirm needs** to reach the confirmation checkbox; check it yourself.
6. Choose **Save reviewed needs**. Refresh and inspect the saved review and history.

The original **Use as editable draft** and **Save grouped review** controls remain available. No customer action is executed by any of these controls.
