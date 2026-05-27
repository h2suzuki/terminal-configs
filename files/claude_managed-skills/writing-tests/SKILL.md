---
name: writing-tests
description: Rules for designing / editing tests (TDD discipline, design-claim enumeration, intent encoding, coverage techniques, observability, verify target expansion).
when_to_use: TRIGGER when designing or editing test code (proposing test cases in chat, enumerating design claims, sketching tests in drafts/, planning TDD red phase, sweeping existing tests against design docs). SKIP for production code.
paths: "**/test_*.py, **/*_test.py, **/tests/**, **/__tests__/**, **/*.test.ts, **/*.test.tsx, **/*.test.js, **/*.spec.ts, **/*.spec.tsx, **/*.spec.js, **/*_test.go, **/*_spec.rb, **/spec/**, **/*Test.java, **/*Tests.cs"
---

# Test Writing

テスト設計・新規作成・編集時のルール。 TDD で進め、 設計クレームを 1 つずつ assert に書き起こし、 intent (WHY) を encode する。 観察可能性が必要な領域では可視化を作って完了判定する。

## Rules

### TDD discipline

新規実装・バグ修正には red → green → refactor の TDD サイクルを必須とする。

1. 設計クレームや期待挙動を文章で列挙
2. 各クレームに対応する **failing test** を先に書く (red phase)
3. test を pass させる最小実装 (green phase)
4. refactor で構造を整える (test は不変)

「実装してからテストを書く」は推奨しない。 実装と test が同じ盲点を共有しカバレッジが false-high になる。 「test を書きながら実装」 もダメ。 必ず red を先に作る。

### Design claim enumeration

設計 doc (ARCH / SKILL / spec / 製品コードの docstring 等) に書かれた請求項 (claim / invariant / 不変条件) を 1 つずつ enumerate し、 各 claim に対応する assert を必ず置く。

手順:

1. canonical doc から claim を抽出 (ID 付与: TR1, L2-2, LV など)
2. 既存 test を sweep し、 各 claim の coverage 状況をマップ
3. 設計と矛盾する assert (= bug を仕様として固定している) は削除
4. 未 cover な claim に対応する new test を追加 (TDD 順序で)

「設計 doc に書いてあるのに test が無い」 状態は regression 温床。 design ↔ test の対応表を維持する。

### Coverage techniques

「正しい結果が返るか」 だけでなく、 以下の coverage 観点も verify 対象に含める。

- **Branch coverage**: 条件式の真偽両側、 早期 return 条件、 fall-through path
- **Boundary value analysis**: off-by-one、 empty・1 件・N 件、 min・max、 timeout 直前 / 直後
- **Equivalence partitioning**: 入力空間の代表点 1 件ずつ
- **Error path**: exception、 失敗 retry、 partial failure、 cleanup ordering
- **Race / ordering**: 並行処理、 event 順序、 I/O ordering の non-deterministic path

実装で if branch を増やす度に、 各 branch に test がぶら下がっているか確認する。

### Intent encoding

テストは intent (WHY) を encode する。 docstring に **設計クレーム ID と出所** を書く (例: "TR3 / ARCH III-7 line 444: dispatch derivation と tag rule は same predicate を共有")。 implementation detail (中間関数名・内部 state) ではなく、 callers が依存する **外から見える振る舞い** を assert する。

business logic が変われば必ず fail するように書く。 implementation 変更で test を直す事態は intent encoding が弱い証拠。

### Observability requirements

以下のいずれかが関わる場合は「気づきにくい欠陥がある」と仮定し、 能動的に可視化 (log 追加 / trace / 状態 dump) し、 観察してから完了判定する。

- 並行処理
- 共有状態
- I/O 順序
- 多 component 連携
- external resource 操作
- event 順序依存

可視化なしに 「テスト通った」 だけで完了とすると、 race condition や境界条件で flake する。

### Verify target expansion

「正しい結果が返るか」 だけでなく、 観察可能な動作品質も verify 対象に含める。

- race condition
- 処理順序
- 冗長計算
- 並列度
- 表示・出力の質

### No dangling-prone references in persistent files

test code / docstring / fixture comment に **dangling reference** を入れない: repo deploy 範囲外の path (`~/.claude/global-memory/`, `~/.claude/projects/.../memory/` 等)、 ephemeral tag (Action Item 番号 / Plan C 等の一時ラベル <!-- dangling-ref-check: allow -->)、 「先ほどのテスト」 系の会話文脈依存 reference 等。 判定基準: 新規環境で repo install したとき参照解決できない reference。 詳細: `writing-code` Rules 参照。

## Related

- **Legacy:** org CLAUDE.md §開発 b. テスト (全体) より
