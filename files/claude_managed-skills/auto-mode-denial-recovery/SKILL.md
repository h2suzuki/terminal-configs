---
name: auto-mode-denial-recovery
description: In auto mode (permission mode = auto), denial / blocked is gated by the classifier itself, so adding permissions to settings.json cannot bypass it (the denial message's suggestion to add a settings rule is misleading); the effective recoveries are `! manual execution` / skip / explicit user re-request.
when_to_use: TRIGGER when auto mode で a tool call is denied / blocked, or about to suggest 「settings.json に permission 追加で迂回」 etc. SKIP for non-auto permission mode or when user explicitly approved a settings.json change.
---

# Auto-Mode Denial Recovery

auto mode で classifier がアクションを deny した時、 denial message に 「settings に permission rule を追加してください」 と書かれていても、 settings.json への追加は迂回にならない。 auto mode では permission rule ではなく **classifier 自体が gate** となる。

## Rules

### Settings.json 迂回を提案しない

auto mode で deny されたとき、 ユーザーに 「settings.json に rule 追加で迂回」 を **提案しない**。 denial message の generic な誘導文言を verbatim 信用しない。

### 有効な選択肢 3 択

1. **`! <command>` 手動実行** — ユーザーに current session で入力してもらい、 shell として実行する (出力は私の context に返る)
2. **Skip** — 該当アクションを skip し、 別経路で目的達成する
3. **User 明示再依頼** — ユーザーが現在の turn で 明示的に再依頼することで classifier を通せる場合がある (user 意図が明確に turn 内にあると classifier が許可しやすい)

## Why

denial の出元が permission system でなく auto-mode classifier だから。 settings.json の permissions は permission mode が non-auto (default / plan 等) のときに rule 適用される。 auto mode では classifier が現セッションの user 意図 ・plan 文脈と照合して判断するため、 settings.json への追加は別レイヤーで効かない。 denial message の文言 (「settings に追加すれば許可される」 系) は generic で auto mode を考慮していない場合がある。

2026-05-25 セッションで `claude --bg -p` (Part 1 commits の /code-review spawn) が classifier に拒否され、 私が誤って 「settings.json に Bash(claude --bg *) permission rule 追加」 を提案。 ユーザーから 「auto mode なので settings.json の問題ではない」 と訂正。 同セッションで user 明示再依頼 (「プロンプトに依頼をかけばよい」) により 2 度目の spawn が通った。

## Related

- `verify-before-claim`: denial message を verbatim 信用せず一次仕様を verify する習慣と同 family
- `feature_findings_build.py` hook → `${XDG_CACHE_HOME:-~/.cache}/claude-code-feature-research/findings.md`: Claude Code ＋ Claude Developer Platform spec delta の cache (auto mode 周りの classifier 挙動も spec delta があれば記録される)
- **Legacy:** user memory `feedback_auto_mode_classifier_vs_settings.md` (2026-05-25 起票) より昇格
