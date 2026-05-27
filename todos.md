# Todos

## Critical

### feature-cache-rename — bg dispatch verify

Goal: 新規 `claude` session で SessionStart hook の bg dispatch が permission ask なしで走り、 `~/.cache/claude-code-feature-research/findings.md` が生成されることを実機 verify する。

Exit Criteria:
- [ ] 新規 session 起こして bg dispatch が走った (`claude agents --json` で `busy` または `idle`)
- [ ] 10 分後に `~/.cache/claude-code-feature-research/findings.md` が生成されている

Work file: `last-session-handoff.md`
