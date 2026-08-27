#!/usr/bin/env python3
r"""Acceptance tests for codex_order_lint, written by the ordering side before the rewrite.

Black box: the CLI is started as a subprocess and only its stdout, stderr and exit code are
read; nothing is imported from it. Every document is linted alone in a temp directory, so the
sibling `fix round` scan sees only what a test puts there.

Contract (each claim maps to the tests named test_c<N>_*):
  C1  `codex_order_lint ORDER.md ...` prints one `{path}: {finding}` line per finding, then
      `{N} 件の規約違反`, and exits 1 with findings / 0 without. Findings keep a fixed order:
      slot / review contract / required sections / report path / terminal token / estimate /
      rulings / prohibitions / command fence / fix contract. A path that is not a regular file,
      an OSError while reading, and a non-UTF-8 body each print one reason line on stdout and
      exit 2. No path at all, `--new` with a path count other than 1, and the retired
      `--selftest` flag are argparse errors (usage on stderr, empty stdout, exit 2).
  C2  Fence normalisation: inside a ``` fence a heading, a `review-kind:` declaration, a
      `# fix round` H1 and a numbered ruling are invisible to every check. The exceptions are
      the `未記入` slot count and the report path / estimate scans, which read the whole text.
  C3  Slots: one finding as soon as any `未記入` remains --
      `未記入 の slot が {N} 件残っている: L.., ..` with the first 8 line numbers and ` 他 {n} 行`.
  C4  `review-kind:` must be exactly one line-head declaration valued adversarial|acceptance|none;
      otherwise one finding and every review-side check is skipped. adversarial and acceptance
      additionally require a non-empty `## 既製手段の棚卸し` and exactly one `scope: diff|artifact`.
      No scope-reason, target or verdict-item requirement exists.
  C5  The seven required sections (スコープ / 成果物 / 作業量上限 / 実行してよい command /
      適用される既存裁定 / 出力言語規約 / 所要見積もり) each give `必須の節がない: ## {節}` when no
      heading of level 2 or deeper starts with that name. A section body runs to the next heading of
      the same or a shallower level, so `###` subheadings and their text belong to the body.
  C6  Report path: `[\w./-]*-report\.md` over the whole text -- zero matches is one finding, two or
      more distinct matches is `報告書 path が食い違う: {sorted / joined}`, exactly one feeds
      `report_path` in the metadata.
  C7  Terminal token: the fence-outside lines containing `最終行` must yield an `[A-Z][A-Z0-9_]{3,}`
      token, else one finding. How often the token appears elsewhere is not checked.
  C8  Estimate: no `見積もりバンド ... N〜M 分` is one finding; a band without
      `調査発動しきい値 ... K 分` is one finding. The threshold's ratio to the band is not checked.
  C9  Rulings: the fence-outside body of `## 適用される既存裁定` must carry at least one `N.` item.
      Their numbering is not checked.
  C10 Prohibitions are three independent findings -- `fuser -k` and `pkill` both present, a
      commit-refusal phrase, and the literal `触らない` -- and the `## 実行してよい command` body
      must contain a fence opener.
  C11 fix contract: a document is a fix order when it carries a `# fix round N:` H1 or a
      `## 修正方式` section (prefix match, so a note after the name is fine). It needs exactly one `review-kind: none`, exactly one round H1, a
      non-empty `## 前巡 verdict` from round 2 on, non-empty `## 2 方向分析` and `## 掃引`, and every
      `所見` line of `## 修正方式` naming 仕様縮小 / 削除 / 既存集約 / 機構追加. `## 全数列挙` and
      `## 依存閉包棚卸し` are not required, and naming 機構追加 pulls in no further section.
  C12 処置の種別 (new): from round 3 on a fix order needs a non-empty `## 処置の種別` naming exactly
      one of 削除・縮小 / 契約の訂正 / 構造化 / bounded-risk 受入 / 廃棄. Missing or empty is one
      finding; present but naming zero, two or only out-of-list words is one finding. Rounds 1 and
      2 are exempt.
  C13 Sibling scan: the `# fix round N:` declarations of the sibling `*.md` files are collected
      only to report `fix round が重複している: {N}` when one N is claimed twice. A gap in the
      sequence and a round below an already existing later round are not findings.
  C14 `--metadata` prints one JSON object per document and no finding lines. Keys are path str /
      order_document bool / review_kind str|null / round int|null / scope str|null /
      methods list[{finding: int|null, methods: list[str]}] / has_previous_verdict bool /
      report_path str|null / findings list[str]. The exit code still follows the findings.
  C15 `--new plain|fix|review PATH` seeds from the codex-delegation template directory (repo-adjacent
      copy first, deployed copy second; both ship the same three files) and prints
      `{path}: {template} から作成した`. It fills `{stem}-report.md`, `{stem}-probe.txt`,
      `# {stem} 報告書` and the title `: {stem}`, and leaves every other `未記入` slot. `fix` numbers
      the round as max(sibling rounds)+1, drops `## 前巡 verdict` at round 1 and `## 処置の種別` below
      round 3. An existing path exits 3 without overwriting it; an unwritable path prints one reason
      line on stdout and exits 2.
  C16 The retired judgements never come back: no finding may contain `機構追加には`, `逆行している`,
      `が欠番`, `終端 token` together with `書式例`, `target:`, `verdict 要件`, `scope-reason`,
      `裁定の採番`, `2 倍でない` or `none と本文` -- neither over the embedded corpus nor over
      documents built to provoke each of them.
  C17 Corpus replay: the seven embedded real orders produce exactly the finding lists recorded
      here.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from typing import Any

CLI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "codex_order_lint")


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, CLI, *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def seed(directory: str, name: str, text: str) -> str:
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def invoke(
    text: str, flags: tuple[str, ...], siblings: dict[str, str] | None
) -> tuple[subprocess.CompletedProcess[str], str]:
    """兄弟走査が test の置いた file だけを見るよう、 temp directory で 1 本だけ lint する。"""
    with tempfile.TemporaryDirectory() as tmp:
        for name, body in (siblings or {}).items():
            seed(tmp, name, body)
        path = seed(tmp, "order.md", text)
        return run(*flags, path), path


def lint(text: str, siblings: dict[str, str] | None = None) -> tuple[int, list[str]]:
    proc, path = invoke(text, (), siblings)
    prefix = f"{path}: "
    return proc.returncode, [
        line[len(prefix) :]
        for line in proc.stdout.splitlines()
        if line.startswith(prefix)
    ]


def meta(
    text: str, siblings: dict[str, str] | None = None
) -> tuple[int, dict[str, Any]]:
    proc, path = invoke(text, ("--metadata",), siblings)
    record = json.loads(proc.stdout)
    del record["path"]
    return proc.returncode, record


def swap(text: str, old: str, new: str) -> str:
    if old not in text:
        raise AssertionError(f"fixture が {old!r} を含まない")
    return text.replace(old, new)


def drop(text: str, needle: str) -> str:
    return "".join(
        line for line in text.splitlines(keepends=True) if needle not in line
    )


def missing(*names: str) -> list[str]:
    return [f"必須の節がない: ## {name}" for name in names]


REQUIRED = (
    "スコープ",
    "成果物",
    "作業量上限",
    "実行してよい command",
    "適用される既存裁定",
    "出力言語規約",
    "所要見積もり",
)
KIND = "review-kind: adversarial|acceptance|none を行頭形式で 1 行指定せよ"
NO_INVENTORY = "## 既製手段の棚卸し に検討した既製 command/skill と不使用理由を列挙せよ"
NO_SCOPE = "scope: diff|artifact を行頭形式で 1 行指定せよ"
NO_REPORT = "報告書 path (*-report.md) が 1 度も書かれていない"
MIXED_REPORT = (
    "報告書 path が食い違う: drafts/example-report.md / drafts/other-report.md"
)
NO_TOKEN = "報告書の最終行に置く終端 token が指定されていない"
NO_BAND = "見積もりバンド (N〜M 分) が無い"
NO_THRESHOLD = "調査発動しきい値 (K 分) が無い"
NO_RULING = "適用される既存裁定が 1 件も列挙されていない"
NO_KILL = "kill-by-port (fuser -k / pkill) の禁止が書かれていない"
NO_COMMIT = "commit しない旨が書かれていない"
NO_TOUCH = "触らない path が明示されていない"
NO_FENCE = "実行してよい command が code fence で列挙されていない"
FIX_KIND = "fix 発注書は review-kind: none と fix round header を指定せよ"
FIX_HEADER = "fix 発注書は # fix round N: の H1 header を 1 行指定せよ"
FIX_PREVIOUS = "fix round 2 以上には必須の節がない: ## 前巡 verdict"
FIX_TWOWAY = "fix 発注書に必須の節がない: ## 2 方向分析"
FIX_METHOD_SECTION = "fix 発注書に必須の節がない: ## 修正方式"
FIX_METHOD = "## 修正方式 で各所見に 仕様縮小 / 削除 / 既存集約 / 機構追加を列挙せよ"
SWEEP = (
    "## 掃引 に各所見の欠陥定義 1 行と、同欠陥の全 site を機械列挙する grep/AST command と結果、"
    "または単一 site である根拠を記載せよ。指摘 site だけの修正による配り漏れと多巡消費を防ぐため"
    "class 単位で掃引せよ"
)
TREATMENTS = ("削除・縮小", "契約の訂正", "構造化", "bounded-risk 受入", "廃棄")
TREATMENT_MISSING = (
    "fix round 3 以上には必須の節がない: ## 処置の種別 ("
    + " / ".join(TREATMENTS)
    + " の 1 つを名乗る)"
)
TREATMENT_CHOICE = (
    "## 処置の種別 で " + " / ".join(TREATMENTS) + " のちょうど 1 つを名乗れ"
)
# 落とした判定の marker。 どの所見にも二度と現れてはならない。
RETIRED = (
    "機構追加には",
    "逆行している",
    "が欠番",
    "target:",
    "verdict 要件",
    "scope-reason",
    "裁定の採番",
    "2 倍でない",
    "none と本文",
)


def retired(finding: str) -> bool:
    return any(mark in finding for mark in RETIRED) or (
        "終端 token" in finding and "書式例" in finding
    )


# 現行 CLI の CONFORMING (files/codex_order_lint) を発注側の正本として引き継いだ最小 conforming 発注書。
CONFORMING = """\
# 発注書: 例

