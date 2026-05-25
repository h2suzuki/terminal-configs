---
name: test-writing
description: テスト新規作成・編集時のルール (intent encoding・並行処理可視化・verify 対象拡張)。
when_to_use: TRIGGER when editing test files (paths で命名規約限定済み)。 SKIP for production code (use code-conventions)。
paths: "**/test_*.py, **/*_test.py, **/tests/**, **/__tests__/**, **/*.test.ts, **/*.test.tsx, **/*.test.js, **/*.spec.ts, **/*.spec.tsx, **/*.spec.js, **/*_test.go, **/*_spec.rb, **/spec/**, **/*Test.java, **/*Tests.cs"
---

# Test Writing

テスト新規作成・編集時のルール。 intent (WHY) を encode し、 観察可能性が必要な領域では可視化を作って完了判定する。

## Rules

### Intent encoding

テストは intent (WHY) を encode する。 business logic が変われば必ず fail するように書く。 implementation detail (中間関数名・内部 state) ではなく、 callers が依存する **外から見える振る舞い** を assert する。

### 観察可能性が必要な領域

以下のいずれかが関わる場合は 「気づきにくい」 と仮定し、 可視化 (log 追加 / trace / 状態 dump) を作って観察してから完了判定する:

- 並行処理
- 共有状態
- I/O 順序
- 多 component 連携
- external resource 操作
- event 順序依存

可視化なしに 「テスト通った」 だけで完了とすると、 race condition や境界条件で flake する。

### Verify 対象の拡張

「正しい結果が返るか」 だけでなく、 観察可能な動作品質も verify 対象に含める:

- race condition
- 処理順序
- 冗長計算
- 並列度
- 表示・出力の質

## Related

- **Legacy:** org CLAUDE.md §開発 b. テスト (全体) より
