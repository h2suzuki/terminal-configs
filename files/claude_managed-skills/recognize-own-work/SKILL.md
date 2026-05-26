---
name: recognize-own-work
description: Verify related commits and read commit messages before voicing surprise expressions; state facts instead of making a binary self-vs-other judgment.
when_to_use: TRIGGER when about to voice surprise expressions like "想定外" / "予想外" / "思っていなかった" / "知らなかった" / "あれ?" / "そんな構造になっていたっけ?" / "自分の知らない変更", or when about to implicitly treat an unfamiliar file / design as "external / from someone else". SKIP for genuinely external systems (third-party libraries, API responses) when no related commit exists in the local repo.
---

# Recognize Own Work

「想定外」 系の驚き表現を発する前に、 該当 file / コンポーネントの関連 commit を verify し、 commit message から背景を理解する。 主目的は **事実 (commit 履歴と rationale) を述べる** こと。 「自分の作業か他人の作業か」 の binary 判定はせず、 commit message が読めれば設計の背景は recover できる。

## Process

1. 驚き wording を発しそうになった時点で**いったん停止**
2. 該当 file / dir の関連 commit を取得: `git log --oneline <path>`
3. 関連 commit があれば commit message を読む: `git show <hash>` または Read で本体
4. **事実を述べる** — commit subject / 背景 / 経緯。 「想定外」 ではなく「この設計は `<hash>` で `<理由>` により導入」 と framing
5. 自他判定の補助 signal (binary に分けない):
   - `Co-Authored-By: Claude ...` trailer が **あれば** 過去 session で自分が co-author した **可能性が上がる**
   - trailer が **無くても** 自分の作業の可能性は排除できない (LLM が常に trailer を付けるとは限らない)
   - したがって trailer 欠如で 「自分ではない」 と断定してはならない

## Rationale

LLM session は揮発的で、 前 session の自分作業が unfamiliar に見える錯覚が起きる。 git log + commit message read で背景理解すれば、 驚きを「設計の rationale を確認した上での事実陳述」 に置き換えられる。 `Co-Authored-By: Claude` trailer は自分の関与の **強い肯定 signal** だが、 **欠如は否定 signal にならない** (trailer 失念ケースあり)。 自他判定で binary に分けず、 事実を述べる discipline が重要。

「自分の知らない変更」 という framing は特に危険: user から「それをやったのは以前のセッションの自分だよ」 と突っ込みが入る class の wording。 trigger に明示登録済。

## Example

**❌ Bad** (verify せず驚く):
> install script に voicevox の copy 行が無いのは想定外。

**❌ Bad** (Co-Authored-By 欠如で「自分ではない」 と誤断):
> `3f37a42` の commit message に Co-Authored-By: Claude が無いから、 これは私の作業ではない。

**✅ Good** (事実陳述):
> `git log --oneline extra/voicevox.sh` で `3f37a42 voicevox: Move install + alert hooks to extra/voicevox.sh` を確認。 commit message を読むと voicevox を base install script から `extra/voicevox.sh` (opt-in installer) に切り出した経緯が記載されている。 deploy 行はそちらに移っている。

## Related

- `verify-spec-before-dismissal` — negation 前の spec verify (scope 違)
- `verify-before-asserting` — positive assertion 前の verify (orthogonal)
- `memory-routing` — 同種 correction を受けた場合の memory 化判定
- `skill-writing` — skill の format / writing convention 統一
- (global memory) `feedback_verify_before_persisting_claims` — persist 前に concrete claim を git log / file 実体で照合 (隣接 scope)
- (global memory) `skill-text-language` — frontmatter description / when_to_use は英語、 trigger keyword のみ quoted 日本語