review-kind: none

## 目的

例である。

## スコープ

読んでよい path は `files/x` のみ。 **触らない path** は上記以外の全て。

## 成果物

- 報告書 1 file のみ: `drafts/example-report.md`
- commit もしない

## 作業量上限 (worst-case bound)

- 読む file は 1 本のみ

## 実行してよい command

```
python3 files/x --metadata drafts/example.md
```

- `fuser -k` / `pkill` 等の kill-by-port は禁止

## 適用される既存裁定 (これに反する指摘は不成立)

1. **裁定 A**: 説明
2. **裁定 B**: 説明

## レビューの観点

新規 material 指摘を探す。

## verdict 要件

1. 指摘の振り分け: 用途内欠陥 / 場外 / 境界に分類する。
2. 受入判定: charter 水準への到達可否を示す。
3. 構造判定: 積み上げ可 / 差し戻しを示す。
4. 由来の帰属: 直前 fix 由来 / 既存在庫 / 新規 code に分類する。
5. 上流要件への批評: charter・使い方への指摘を示し、無ければ「なし」とする。
6. 概念診断: 欠けている・歪んでいる抽象を名指しし、無ければ「なし」とする。

## 出力言語規約

- 報告書 (`drafts/example-report.md`) は **日本語**で書く

## 報告書の書式

