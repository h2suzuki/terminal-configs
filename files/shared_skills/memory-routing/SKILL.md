---
name: memory-routing
description: Route user corrections and durable instructions among shared lessons learned, hooks, skills, AGENTS.md, and Claude Code organization CLAUDE.md. Use when asked to remember a lesson, corrected repeatedly, or deciding where persistent guidance belongs; check relevant lessons after repeated failure or before declaring an authorized action impossible.
when_to_use: TRIGGER when the user asks to remember or record a lesson ("覚えて" / "記録して" / "教訓"), repeats a correction, or asks where persistent guidance belongs; also after repeated failure or before declaring an authorized action impossible. SKIP for in-session Task tracking and ordinary task notes.
---

# Memory routing

Choose where the guidance belongs before writing it. A request to record a lesson does not authorize a new skill, hook, or always-loaded instruction. Keep the user's requested artifact and scope when they have already specified them.

## Choose the destination

| Need | Destination | Boundary |
| --- | --- | --- |
| A durable correction, preference, or dated case that should be recalled when relevant | A `feedback_*.md` entry in the shared lessons-learned repository | Search for an existing entry first. A single correction is not a standing policy. |
| A deterministic action at a documented lifecycle event | Hook | Implement only within an authorized task. Verify the event and its blocking semantics before using enforcement. |
| A reusable procedure that should load for a matching task | Skill | Create a new skill only when the user explicitly directs it. Do not turn feedback into a skill on your own. |
| A standing project instruction shared by coding agents | The project's `AGENTS.md` | Use when the user directs or approves a persistent project rule. Check that the target clients actually load it. |
| Claude Code-only organization policy | Managed `CLAUDE.md` (`files/claude_managed-CLAUDE.md` in this repository) | Discuss the exact rule and its scope with the user and require their explicit instruction before editing. Do not use project or user `CLAUDE.md` for a new rule under this policy. |

These destinations serve different purposes; an implementation request may call for a hook or skill while a distinct dated lesson remains in the lessons-learned store. Do not duplicate the same standing rule in several instruction files. Retire an incorrect entry rather than leaving harmful advice active. A correct entry can be retired when a user-authorized managed instruction or mechanism fully covers it.

Codex loads project `AGENTS.md` by default. Claude Code v2.1.277+ can also load it, but its default chooses project `CLAUDE.md` or `CLAUDE.local.md` instead when either is on the path. Managed and user `CLAUDE.md` do not suppress project `AGENTS.md`; some Claude sessions cannot load `AGENTS.md` directly. Check the target version, project files, and Project instructions setting before relying on it. Sources: [Codex AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md), [Claude Code AGENTS.md](https://code.claude.com/docs/en/memory#agents-md). This project's preference for managed `CLAUDE.md` only for Claude Code organization policy is a user instruction, not a vendor restriction.

## Save a lessons-learned entry

The canonical store is the private `h2suzuki/claude-lessons-learned` GitHub repository; `/var/lib/claude-rag-memory/claude-lessons-learned` is its local clone. An entry file in the clone is active. The search index is derived from those files, not a second source of truth.

1. Search across model tags before writing: `python3 /etc/claude-code/skel/hooks/memory_surface.py --search "<lesson>"`. Compare the corrective action and inspect likely hits, not just matching words. Update an entry that already teaches the same action and append the dated case; otherwise create one entry. Record a durable correction when it occurs, especially after repeated feedback. Also search before declaring an authorized action impossible or after a second failure. Skip temporary task notes and facts already available in the code.
2. Choose the narrowest justified scope. `org/` is for user-independent guidance established across projects or a general model failure; `user/<login>/` is for that user's preferences or circumstances; `project/<project-id>/` is for one repository's rule, incident, or defect. When unsure, prefer project or user over org. Obtain the project ID with `python3 /etc/claude-code/skel/hooks/memory_surface.py --project-id`; do not guess from a checkout path.
3. Write a `feedback_*.md` entry for a behavioral correction, or `reference_*.md` for a dated external-reference snapshot. Both need frontmatter `name`, `description`, `metadata.type` matching the filename prefix, `reminder`, `keywords`, `models`, and, when new, `check`. `when` is optional; the default is `prompt`, and accepted values are `prompt`, `stop`, and `after-subagent` separated by spaces. Use only model tags in which the failure was observed; add a tag later if the same failure is observed in another model.
4. Make `reminder` one actionable sentence of at most 150 characters, `keywords` selective and searchable (at least one meaningful 3+ character CJK or 4+ character ASCII token, and at least four phrases separated by `,` or `、`; the Stop route matches each phrase as a substring of the reply, so a space-separated list is one phrase that never matches), and `check` one positive inspection of the last output of at most 100 characters. Do not use `oneline_summary`. For `feedback_*`, use `## 理由`, optional `## 対処`, `## 事例`, optional `## 関連`, once each in that order, and date the case `YYYY-MM-DD`. For `reference_*`, include an absolute verification date. Keep case detail in the body, not the reminder. The installed validator is `memory_routing_gate.py`.
5. Prepare the complete entry in ignored workspace scratch and confirm it is ignored. Invoke the bare command `claude_memory_sync --write-from <draft-path> <absolute-entry-path>` with the tool's working-directory option. This one command validates the entry, writes the clone, updates the index, commits, and schedules a push for both Claude Code and Codex. Direct `Write`/`Edit` of the clone is not this workflow. Remove only the draft you created after verification.
6. Run `claude_memory_sync --status`, compare the saved file with the draft, and search for the new entry. `--search` exercises only the prompt route; for an entry whose `when` includes `stop`, also confirm that at least one keyword phrase appears verbatim in the kind of reply the lesson targets. A successful local write is not proof of remote delivery; report pending push or failure accurately. On a read-only or permission error, diagnose the invocation under `sandbox-host-recovery` before handing it to the operator.

The `models` and `when` fields control surfacing. Claude Code supports prompt, Stop, and after-subagent routes. Codex currently surfaces general entries at UserPromptSubmit; its Stop hook handles only a targeted write-failure reminder. Check the installed hook before promising a particular Stop or subagent notification on Codex.

## Update or retire an entry

Use the same search, scope, complete-draft, and `--write-from` procedure to update an entry. An update replaces the whole file: include the existing content and the new dated case in the draft. Retire an entry when it is incorrect, when the user asks to remove it, or when an authorized managed skill, hook, or instruction fully replaces it. Run `claude_memory_sync --retire <absolute-entry-path>` and verify that the file and index record are gone. Retirement deletes the active file and pushes that deletion; Git history remains an archive. Partial coverage is not grounds for retirement. Use `claude_memory_sync --status` to verify the resulting local and remote state.
