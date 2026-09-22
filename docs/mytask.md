# Mytask

依頼の記録、大きな作業の分解、自分の計画の見直しを、Claude Code と Codex で共有します。
具体的な手順は [共通 Skill](../files/shared_skills/mytask/SKILL.md) を参照してください。
Claude Code は標準 Task を優先し、使えない場合は mytask MCP、Codex は mytask MCP を使います。
UserPromptSubmit hook はこの Skill の参照を促します。

## 既存環境への個別反映

mytask MCP が導入済みなら、リポジトリのルートで以下を実行して今回の指示変更を反映できます。

```bash
sudo install -D -m 644 files/shared_skills/mytask/SKILL.md /etc/codex/skills/mytask/SKILL.md
sudo install -D -m 644 files/shared_skills/mytask/SKILL.md /etc/claude-code/skel/skills/mytask/SKILL.md
install -D -m 644 files/shared_skills/mytask/SKILL.md ~/.claude/skills/mytask/SKILL.md
sudo cp files/claude_managed-CLAUDE.md /etc/claude-code/CLAUDE.md
sudo cp files/shared_hooks/plan_first_nudge.py /etc/claude-code/hooks/plan_first_nudge.py
sudo cp files/shared_hooks/plan_first_nudge.py /etc/codex/hooks/plan_first_nudge.py
sudo cp files/claude_managed-hooks/stop_checks.py /etc/claude-code/hooks/stop_checks.py
sudo cp files/shared_cli/mytask /usr/local/bin/mytask
```

他の Claude Code 利用ユーザーにも、それぞれの `~/.claude/skills/mytask/SKILL.md` を反映します。
対象エージェントを再起動し、mytask Skill と MCP の TaskList / TaskCreate / TaskUpdate が使えることを確認してください。
MCP が未導入の場合は、ユーザー環境の導入処理 `install_claude_extensions` に登録手順があります。
