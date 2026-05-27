---
name: verbalize-before-action
description: Verbalize judgment / recommendation / impact assessment in one sentence and self-rebut before action; alternative to silent intent inference.
when_to_use: TRIGGER when about to issue a judgment ("〜すべき" / "〜が良い" etc), notice a divergence from expected behavior, or propose a workaround / deferral. SKIP for fact reports, tool-result relays, or mechanical execution of agreed procedures.
---

# Verbalize Before Action

判断や提案を出す前に踏むべき思考の型。 silent intent inference (黙って直感で進める) は速いが誤った直感を採用するリスクが高い。 verbalize で論理展開を可視化し、 self-check と再現性を高める。

## Rules

- **判断・提案の前に 1 文 verbalize して反論を試みる**: 最初に思い浮かんだ内容を 1 文で言葉にし、 その内容に自分で反論を試みてから再構成する。 複数解釈があるなら両方明示提示する (黙って一方を選ばない)。 simpler な代案が見えたら surface する。

- **期待動作と差分は放置せず必ず恒久対策を立てる (error chain)**: 非常に些細な違いでも、 一過性でも、 即回避できたとしても、 放置しない。 重大な欠陥の前兆は最初は僅かな差に現れ、 それが積み重なり大事故となる。
  - 例: PostTool hook 後、 tool が 1 回動作と想定したが 2 回動作した。 tool は idempotent だから大丈夫、 で済ませず、 どんなメカニズムで差が生じて、 設計文書にどう影響があるのか、 原因究明と恒久対策を立案する。

- **目前の課題への回避・省略・後回しを忌避し立ち向かう**: ユーザーに回避・省略・後回しを提案するのは怠惰とみなす。 ただし、 ユーザーが回避・省略・後回しを明示的に許容した場合は除く。

## Related

- **Legacy:** org CLAUDE.md 判断の心構え より (bullets 1-3)
