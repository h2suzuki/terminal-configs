---
name: artifact-self-review
description: >
  Session を越えて残る artifact (README / 公開 doc / 教材 / spec / canonical ガイドライン / 設計書 / ライブラリ API / コードコメント) を編集する前に、
  分類 / 読者 / 節目的 / 不要な文 / jargon 適切性 を 1 文 verbalize する。
  対話相手のユーザーと artifact の読者は必ず別人。
  TRIGGER when: 「このドキュメントが解決した / 修正した / 書き直した」「旧 X との差分」「以前は…だった」「矛盾していたので一本化」 と artifact 本文に書き出そうとした瞬間 (赤信号フレーズ);
  artifact 本文に執筆経緯 / 旧版 changelog / reconciliation / 検証証跡 / 台帳参照 (C## / M## / H## 等) / ephemeral file 参照 (drafts/*.md) を入れようとしたとき;
  確定済みの選択肢を discussion ラベル (Plan C / Phase γ 等) で恒久 doc に書こうとしたとき;
  初心者向け文章に内部 jargon (last reviewed endpoint / cascade / SP 等) を混ぜようとしたとき。
  SKIP: ephemeral な scratchpad / drafts/*.md / commit message 本体 / 本セッション TUI 上の対話応答 (artifact ではない)。
---

# Artifact Self-Review

質の高い session-persistent artifact を書くための habit。 これは繰り返す regression のため強制ルール扱い。

## Rules

- **artifact の読者 ≠ 対話相手**: 編集する artifact (session を越えて残るもの) の読者は対話相手のユーザーと必ず別人。 旧版 / 本対話を知らない将来の自分 / 社外 / 初心者 を読者として書く。

- **編集前に 1 文 verbalize**: 「この artifact の分類は？ 読者は誰？ この節・文は読者の役に立っている？ 不要な文は含まれていない？ 読者 level に合わない jargon はないか？」 を 1 文で言葉にしてから編集に入る。
  - **分類の例**: README、 公開 doc、 教材、 spec、 canonical ガイドライン、 設計書、 ライブラリ API、 コードコメント、 ハウスキーピング文章。
  - **読者の例**: 初心者、 社外、 旧版も本対話も知らない将来の自分。
  - **不要な文の例**: 執筆経緯、 旧版 changelog、 reconciliation、 「今回直した / 解決した点」、 検証証跡、 台帳参照 (C## / M## / H## 等)、 ephemeral 参照 (drafts/*.md)。
  - **不適切な jargon の例**: 初心者向け文章に突然 last reviewed endpoint、 cascade、 SP などと書く。

- **赤信号フレーズで停止**: これで始まる節・文を書こうとしたら手を止め、 artifact 本文に書かず commit message か todos へ回す:
  - 「このドキュメントが解決した / 修正した / 書き直した」
  - 「旧 X との差分」
  - 「以前は…だった」
  - 「矛盾していたので一本化」

- **確定済みの選択肢を discussion ラベルで呼び続けない**: Plan C / Phase γ 等の discussion ラベルは選択肢併存時のみ使う。 確定後は descriptive name に変える。 恒久 doc に discussion ラベルを残さない。
