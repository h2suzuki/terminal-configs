---
name: recognize-own-work
description: 「想定外」 系の驚き表現を発する前に git log / blame で履歴を確認し、 自分の commit が混ざっていないか verify する。
when_to_use: TRIGGER when about to say "想定外" / "予想外" / "思っていなかった" / "知らなかった" / "あれ?" / "そんな構造になっていたっけ?" 系の驚き表現を発する寸前、 または unfamiliar に見える file / 設計を「外部 / 他人由来」 と暗黙に仮定しそうな時。 SKIP for genuinely external systems (third-party libraries, API responses) or files with verified no own commit history.
---

# Recognize Own Work

「想定外」 系の驚き表現を発する前に、 該当 file / コンポーネントの履歴を verify し、 自分の commit が混ざっていないか確認する。 自分の作業を verify せず驚くと、 user から「過去作業を覚えていない」 と corrective input が入る。

## Process

1. 驚き wording を発しそうになった時点で**いったん停止**
2. 該当 file / dir の履歴を取得:
   - `git log --oneline <path>` で commit subject 列を確認
   - 必要なら `git blame <path>` で行単位の author を確認
3. 自分 (LLM) の commit が混ざっている場合 (`Co-Authored-By: Claude ...` の trailer 等):
   - 「想定外」 ではなく **「過去に自分が触った範囲」** として再認識
   - 必要なら当該 commit message を `git show <hash>` で読み rationale を recall
4. 自分の commit が無く、 真に外部 / 他人由来と verify できた場合のみ surprise 表現を許容

## Rationale

LLM session は揮発的なので、 前 session で自分が書いた code / 設計が「他人作業」 のように見える錯覚が起きる。 git log は 1 コマンド (`git log --oneline <path>`) で済むので verify cost が低い。 履歴 verify を省略して驚き表現を出すと、 user から「自分で書いたものを覚えていないのか」 と corrective input が入る (実際 2026-05-26 に発生)。

## Example

**❌ Bad** (verify せず驚く):
> install script に voicevox の copy 行が無いのは想定外。

**✅ Good** (verify 後の framing):
> `git log --oneline extra/voicevox.sh` で確認した結果、 `3f37a42 voicevox: Move install + alert hooks to extra/voicevox.sh` が自分の過去 commit。 voicevox の deploy 行は `extra/voicevox.sh` に切り出した形。

## Related

- `verify-spec-before-dismissal` — negation 前の spec verify (scope 違: あちらは仕様 dismissal、 当 skill は self-work recognition)
- `verify-before-asserting` — positive assertion 前の verify (orthogonal)
- `memory-routing` — 同種 correction を受けた場合の memory 化判定