```markdown
# 報告書

REPORT_COMPLETE
```

- **報告書の最終行は `REPORT_COMPLETE` の 1 行で終える**

## 所要見積もり

- 見積もりバンド: **20〜30 分**
- 調査発動しきい値: **60 分** (見積もりの 2 倍)
"""

FIX_TAIL = """
## 前巡 verdict

前巡の判定を受けて class 是正する。

## 2 方向分析

受領側の分析と発注側の分析を並べる。

## 修正方式

- 所見 1: 既存集約 — 既存の funnel に寄せる。

## 掃引

同欠陥の全 site を `grep -rn x files/` で列挙し、単一 site である根拠を示した。
"""
PREVIOUS_SECTION = "## 前巡 verdict\n\n前巡の判定を受けて class 是正する。\n\n"
TWOWAY_SECTION = "## 2 方向分析\n\n受領側の分析と発注側の分析を並べる。\n\n"
METHOD_SECTION = "## 修正方式\n\n- 所見 1: 既存集約 — 既存の funnel に寄せる。\n\n"
SWEEP_SECTION = "## 掃引\n\n同欠陥の全 site を `grep -rn x files/` で列挙し、単一 site である根拠を示した。\n"
TREATMENT_SECTION = "\n## 処置の種別\n\n契約の訂正 — 契約側の文言を直す。\n"


def fix_order(number: int, treatment: str = TREATMENT_SECTION) -> str:
    """CONFORMING を fix 発注書に仕立てた、 契約上 clean な文書。"""
    head = swap(CONFORMING, "# 発注書: 例", f"# fix round {number}: 例")
    return head + FIX_TAIL + treatment


# from drafts/gates/send-gate-order.md @ e9f16141 (trim 31/129 行)
SEND_GATE = """\
# 発注: SendMessage 発信文の承認語 gate の新設
review-kind: none
## 目的 / 背景
## 2 方向分析 (発注側の分析 — 本発注の根拠)
## 実装方式
## 既存保証の監査
## 全数列挙 (受け入れ条件)
## 掃引
## スコープ
- 触らない: 他の全 file (`stop_checks.py`・`codex_delegation_gate.py`・`codex_order_lint`・
- commit しない (受け入れ後に発注側が行う)。kill-by-port (`fuser -k` / `pkill`) は禁止
## 成果物
- 報告書 `drafts/send-gate-report.md` — 書式例:
```
# 承認語 gate 報告
## 実装概要
## 掃引の表 (断定形 RE と非対象語の対応)
## 検証結果 (unittest 総数)
REPORT_COMPLETE
```
報告書の最終行は REPORT_COMPLETE の 1 行で終える。報告書を書いたら即座に終了する
## 実行してよい command
```
```
## 適用される既存裁定
1. gate は stateless — 自前の台帳・lock・state file を持たない
## 出力言語規約
## 作業量上限
## 所要見積もり
- 見積もりバンド: **20〜40 分** (sol high・warm)
- 調査発動しきい値: **80 分** (見積もり上限の 2 倍) — 超過したら再アームをやめ調査に切り替える
"""

# from drafts/ruling61/sentinel-r80-review-order.md @ a6949085 (trim 41/101 行)
R80_REVIEW = """\
# r80: 分類後一意性の適用後の確認巡 (全体 round・認定)
review-kind: adversarial
scope: artifact
scope-reason: r79 の是正 (pending 起動条件を分類後の一意性へ変更) の解消確認と、変更が開けた窓の全体確認
target: codex-task-sentinel
## 既製手段の棚卸し
(略)
## 目的
## 報告書の要件 (verdict 6 項目)
1. 指摘の振り分け — 各指摘を U0 (用途内で発生) / U1 (境界 — 決定不能は人間へ) /
2. 受入判定 — ship / needs-attention のどちらかを宣言する
3. 構造判定 — **指摘 1 件ごと**に「アーキテクチャの問題か / 構造の改善 (削除・代替・
4. 由来の帰属 — 各指摘が在庫か、r79 是正 diff 由来かを帰属する
5. 上流要件への批評 — charter・裁定・発注側の欠陥があれば指摘する
6. 概念診断 — 欠けている抽象・概念的一貫性の欠落を名指しする (無ければ「なし」と書く)
## 適用される既存裁定
1. 用途と環境前提の正本は `docs/sentinel-use-cases.md`。blocking は U0 のみ。用途を広げる
## スコープ
- 触らない: `files/`・`docs/`・deploy 先 (/etc, /usr/local) を含む全 file (review-only)。
- commit しない。kill-by-port (`fuser -k` / `pkill`) は禁止
## 実行してよい command
```
```
## 成果物
- 報告書 `drafts/sentinel-r80-report.md` — verdict 6 節 + 指摘一覧 (U 分類・severity・
```
# r80 報告
## 指摘の振り分け
## 受入判定
## 構造判定
## 由来の帰属
## 上流要件への批評
## 概念診断
REPORT_COMPLETE
```
- 報告書の最終行は REPORT_COMPLETE の 1 行で終える。報告書を書いたら即座に終了する
## 作業量上限
## 出力言語規約
## 所要見積もり
- 見積もりバンド: **25〜50 分** (sol xhigh)
- 調査発動しきい値: **100 分** (見積もり上限の 2 倍) — 超過したら再アームをやめ調査に切り替える
"""

# from drafts/gates/review-gates-fixes-12.md @ a5487e84 (trim 39/123 行)
FIXES_12 = """\
# fix round 12: 回帰 filter round 3 の低位 2 指摘の是正
review-kind: none
## 前巡 verdict
(略)
## 構造再審 (同段 3 巡目の verdict への回答)
## 2 方向分析 (受領側の分析 — 本発注の根拠)
(略)
## 修正方式
- 所見 1 (D) = 削除 — 到達不能の funnel 補強枝を削除する。warning 配達 matrix test は
## 全数列挙 (受け入れ条件)
(略)
## 依存閉包棚卸し
(略)
## 既存保証の監査 (機構追加ゼロの根拠)
## 掃引
(略)
## スコープ
- 触らない: `files/claude_managed-hooks/codex_delegation_gate.py`・`files/codex_order_lint`・
- commit しない (受け入れ後に発注側が行う)。kill-by-port (`fuser -k` / `pkill`) は禁止
## 成果物
- 報告書 `drafts/review-gates-fixes-12-report.md` — 書式例:
```
# fix round 12 報告
## 実装概要
## 掃引の表 (2 class の全列挙と処置)
## 検証結果 (selftest 総数の前後)
REPORT_COMPLETE
```
報告書の最終行は REPORT_COMPLETE の 1 行で終える。報告書を書いたら即座に終了する
## 実行してよい command
```
```
## 適用される既存裁定
1. 承認ファイル方式は廃止済み — 復活させない。直接起動一律 deny・stateless 設計を維持
## 出力言語規約
## 作業量上限
## 所要見積もり
- 見積もりバンド: **15〜30 分** (sol・warm)
- 調査発動しきい値: **60 分** (見積もり上限の 2 倍) — 超過したら再アームをやめ調査に切り替える
"""

# from drafts/ruling61/sentinel-r81-fixes.md @ 0a4256d7 (trim 42/140 行)
R81_FIXES = """\
# fix round 8: 縮小再入場 — r81 の 2 指摘の是正
review-kind: none
## 前巡 verdict
(略)
## 2 方向分析 (受領側の分析 — 本発注の根拠)
(略)
## 修正方式
- 所見 1 (R81-1) = 機構追加 — 裁定 55 の byte 上限条項の担保を復元する。`tree_age` の
  機構追加の列挙: 追加する観測 = worklist の live path byte 合計 (scalar 1 個)。追加する
  分岐 = 上限超過時の unknowable return 1 分岐。追加する資源 = なし (counter は int 1 個)。
  failure mode と test: (a) 加算漏れ / 減算漏れで counter が実保持とずれる → push/pop 対の
## 全数列挙 (受け入れ条件)
(略)
## 依存閉包棚卸し
(略)
## 既存保証の監査
(略)
## 掃引
(略)
## スコープ
- 触らない: `files/codex_task_sentinel.test.py` (実行のみ可)・`docs/`・他の `files/`・
- commit しない (受け入れ後に発注側が行う)。kill-by-port (`fuser -k` / `pkill`) は禁止
## 成果物
- 報告書 `drafts/sentinel-r81-fixes-report.md` — 書式例:
```
# fix round 8 報告
## 実装概要
## 掃引の表 (2 class の全列挙と処置)
## 検証結果 (selftest 総数の前後)
REPORT_COMPLETE
```
報告書の最終行は REPORT_COMPLETE の 1 行で終える。報告書を書いたら即座に終了する
## 実行してよい command
```
```
## 適用される既存裁定
1. 裁定 55: tree 走査は件数と保持 byte の両輪で囲う — cap は選り分けの前に消費し、超過は
## 出力言語規約
## 作業量上限
## 所要見積もり
- 見積もりバンド: **20〜40 分** (sol high・warm)
- 調査発動しきい値: **80 分** (見積もり上限の 2 倍) — 超過したら再アームをやめ調査に切り替える
"""

# from drafts/gates/review-gates-fixes-3.md @ d7ed5a44 (trim 34/109 行)
FIXES_3 = """\
# fix round 3: 既製判定器の 6 指摘の class 是正
review-kind: none
## 目的
## 修正方式
- 所見 3 (台帳の排他) = 機構追加 — 追加する観測 = target 単位 lock file の fd 1 個 (資源)。
  分岐 = lock 取得失敗 (競合検出) は許可せず deny / lock 置き場の作成失敗も deny。
  failure mode: 競合 → deny・保持中 crash → OS が fd 解放 (flock)・置き場不在 → 作成。各 1 test
## 掃引
(略)
## 所見の原文要約 (行番号は現 diff 時点)
## スコープ
- 触らない: `files/codex_task_sentinel`・`files/claude_managed-hooks/stop_checks.py`・
- commit しない (受け入れ後に発注側が行う)。kill-by-port (`fuser -k` / `pkill`) は禁止
## 成果物
- 報告書 `drafts/review-gates-fixes-3-report.md` — 書式例:
```
# fix round 3 報告
## 実装概要
## 掃引の表 (class ごとの全 site と処置)
## 検証結果
## 変異確認
REPORT_COMPLETE
```
報告書の最終行は REPORT_COMPLETE の 1 行で終える。報告書を書いたら即座に終了する
## 実行してよい command
```
```
## 適用される既存裁定
1. 決定的に判定できるものを LLM に委ねない — 判定は構造化 metadata の共通 parser へ集約する
## 出力言語規約
## 作業量上限
## 所要見積もり
- 見積もりバンド: **20〜40 分** (sol high・warm)
- 調査発動しきい値: **80 分** (見積もり上限の 2 倍) — 超過したら再アームをやめ調査に切り替える
"""

# from drafts/gates/review-gates-fixes.md @ 0707d51c (trim 12/57 行)
FIXES_1 = """\
# fix round 1: verdict 強制の組み込み (G4 再設計 + G5/G6 追加)
review-kind: none
## 修正方式
- 所見 1 (G4 再設計) = 構造変更 (counter → 台帳) + 機構追加。追加する観測と failure mode:
  `.verdict` drop の read/parse (不在 = deny・形式不正 = deny・処置語彙外 = deny、各 1 test) /
- 所見 2 (G5) = 既存 lint への検査追加のみ (機構追加なし)
## 所見
### 1. G4 を「counter」から「round ごとの verdict 台帳」へ再設計する
### 2. G5: 発注書 lint に「verdict 要求」の必須化を追加する
### 3. G6: fix 発注書の「修正方式」宣言を lint 必須化する
## スコープ・完了条件 (初回発注書と同じ規約)
- 報告書 = `drafts/review-gates-fixes-report.md`、最終行 `REPORT_COMPLETE`、報告後即終了
"""

# from drafts/codex-delegation-integration-fixes.md @ 53a74d81 (trim 10/58 行)
INTEGRATION = """\
# fix round 発注書: codex-delegation SKILL.md 受け入れレビュー所見
`/home/h2suzuki/terminal-configs/files/claude_managed-skills/codex-delegation/SKILL.md` 1 file のみ、commit はしない。
## 1. [blocker] 重複掲載の解消（これを最初にやる。以降の番号はこの整理後の姿に対して適用する）
## 2. [blocker] 3 分岐 rule が 2 条件 AND を迂回できる
## 3. [blocker] stall 判定に検証フェーズの carve-out が無い
## 4. [blocker] 長寿命 listener rule の第 2 分岐が欠落（前回発注書の記載漏れ。codex の逸脱ではない）
## 5. [nit] 一次情報との不一致・記法
## 6. [nit] 自己申告レポートの訂正
`drafts/codex-delegation-integration-report.md` の「Process 3 に教訓 3、4、6、7、8、9、10 を統合した」という記述のうち教訓 6 は Process 3 に存在しない（Rules にのみ存在）。今回の整理後の実態に合わせてレポートを更新すること。
## 完了条件
"""

CORPUS: tuple[tuple[str, str, list[str]], ...] = (
    ("send-gate-order.md", SEND_GATE, []),
    ("sentinel-r80-review-order.md", R80_REVIEW, []),
    ("review-gates-fixes-12.md", FIXES_12, [TREATMENT_MISSING]),
    ("sentinel-r81-fixes.md", R81_FIXES, [TREATMENT_MISSING]),
    ("review-gates-fixes-3.md", FIXES_3, [FIX_PREVIOUS, FIX_TWOWAY, TREATMENT_MISSING]),
    (
        "review-gates-fixes.md",
        FIXES_1,
        [
            *missing(*REQUIRED[1:]),
            NO_BAND,
            NO_RULING,
            NO_KILL,
            NO_COMMIT,
            NO_TOUCH,
            NO_FENCE,
            FIX_TWOWAY,
            FIX_METHOD,
            SWEEP,
        ],
    ),
    (
        "codex-delegation-integration-fixes.md",
        INTEGRATION,
        [
            KIND,
            *missing(*REQUIRED),
            NO_TOKEN,
            NO_BAND,
            NO_RULING,
            NO_KILL,
            NO_TOUCH,
            NO_FENCE,
        ],
    ),
)


class OrderLintTest(unittest.TestCase):
    def check(
        self, text: str, expected: list[str], siblings: dict[str, str] | None = None
    ) -> None:
        code, found = lint(text, siblings)
        self.assertEqual(found, expected)
        self.assertEqual(code, 1 if expected else 0)

    def test_c1_findings_stdout_and_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clean = seed(tmp, "clean.md", CONFORMING)
            broken = seed(tmp, "broken.md", drop(CONFORMING, "触らない"))
            out = run(clean)
            self.assertEqual((out.returncode, out.stdout), (0, ""))
            out = run(clean, broken)
            self.assertEqual(out.returncode, 1)
            self.assertEqual(
                out.stdout.splitlines(), [f"{broken}: {NO_TOUCH}", "1 件の規約違反"]
            )

    def test_c1_unreadable_inputs_exit_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            binary = os.path.join(tmp, "latin1.md")
            with open(binary, "wb") as handle:
                handle.write("# 発注書\n".encode("cp932"))
            for path in (tmp, "/dev/null", os.path.join(tmp, "absent.md"), binary):
                with self.subTest(path=path):
                    out = run(path)
                    self.assertEqual(out.returncode, 2, out.stdout)
                    self.assertEqual(len(out.stdout.splitlines()), 1)

    @unittest.skipIf(os.geteuid() == 0, "root は mode 000 の file も読めてしまう")
    def test_c1_unreadable_mode_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = seed(tmp, "locked.md", CONFORMING)
            os.chmod(path, 0o000)
            out = run(path)
        self.assertEqual(out.returncode, 2)
        self.assertEqual(len(out.stdout.splitlines()), 1)

    def test_c1_usage_errors_exit_2(self) -> None:
        for args in (
            (),
            ("--new", "fix"),
            ("--new", "fix", "a.md", "b.md"),
            ("--selftest",),
            ("--new", "unknown", "a.md"),
        ):
            with self.subTest(args=args):
                out = run(*args)
                self.assertEqual(out.returncode, 2, out.stdout)
                self.assertEqual(out.stdout, "")
                self.assertIn("usage:", out.stderr)

    def test_c2_fences_hide_declarations(self) -> None:
        self.check(
            swap(CONFORMING, "## 成果物", "## 納品物") + "```\n## 成果物\n```\n",
            missing("成果物"),
        )
        self.check(
            drop(CONFORMING, "review-kind:") + "```\nreview-kind: none\n```\n", [KIND]
        )
        self.check(CONFORMING + "```\n# fix round 5: 例\n```\n", [])
        self.check(
            swap(
                CONFORMING,
                "1. **裁定 A**: 説明\n2. **裁定 B**: 説明\n",
                "```\n1. **裁定 A**: 説明\n```\n",
            ),
            [NO_RULING],
        )

    def test_c2_fences_do_not_hide_slots_paths_and_estimates(self) -> None:
        text = CONFORMING + "```\n未記入\n```\n"
        line = text.splitlines().index("未記入") + 1
        self.check(text, [f"未記入 の slot が 1 件残っている: L{line}"])
        self.check(CONFORMING + "```\ndrafts/other-report.md\n```\n", [MIXED_REPORT])
        self.check(
            swap(
                CONFORMING,
                "- 見積もりバンド: **20〜30 分**",
                "```\n- 見積もりバンド: **20〜30 分**\n```",
            ),
            [],
        )

    def test_c3_slot_report(self) -> None:
        # slot の所見は先頭に出る。 骨組みの無い断片なので他の所見も一緒に返る。
        self.assertEqual(
            lint("未記入\n\n未記入\n")[1][0], "未記入 の slot が 2 件残っている: L1, L3"
        )
        body = "".join(f"{index}: 未記入\n" for index in range(1, 40))
        preview = ", ".join(f"L{index}" for index in range(1, 9))
        self.assertEqual(
            lint(body)[1][0], f"未記入 の slot が 39 件残っている: {preview} 他 31 行"
        )
        self.assertEqual(lint(CONFORMING)[1], [])

    def test_c4_review_kind_declaration(self) -> None:
        self.check(drop(CONFORMING, "review-kind:"), [KIND])
        self.check(CONFORMING + "review-kind: none\n", [KIND])
        # 値が閉じた 3 択の外なら、 以降の review 側 check は走らない。
        self.check(swap(CONFORMING, "review-kind: none", "review-kind: strict"), [KIND])

    def test_c4_review_side_checks(self) -> None:
        review = swap(CONFORMING, "review-kind: none", "review-kind: adversarial")
        self.check(review, [NO_INVENTORY, NO_SCOPE])
        stocked = review + "\n## 既製手段の棚卸し\n\n既製 X は Y のため使わない。\n"
        for kind, scope in (("adversarial", "diff"), ("acceptance", "artifact")):
            with self.subTest(kind=kind):
                self.check(
                    swap(
                        stocked,
                        "review-kind: adversarial\n",
                        f"review-kind: {kind}\nscope: {scope}\n",
                    ),
                    [],
                )

    def test_c5_required_sections(self) -> None:
        extra = {"実行してよい command": [NO_FENCE], "適用される既存裁定": [NO_RULING]}
        for name in REQUIRED:
            with self.subTest(section=name):
                self.check(
                    swap(CONFORMING, f"## {name}", f"## 旧{name}"),
                    [*missing(name), *extra.get(name, [])],
                )

    def test_c6_report_path(self) -> None:
        self.check(swap(CONFORMING, "example-report.md", "example-out.md"), [NO_REPORT])
        self.check(
            swap(
                CONFORMING,
                "`drafts/example-report.md`) は",
                "`drafts/other-report.md`) は",
            ),
            [MIXED_REPORT],
        )

    def test_c7_terminal_token(self) -> None:
        self.check(drop(CONFORMING, "最終行"), [NO_TOKEN])
        self.check(
            swap(
                CONFORMING,
                "- **報告書の最終行は `REPORT_COMPLETE` の 1 行で終える**\n",
                "```\n- **報告書の最終行は `REPORT_COMPLETE` の 1 行で終える**\n```\n",
            ),
            [NO_TOKEN],
        )
        self.check(
            swap(CONFORMING, "最終行は `REPORT_COMPLETE` の", "最終行は `done` の"),
            [NO_TOKEN],
        )

    def test_c8_estimate(self) -> None:
        self.check(drop(CONFORMING, "見積もりバンド"), [NO_BAND])
        self.check(drop(CONFORMING, "調査発動しきい値"), [NO_THRESHOLD])

    def test_c9_rulings(self) -> None:
        self.check(
            swap(
                CONFORMING, "1. **裁定 A**: 説明\n2. **裁定 B**: 説明\n", "(該当なし)\n"
            ),
            [NO_RULING],
        )

    def test_c10_prohibitions_and_command_fence(self) -> None:
        self.check(swap(CONFORMING, "`fuser -k` /", "`fuser -x` /"), [NO_KILL])
        self.check(
            swap(CONFORMING, "- commit もしない", "- 差分を残さない"), [NO_COMMIT]
        )
        self.check(
            swap(CONFORMING, "**触らない path**", "**読まない path**"), [NO_TOUCH]
        )
        self.check(
            swap(
                CONFORMING,
                "```\npython3 files/x --metadata drafts/example.md\n```\n",
                "- 使う command: `python3 files/x --metadata drafts/example.md`\n",
            ),
            [NO_FENCE],
        )

    def test_c11_fix_document_detection(self) -> None:
        self.check(CONFORMING, [])
        self.check(fix_order(2, ""), [])
        # 修正方式 だけでも fix 発注書として扱う。
        self.check(
            swap(fix_order(2, ""), "# fix round 2: 例", "# 発注書: 例"), [FIX_HEADER]
        )
        self.check(drop(fix_order(2, ""), "review-kind:"), [KIND, FIX_KIND])

    def test_c11_fix_required_parts(self) -> None:
        self.check(swap(fix_order(2, ""), PREVIOUS_SECTION, ""), [FIX_PREVIOUS])
        self.check(swap(fix_order(1, ""), PREVIOUS_SECTION, ""), [])
        self.check(swap(fix_order(2, ""), TWOWAY_SECTION, ""), [FIX_TWOWAY])
        self.check(swap(fix_order(2, ""), METHOD_SECTION, ""), [FIX_METHOD_SECTION])
        self.check(
            swap(fix_order(2, ""), "所見 1: 既存集約 —", "所見 1: 様子を見る —"),
            [FIX_METHOD],
        )
        self.check(swap(fix_order(2, ""), SWEEP_SECTION, ""), [SWEEP])

    def test_c11_inventory_sections_are_not_required(self) -> None:
        text = fix_order(2, "")
        self.assertNotIn("全数列挙", text)
        self.assertNotIn("依存閉包棚卸し", text)
        self.check(text, [])
        # 機構追加 を名乗っても、 追加の節も語の列挙も要求しない。
        self.check(swap(text, "所見 1: 既存集約 —", "所見 1: 機構追加 —"), [])

    def test_c12_treatment_required_from_round_3(self) -> None:
        for number in (1, 2):
            with self.subTest(round=number):
                self.check(fix_order(number, ""), [])
        for number in (3, 4, 12):
            with self.subTest(round=number):
                self.check(fix_order(number, ""), [TREATMENT_MISSING])
                self.check(
                    fix_order(number, "\n## 処置の種別\n\n"), [TREATMENT_MISSING]
                )
                self.check(fix_order(number), [])

    def test_c12_treatment_names_exactly_one_option(self) -> None:
        for option in TREATMENTS:
            with self.subTest(option=option):
                self.check(fix_order(3, f"\n## 処置の種別\n\n{option} を選ぶ。\n"), [])
        self.check(
            fix_order(3, "\n## 処置の種別\n\n様子を見る。\n"), [TREATMENT_CHOICE]
        )
        self.check(
            fix_order(3, "\n## 処置の種別\n\n廃棄 と 構造化 の両方を行う。\n"),
            [TREATMENT_CHOICE],
        )

    def test_c12_real_fix_order_gains_only_the_treatment_finding(self) -> None:
        self.assertNotIn("## 処置の種別", R81_FIXES)
        self.check(R81_FIXES, [TREATMENT_MISSING])

    def test_c13_duplicate_rounds_only(self) -> None:
        duplicate = {"other.md": "# fix round 3: 別\n"}
        self.check(fix_order(3), ["fix round が重複している: 3"], duplicate)
        self.check(fix_order(5), [])  # 1..4 が欠番でも所見にしない
        self.check(fix_order(2, ""), [], {"later.md": "# fix round 7: 別\n"})
        self.check(fix_order(3), [], {"fenced.md": "```\n# fix round 3: 別\n```\n"})
        self.check(fix_order(3), [], {"note.txt": "# fix round 3: 別\n"})

    def test_c14_metadata_shape(self) -> None:
        code, record = meta(fix_order(3))
        self.assertEqual(code, 0)
        self.assertEqual(
            record,
            {
                "order_document": True,
                "review_kind": "none",
                "round": 3,
                "scope": None,
                "methods": [{"finding": 1, "methods": ["既存集約"]}],
                "has_previous_verdict": True,
                "report_path": "drafts/example-report.md",
                "findings": [],
            },
        )
        note = "# 覚書\n\n本文だけの文書。\n"
        code, record = meta(note)
        self.assertEqual(code, 1)
        self.assertFalse(record["order_document"])
        self.assertEqual(record["findings"], lint(note)[1])
        proc, path = invoke(CONFORMING, ("--metadata",), None)
        self.assertNotIn(f"{path}: ", proc.stdout)
        self.assertEqual(len(proc.stdout.splitlines()), 1)

    def test_c14_metadata_ambiguous_values_are_null(self) -> None:
        text = (
            fix_order(3)
            + "\nreview-kind: none\n# fix round 4: 例\ndrafts/x-report.md\n"
        )
        record = meta(text)[1]
        for key in ("review_kind", "round", "report_path"):
            with self.subTest(key=key):
                self.assertIsNone(record[key])
        review = swap(
            CONFORMING, "review-kind: none\n", "review-kind: adversarial\nscope: diff\n"
        )
        self.assertEqual(meta(review)[1]["scope"], "diff")

    def test_c15_new_seeds_the_stem(self) -> None:
        for kind, template in (
            ("plain", "template-order.md"),
            ("review", "template-review-order.md"),
        ):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "sample-order.md")
                out = run("--new", kind, path)
                self.assertEqual(out.returncode, 0, out.stderr)
                self.assertEqual(out.stdout.strip(), f"{path}: {template} から作成した")
                text = read(path)
                self.assertIn(os.path.join(tmp, "sample-order-report.md"), text)
                self.assertIn(os.path.join(tmp, "sample-order-probe.txt"), text)
                self.assertIn("# sample-order 報告書", text)
                self.assertIn(": sample-order\n", text)
                self.assertIn("未記入", text)

    def test_c15_new_fix_numbers_the_round(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first, second = os.path.join(tmp, "a.md"), os.path.join(tmp, "b.md")
            self.assertEqual(run("--new", "fix", first).returncode, 0)
            self.assertEqual(run("--new", "fix", second).returncode, 0)
            head, tail = read(first), read(second)
        self.assertIn("# fix round 1: a", head)
        self.assertNotIn("前巡 verdict", head)
        self.assertIn("# fix round 2: b", tail)
        self.assertIn("## 前巡 verdict", tail)

    def test_c15_new_refuses_to_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = seed(tmp, "taken.md", "既存の本文\n")
            self.assertEqual(run("--new", "plain", path).returncode, 3)
            self.assertEqual(read(path), "既存の本文\n")

    def test_c16_retired_findings_never_return(self) -> None:
        review = swap(
            CONFORMING,
            "review-kind: none\n",
            "review-kind: adversarial\nscope: artifact\n",
        )
        review = (
            drop(review, "指摘の振り分け")
            + "\n## 既製手段の棚卸し\n\n既製 X は使わない。\n"
        )
        provocations = {
            "none と本文": CONFORMING + "\n敵対レビュー は行わない。\n",
            "scope-reason / target / verdict 要件": review,
            "裁定の採番": swap(CONFORMING, "2. **裁定 B**", "3. **裁定 B**"),
            "2 倍でない": swap(
                CONFORMING,
                "- 調査発動しきい値: **60 分**",
                "- 調査発動しきい値: **50 分**",
            ),
            "終端 token の書式例": swap(
                CONFORMING, "# 報告書\n\nREPORT_COMPLETE\n", "# 報告書\n\n本文\n"
            ),
            "機構追加には": swap(
                fix_order(2, ""), "所見 1: 既存集約 —", "所見 1: 機構追加 —"
            ),
            "が欠番": fix_order(5),
        }
        for name, text in provocations.items():
            with self.subTest(provocation=name):
                self.check(text, [])
        self.check(fix_order(2, ""), [], {"later.md": "# fix round 9: 別\n"})
        for name, text, _ in CORPUS:
            with self.subTest(corpus=name):
                self.assertEqual([f for f in lint(text)[1] if retired(f)], [])

    def test_c17_corpus_replay(self) -> None:
        for name, text, expected in CORPUS:
            with self.subTest(corpus=name):
                self.check(text, expected)
        clean = [name for name, _, expected in CORPUS if not expected]
        self.assertEqual(clean, ["send-gate-order.md", "sentinel-r80-review-order.md"])

    # -- independent review corrections (P0-1, P0-2, P1-1, P1-2, P1-3) ---------------------------
    def test_c11_method_heading_may_carry_a_note(self) -> None:
        noted = swap(fix_order(2, ""), "## 修正方式\n", "## 修正方式 (所見 1 件)\n")
        self.check(noted, [])
        self.check(swap(noted, "# fix round 2: 例", "# 発注書: 例"), [FIX_HEADER])

    def test_c5_subheadings_belong_to_the_section_body(self) -> None:
        self.check(
            swap(
                CONFORMING,
                "## 適用される既存裁定 (これに反する指摘は不成立)\n",
                "## 適用される既存裁定 (これに反する指摘は不成立)\n\n### 委譲裁定\n",
            ),
            [],
        )
        self.check(
            swap(
                CONFORMING,
                "## 実行してよい command\n",
                "## 実行してよい command\n\n### 読み取り系\n",
            ),
            [],
        )
        text = fix_order(3)
        for heading, sub in (
            ("## 前巡 verdict\n", "### verdict 本文\n"),
            ("## 2 方向分析\n", "### 方向 1\n"),
            ("## 掃引\n", "### 欠陥 class A\n"),
            ("## 処置の種別\n", "### 判断\n"),
        ):
            self.check(swap(text, heading, f"{heading}\n{sub}"), [])

    def test_c2_fences_hide_prohibitions(self) -> None:
        text = swap(CONFORMING, "`fuser -k` /", "`fuser -x` /")
        text = swap(text, "- commit もしない", "- 差分を残さない")
        text = swap(text, "**触らない path**", "**読まない path**")
        quoted = (
            text
            + "\n## 前巡の発注書 (引用)\n\n```\n**触らない path** は上記以外の全て。 "
            "commit もしない。 `fuser -k` / `pkill` は禁止。\n```\n"
        )
        self.check(quoted, [NO_KILL, NO_COMMIT, NO_TOUCH])

    def test_c15_new_reports_an_unwritable_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "missing", "x.md")
            out = run("--new", "plain", path)
        self.assertEqual(out.returncode, 2, out.stderr)
        self.assertTrue(out.stdout.startswith(f"{path}: "), out.stdout)
        self.assertEqual(out.stderr, "")

    def test_c15_new_fix_seeds_the_treatment_from_round_3(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = [os.path.join(tmp, name) for name in ("a.md", "b.md", "c.md")]
            for path in paths:
                self.assertEqual(run("--new", "fix", path).returncode, 0)
            texts = [read(path) for path in paths]
            third = run(paths[2])
        self.assertNotIn("## 処置の種別", texts[0])
        self.assertNotIn("## 処置の種別", texts[1])
        self.assertIn("## 処置の種別", texts[2])
        self.assertNotIn("必須の節がない: ## 処置の種別", third.stdout)


if __name__ == "__main__":
    unittest.main()
