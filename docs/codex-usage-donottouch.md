# codex 利用規定 — 触らない箇所の一覧

ポリシーが何であれ緩めない安全側の規定。適用作業の対象から外す。
生成 2026-08-25。**各 file の実在を実測済み**。

## 4-1. 経路の gate (companion 直接起動の禁止)

- `codex-delegation/SKILL.md` — 実在
- `files/claude_managed-hooks/codex_delegation_gate.py` — 実在
- `todos.md` — 実在
- `user/h2suzuki/feedback_codex_plugin_route_only.md` — 実在

## 4-2. worktree 隔離

- `codex-delegation/SKILL.md` — 実在
- `files/claude_managed-hooks/codex_delegation_gate.py` — 実在 (2026-08-27 に worktree gate を統合: `[tree]` / `[same-root]`)

## 4-3. 監視規律

- `codex-delegation/SKILL.md` — 実在
- `codex_delegation_gate.py` — 実在
- `files/claude_managed-hooks/stop_checks.py` — 実在
- `files/codex_task_sentinel` — 実在
- `org/feedback_codex_broker_outlives_session.md` — 実在
- `org/feedback_codex_monitor_job_state.md` — 実在
- `org/feedback_unrequested_scale_rationalization.md` — 実在

## 4-4. 発注書規律

- `codex-delegation/SKILL.md` — 実在
- `codex_delegation_gate.py` — 実在
- `files/claude_managed-hooks/codex_order_scaffold.py` — 実在
- `files/codex_order_lint` — 実在
- `org/feedback_threat_model_in_review_order.md` — 実在
- `org/feedback_unrequested_scale_rationalization.md` — 実在

## 4-5. 受け入れの証拠規律

- `codex-delegation/SKILL.md` — 実在
- `docs/adversarial-review-methodology.md` — 実在
- `files/claude_lang_lint` — 実在

## 4-6. skill invoke の強制

- `codex_delegation_gate.py` — 実在
- `files/claude_managed-hooks/skill_reminder_gate.py` — 実在
- `org/feedback_codex_delegation_skill_skip.md` — 実在

## 4-7. その他、緩和で壊れるもの

- `codex-delegation/SKILL.md` — 実在
- `codex_delegation_gate.py` — 実在
- `feedback_auditor_verdict_deference.md` — 実在
- `files/claude_managed-skills/codex-delegation/template-review-order.md` — 実在
- `files/claude_managed-skills/handoff/crosscheck-prompt.md` — 実在
- `org/feedback_delegation_failure_no_self_impl.md` — 実在
- `org/feedback_inventory_existing_tools_first.md` — 実在
- `org/feedback_no_ui_design_delegation.md` — 実在
- `org/feedback_self_build_impulse.md` — 実在
- `project/…/feedback_adversarial_audit_model_selection.md` — **未解決**
- `template-fix-order.md` — 実在
- `template-order.md` — 実在
- `todos.md` — 実在

## 特に注意

- `files/codex_order_lint` の `review-kind` は `none` が既に正規値なので、
  「敵対レビューは必ずではない」は **lint を一切変えずに表現できる**。触ると gate を壊す
- 実装も回帰レビューも opus になる回が出るため、**実装・受け入れ・検証設計・認定の兼務禁止**は
  重要度が上がる。agent 分離を落とすと 53 巡ループの再発条件が揃う
- 別 project scope の memory entry は terminal-configs の方針変更で触らない
