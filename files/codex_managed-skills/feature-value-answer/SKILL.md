---
name: feature-value-answer
description: Answer directly when a user asks what benefit a feature provides, why it was added, or whether it is dead code. Verify the actual user outcome and origin before defending or retaining the feature.
---

# Feature value answer

State the concrete result the user gains in the first sentence. If the code and
history do not support a user-facing benefit, say that no benefit is confirmed.
Do not substitute an explanation of internal state transitions for an answer
about value.

Inspect the current call sites, effective behavior, requirements and Git
history. Separate a documented requirement from a commit message or an
inference. If the user has asked to remove an unneeded feature, remove its
runtime path, public API, hooks and descriptions, then verify that the core
workflow still works. Keep legacy data inert if deleting it would risk loss.

On 2026-09-22, agent_coord worktree ownership had been explained as a
two-step change of a ledger label. That did not answer the user's repeated
question about what they gained. It was not needed for message delivery,
and no supporting user requirement was found in the repository history. The
feature was removed. This example is a reminder to answer the benefit
question before describing mechanics.
