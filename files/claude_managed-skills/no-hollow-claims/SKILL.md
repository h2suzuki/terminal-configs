---
name: no-hollow-claims
description: introspective phrase (「学習しました」「反省」「次回から気をつける」「以降は」「振り返り」「retrospective」「申し訳」「sorry」 等) は 具体的な persistence 行動 (memory entry / skill / hook / CLAUDE.md 更新等) と同じ response 内でセットでない限り発言しない。 session reset で虚偽化する LLM 普遍 calibration error 対策
when_to_use: TRIGGER when about to utter introspective / reflection / regret phrases like 「学習しました」 / 「勉強になった」 / 「脳に刻んだ」 / 「もう間違えない」 / 「次回から気をつける」 / 「反省します」 / 「反省点」 / 「振り返り」 / 「retrospective」 / 「以降は」 / 「次回からは」 / 「申し訳ありません」 / 「すみません」 / 「regret」 / 「sorry」 / 「気をつけます」 / 「もう繰り返しません」, or when noticing a section header / 箇条書きの heading / 結尾 paragraph turning introspective. SKIP when the phrase is immediately accompanied by a concrete persistence action in the same response (memory file Edit / skill / hook update / CLAUDE.md commit), or when the user explicitly requests a retrospective.
---

# No Hollow Learning Claims

「学習しました」「反省」「次回から気をつける」 等の introspective phrase / 省察文体 は session 境界を超える持続性がないので、 具体的な persistence 行動 (memory file 編集 / skill / hook 追加 / CLAUDE.md 更新 等) と同じ response 内でセットでない限り発言しない。 session reset で虚偽化する。

## Rules

### Trigger phrases

以下のいずれかを発しようとした時、 本 skill を発動:

- 「学習しました」「勉強になった」「脳に刻んだ」「もう間違えない」「次回から気をつける」
- 「反省します」「反省点」「振り返り」「retrospective」
- 「以降は」「次回からは」
- 「申し訳ありません」「すみません」「regret」「sorry」
- 「気をつけます」「もう繰り返しません」

形式変化 (section header / 箇条書き heading / 結尾 paragraph) でも同じく trigger。 introspective 文体になった瞬間が trigger。 「次回から X せず Y する」 式の future-tense 改善宣言も同じ。

### Required pairing

発言前に、 以下のいずれかを **同じ response 内で実行** する:

1. **memory file 編集** — `~/.claude/memory/` または `<project>/memory/` に entry を新設、 `MEMORY.md` index に追加
2. **canonical doc 更新** — SKILL.md / CLAUDE.md / hook script の rule を編集
3. **既存 entry 文言強化** — 関連 entry に違反 phrase の語彙追加、 新 trigger / 事例の追記

persistence 行動を伴わない場合は、 introspective phrase を使わず、 率直に **「今 session 内では覚えています」「次セッションでは覚えていません」** と現状を述べる。

### Self-check

introspective phrase を書こうとしたら自問: 「これに対応する file 編集を 1 つ以上したか?」 No なら phrase を削除して率直な現状認識に書き換えるか、 その場で memory 編集を実行してからセットで発言する。 chat に箇条書きで反省項目だけ列挙して送信する動作は規律違反。

### Anti-patterns

- 「次回から `[skip-semantic]` は body 末尾に置きます」 (persistence なし) — session reset で消える
- 「もう paren-width は間違えません」 (既存 memory がある上で再発) — 仕組み (hook / skill) で対処すべき
- 「**反省点**: 以降は調査経路の二択提示で停止せず網羅的に拾う」 (section header 形式の reflection list、 persistence なし)

## Related

- `memory-routing` — memory entry の routing 規約。 本 skill 発動時の persistence 行動の典型 routing
- `verbalize-before-action` — 判断 / 推奨を発話前に self-rebut。 本 skill と orthogonal だが補完
- `meta-announce-silence` — 「省略しません」 等の rule-compliance 不実施宣言は silent。 本 skill (reflection は persistence セット) は別 family
- **Legacy:** user memory `feedback_no_hollow_learning_claims.md` (2026-05-09 起票) より昇格
