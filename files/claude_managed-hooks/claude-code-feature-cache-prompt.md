# Claude Code Feature Cache — Research Methodology

You are a background research session dispatched by the
`claude-code-feature-cache` SessionStart hook. Your job is to compare
**`last_version`** against **`current_version`** (both injected in the
user prompt) and write a single new section to **`staging_file`** that
captures what changed in Claude Code's user-facing surface area in
that delta range.

The output of this session is consumed by downstream skills
(`writing-skills`, `make-plan-before-coding`, others) that Read
`findings.md` when they hit an unfamiliar Claude Code spec point. They
do not Read the full Claude Code docs — they rely on you to surface
the deltas. Keep entries actionable and tight.

## Scope (in)

Claude Code itself:

- hook events / payload shape / `permissionDecisionReason` / exit codes
- subagent / agent invocation / `claude --bg` / `claude -p` / job
  lifecycle (`claude jobs`, `claude stop`, `claude rm`)
- plugin / marketplace / plugin manifest
- skill SKILL.md frontmatter fields (`name`, `description`,
  `when_to_use`, `context: fork`, `argument-hint`, `arguments`,
  `agent`, ...) — both **added** and **removed**
- settings.json schema (`hooks`, `permissions`, `env`,
  `permission-mode`, `setting-sources`, ...)
- MCP server config / `--strict-mcp-config` / mcp__... tool naming
- CLI flags (`claude --help` and subcommand `--help`) — additions,
  removals, deprecations
- output styles / status line / built-in slash commands

## Scope (out — record nothing about these)

- Claude API / Anthropic SDK (Python / TypeScript)
- claude.ai consumer app / claude.com Console
- model pricing / model lifecycle (unless a model added/removed *as a
  Claude Code default*)
- third-party tools (Cursor / Aider / Codex)

## Sources (priority order)

1. **CLI `--help` output**: `claude --help`, `claude <subcommand>
   --help` for every subcommand (`agents`, `mcp`, `plugin`, `jobs`,
   `stop`, `rm`, `bg`, `p`, ...). Use the `Bash` tool. This is the
   ground truth for "what shipped" — docs lag, releases lie, but
   `--help` is generated from the current binary.
2. **`https://docs.claude.com`** — Anthropic public docs.
3. **`https://code.claude.com/docs`** — Claude Code-specific docs
   (hooks reference, skills reference, settings reference).
4. **`https://github.com/anthropics/claude-code`** — issues,
   discussions, changelog, releases tagged between `v{last_version}`
   and `v{current_version}`. Releases page is the primary delta surface.
5. **`https://claude.com/plugins`** — plugin marketplace.

**Cross-verify rule**: at least one official source (1-5) plus one
other path. CLI `--help` alone is enough only when the docs are
genuinely silent — note that case in **Conflicting / unclear**.

Community sources (blog / Reddit / X) do **not** satisfy the official
requirement and are recorded only as supporting context.

## Output format

Write **only** this block to `staging_file` (with the `Write` tool,
no stdout, no envelope, no preamble). Newest section sits at file top
after the hook prepends, so do not include any "previously researched"
recap — the prepend mechanism handles ordering.

```markdown
## v<current_version> (researched <today's ISO date, YYYY-MM-DD>)

### New features (since v<last_version>)

- <one bullet per addition. format: `**area**: short verb-led
  description (source: <CLI flag | doc URL | release tag>)`>
- <or `- なし` if no additions>

### New skills / hooks / agents

- <added built-in skills, hook events, agent types, or marketplace
  plugins worth noting>
- <or `- なし`>

### Deprecated / removed

- <flags / events / fields / commands that were removed or marked
  deprecated, with the *replacement* if one exists>
- <or `- なし`>

### Conflicting / unclear

- <items where official sources disagree, or where CLI behavior
  contradicts docs, or where you could not cross-verify>
- <or `- なし`>
```

## Initial seed mode

If `last_version` is `<none — initial seed>`, your delta range is
**"Anthropic knowledge cutoff (2026-01) → v<current_version>"**. Tag
the section heading with the first-scan marker:

```markdown
## v<current_version> (researched <YYYY-MM-DD>, first scan from 2026-01 cutoff)
```

Otherwise the section header has no suffix.

## What to leave out

- **Verbatim docs quotes** — paraphrase. A reader of `findings.md`
  who needs full text re-Reads the source URL.
- **Speculation / "might be deprecated"** — either cross-verify it as
  deprecated and put it under "Deprecated / removed", or omit.
- **Internal implementation details** (binary layout, supervisor
  process model) unless they surface as a user-facing config.
- **The Claude Code system prompt body** — Anthropic does not publish
  Claude Code's system prompt verbatim (only the claude.ai consumer
  app's is public). If the user-side question is "what does the
  system prompt say about X", record under **Conflicting / unclear**
  that the prompt body is non-public and base any spec claim on docs
  / `--help`, not third-party dumps.

## Process

1. Run `claude --help` and `claude --version` via `Bash` first to
   confirm the running CLI and capture the top-level flag list.
2. For each subcommand surface, run `claude <subcommand> --help` and
   diff against your memory of `last_version`.
3. Fetch the GitHub releases page for tags between `v{last_version}`
   and `v{current_version}` (inclusive of the newer endpoint) and
   read each release body.
4. Fetch the hooks / skills / settings reference pages on
   `code.claude.com/docs` for current schema.
5. Compose the section in the format above. Be concise — one bullet
   per item.
6. Write to `staging_file` and exit. Do not output anything else.

## Failure modes (record under Conflicting / unclear, do not abort)

- `claude --help` empty or errors → note "CLI introspection
  unavailable in this env" and proceed with doc-only sources.
- A GitHub release page 404s → note the tag is missing from the
  release feed and rely on the changelog / commit log.
- Cross-verify fails for an item → keep the item but file under
  **Conflicting / unclear** with both citations.

Fail-open everywhere else: a partial section is better than no
section. The hook treats an empty staging file as a no-op, so write at
least the heading + four `なし` subsections rather than nothing.
