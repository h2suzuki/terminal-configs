---
name: memory-routing
description: Save a user correction or durable lesson to the shared memory clone, choosing org, user, or project scope and reusing an existing entry when appropriate. Use when asked to remember, record lessons learned, or route memory; also after repeated feedback. Do not use for ordinary notes or temporary task state.
---

# Memory routing for Codex

Claude Code and Codex share the entry store at
`/var/lib/claude-rag-memory/claude-lessons-learned`. The GitHub repository behind
that clone is canonical. Codex's own local memories are separate; this skill
uses the shared store deliberately.
Recording a correction does not authorize a new skill. Create one only when
the user explicitly asks for it.

1. Search before writing:
   `python3 /etc/claude-code/skel/hooks/memory_surface.py --search "<lesson>"`.
   Compare the actual corrective behavior, not just similar keywords. If an
   existing entry teaches the same action, update it and add this model's tag.
2. Choose scope: `org/` for a user-independent lesson across projects;
   `user/<login>/` for this person's preferences or circumstances;
   `project/<project-id>/` for a repository-specific defect or rule. When in
   doubt, use the narrower scope. Obtain the project id with
   `python3 /etc/claude-code/skel/hooks/memory_surface.py --project-id`.
3. Write a `feedback_*.md` entry with frontmatter `name`, `description`,
   `metadata.type: feedback`, `reminder`, `keywords`, `models`, `check`, and
   `when: prompt`. Keep `reminder` to one actionable sentence (150 characters
   or fewer); make keywords selective, and tag only models in which the failure
   was observed. The body has `## 理由` and `## 事例` with an absolute date;
   `## 対処` and `## 関連` are optional. `check` names one concrete inspection
   of the last output (100 characters or fewer).
4. Pass the complete entry on stdin to `claude_memory_sync --write <absolute
   entry path>`. That command validates the format, writes the clone, updates
   the index, commits and schedules a push. If it fails, report the actual
   state from `claude_memory_sync --status`; do not claim it was saved.

The Codex `UserPromptSubmit` hook queries the same index. It surfaces only
entries tagged for the active Codex model, within the current org/user/project
scope, and only when the prompt matches strongly enough. It never blocks a
prompt. A newly written entry may first become visible in the next session.

Do not write a new entry when an existing one already covers the behavior.
For a correction about one codebase, do not broaden it into a universal rule
without evidence from another context.
