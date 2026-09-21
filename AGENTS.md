# Project guidance for Codex

When a user asks what benefit an `agent_coord` feature provides, answer the
user-facing result directly and inspect the original requirement and actual
call sites. If no benefit is supported, say so and remove the unused feature
when requested. Do not defend a ledger transition as a benefit by itself.

For a correction or a request to record a lesson, use
`files/codex_managed-skills/memory-routing/SKILL.md`. For questions about a
feature's value or origin, use
`files/codex_managed-skills/feature-value-answer/SKILL.md`.

For `agent_coord` incidents reported from another environment that the user
has said is inaccessible, finish the source fix and local verification here.
Do not make access to that environment, testing there, or deployment there a
completion condition. The user deploys; give commands from the repository's
canonical redeployment instructions.
