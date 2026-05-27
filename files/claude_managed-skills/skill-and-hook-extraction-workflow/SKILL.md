---
name: skill-and-hook-extraction-workflow
description: Workflow applied across iterative sessions that extract CLAUDE.md rules into hooks / skills — implement + smoke + pair commit (code + CLAUDE.md deletion) + spawn /code-review skill in background via `claude --bg -p` + run next item in parallel + triage bg findings once idle + fixup-autosquash.
when_to_use: TRIGGER when user instructs "CLAUDE.md ルール X を hook / skill 化" repeated extraction work, or about to write a hook / skill that extracts a CLAUDE.md section. SKIP for single-shot creation or skill / hook unrelated to CLAUDE.md.
---

# Skill and Hook Extraction Workflow

CLAUDE.md ルールを hook / skill 化する繰り返し session の workflow。 pair commit + background `/code-review` + 次アイテム並走で iteration を高速化する。

## Process

### 1. Implement

hook / skill source + `files/claude_settings.json` の登録 + `ubuntu2404-wsl.sh` / `debian12.sh` の `copy` 行。

- **Skill (.md)**: body 末尾の `## Related` section に `- **Legacy:** org CLAUDE.md <旧 section 名> より [(scope 補足)]` を必ず付ける (frontmatter `legacy:` は公式 spec 未掲載なので body 側で表現する)
- **Hook (.py)**: module docstring に `Legacy: org CLAUDE.md <旧 section 名> より [(同上)]` を必ず付ける
- **編集履歴 / 経緯 / supersede narration を Legacy に書かない** (artifact-self-review / document-editor の discipline 対象 — 赤信号 framing 違反)
- **User-invoked only な skill**: YAML frontmatter に `disable-model-invocation: true` を付け、 description を user 向け一行サマリにする (TRIGGER/SKIP boilerplate は無意味)

### 2. Smoke test

隔離 HOME 等で挙動確認 (成功・失敗・edge case を 4-8 ケース)。

### 3. Pair commit 1: hook / skill 追加

source + settings + deploy script + .gitignore 等の付随を 1 commit。

### 4. Pair commit 2: CLAUDE.md 削除

`claude_system-CLAUDE.md` (or `claude_user-CLAUDE.md`) から該当 rule 行を削除。

### 5. /code-review を background spawn

`claude --bg -p "<prompt>"` を別プロセスで起動。 `-p` 必須 (これがないと session は対話モード待機で prompt 実行されず即 idle)。 `--bg` / `-p` は `claude --help` 未掲載だが実機で動作する hidden flag (v2.1.150 で確認)。 spawn 出力に session_id が返る。

prompt は findings を file に吐く形:

```
Run /code-review against the most recent pair (HEAD~2..HEAD by default;
adjust if the iteration committed a single combined change).
Write the JSON findings array to /tmp/code-review-<sessionId>.json
(no auto-fix — main session applies CONFIRMED fixes and squashes).
```

### 6. 次の rule extraction instruction を即受付

bg session が走っている間、 main session は次のアイテムに進む。 通常 `/code-review` は user が `かけましょうか` と聞かない限り spawn しないが、 本 workflow では毎アイテムで spawn する (user 同意 standing)。

### 7. Bg idle 後の triage + fixup-autosquash

`claude agents --json | jq '.[] | select(.sessionId|startswith("<id>"))'` で status 確認 (`busy` / `idle` / 消失)。 `idle` 確認後、 `/tmp/code-review-<sessionId>.json` を Read で読み込み、 findings を triage:

- **CONFIRMED** → file 編集 → `git commit --fixup=<code-commit-sha>` → `GIT_SEQUENCE_EDITOR=true git rebase --autostash -i --autosquash <code-commit-sha>^`
- **PLAUSIBLE** → 判定 (fix / 保留 / 却下) を 1 つずつ
- **REFUTED** → drop

`--autostash` は worktree に他の未 staged 変更がある場合に必須、 `GIT_SEQUENCE_EDITOR=true` は TODO editor を空回りさせて autosquash 順を採用する。 1 ルール抽出 = 2 commit (code + CLAUDE.md) を固定する。 push 前なので reflog で reversible、 destructive permission 不要。

**Cleanup**: `claude stop <id>` (process 終了) → `claude rm <id>` (session 記録 + worktree 削除)。 stop と rm は両方必要 — stop だけだと session 記録と worktree が残る。

## Rules

### Message を fixup と一緒に更新したい場合

`--fixup=reword:<sha>` は `-m` と排他なので、 `git reset --soft <pair-の親>` で un-commit して **再 commit** する方が clean。 worktree 上のすべての変更を再 stage して、 新 message で再 commit する (pre-push かつ reversible、 permission 不要)。

## Why

foreground で `/code-review` を待つと、 5+ finder agents × 数十秒で作業が止まる。 pair commit 自体は smoke test 後の小規模変更で reversible (push 前なら `git reset` / `revert` で巻き戻せる)。 review 完了を待つ前に commit しても安全。 2026-05-23 セッションで read_before_edit hook を実装した時に user が明示提示。

## Related

- `commit-discipline`: 通常の commit 規律。 本 skill は extraction workflow 固有の pair commit pattern を追加
- `claude-code-feature-research.sh` hook → `${XDG_CACHE_HOME:-~/.cache}/claude-code-feature-research/findings.md`: `claude --bg -p` / `claude agents` 等 hidden flag の delta を SessionStart bg research で累積
- `subagent-gate`: bg spawn は subagent の 1 form (parallelizable / specialized agent domain 条件をクリア)
- **Legacy:** project memory `feedback_rule_extraction_workflow.md` (2026-05-23 起票) より昇格
