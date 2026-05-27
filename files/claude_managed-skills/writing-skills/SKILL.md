---
name: writing-skills
description: Meta-skill for writing or editing skills and hooks consistently — frontmatter format, section structure, language convention, deploy locations.
when_to_use: TRIGGER when about to Write / Edit a skill SKILL.md or a hook script, when designing a new skill / hook from scratch, when reviewing skill format consistency, or when about to ask "skill のフォーマットは合ってる?" type question to user. SKIP for ephemeral text or one-off scripts that will not be registered as a Claude Code skill / hook.
---

# Skill Writing

skill SKILL.md / hook script を書く時の format 統一・writing convention のメタ skill。 template と既存 skill を参照し、 user に「format 合ってる?」 と毎回確認する冗長性を排する。

## Process

1. **Read the templates first** — `template-skill.md` (skill 用) と `template-hook.md` (hook 用) を SKILL.md の隣 (本 skill dir 内) から Read で読む。 frontmatter field 全列挙と writing convention の inline reminder が入っている。
2. **Cross-reference an existing skill** — 同じ project 内の既存 skill を 1-2 個 sample で Read する (例: `verify-before-asserting`, `subagent-gate`, `writing-code`)。 frontmatter pattern と section 構成が template 通りか実例で確認。
3. **Apply writing convention** — frontmatter description / when_to_use / headers は **英語**、 body は **日本語可**。 trigger keyword だけ quoted 日本語 OK。 詳細は `template-skill.md` の commented cheatsheet (本 skill dir 内) を参照。
4. **Verify the deploy path** — managed (org-wide) vs user (個人) を意識:
   - managed: `files/claude_managed-skills/<name>/` → `/etc/claude-code/skills/<name>/` + symlink to `~/.claude/skills/<name>`
   - user: `files/claude_user-skills/<name>/` → `~/.claude/skills/<name>/` (実 dir、 install script で copy)
5. **Sync both source and deploy target** — deploy 先だけ編集して repo の source を放置すると、 次に repo から再 deploy した時点で改造が静かに消える regression を抱える。 source 編集と deploy 先への `cp` を同 session 内で完結させる

## Rules

- **frontmatter は英語、 body は日本語可**: 中途半端な日英 mix は禁止 (例: `description: Rules for X (categories 日本語).` は NG)
- **TRIGGER + SKIP の pair**: when_to_use は両方明示。 片方だけは ambiguous
- **`##` headers は Process / Rules / Output / Related 優先**: 内容に合わない場合のみ他の英語名 (Sources / Examples / Definitions / Red flags 等)
- **Related section で隣接 skill を citation**: skill 名 symbolic (例: `writing-code`) で。 重複や orthogonal scope の明示で family 化。 repo deploy 範囲外 path / skill dir 外 file / ephemeral tag は **citation しない** (詳細は `writing-code` Rules)
- **description tighten 時**: 削った詳細を body に明文化 (frontmatter 短縮 ≠ 情報削除)
- **trigger 列挙の精度**: specific phrase を quote する。 一般化しすぎると trigger 不発火
- **No dangling-prone references**: SKILL.md / hook / template にrepo deploy 範囲外 path / skill dir 外 file への file path citation / ephemeral tag / 会話文脈依存 reference を残さない。 詳細: `writing-code` Rules

## Output

新規 / 編集後の skill は:

- syntax: YAML frontmatter が valid (`---` で挟まれ、 colon の前後に space)
- deploy: source と deploy 先で `diff -q` 一致
- registration: 新 skill 追加時は Claude Code が自動 discover (session 中の skill 一覧に出現)

## Related

- `template-skill.md` (本 skill dir 内) — skill SKILL.md の commented template
- `template-hook.md` (本 skill dir 内) — hook script + settings.json entry の template
- `claude-code-guide` — Claude Code 公式 spec を primary source で verify
- `writing-code` — Rules に「No dangling-prone references in persistent files」 (新規環境 deploy で参照解決できない reference を永続 file に入れない: repo 範囲外 path / skill dir 外 file path / ephemeral tag / 会話文脈依存)
