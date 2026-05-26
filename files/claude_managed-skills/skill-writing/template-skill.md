---
# === frontmatter (公式 spec: https://code.claude.com/docs/en/skills) ===
# 必須: name のみ。 他は全 optional。
name: skill-name-in-kebab-case
# 1 文の英語、 文末 `.`。 何をする skill か。
# trigger keyword を含まない abstract な役割説明。
description: One-line English summary of what this skill does.
# TRIGGER + SKIP の paired clause。 英語、 trigger keyword だけ quoted 日本語 OK。
# `。` / `「」` を英文に混ぜない。
when_to_use: TRIGGER when about to do X / when noticing Y / when "specific phrase" is about to be uttered. SKIP for Z / when condition W holds.

# === optional fields (必要時のみ) ===
# argument-hint: <arg1> <arg2>          # /skill-name <arg1> <arg2> の入力 hint
# arguments: arg1 arg2                  # CLI arg 名 ($ARGUMENTS / $1 substitution 用)
# disable-model-invocation: true        # 手動 invoke only (/<name>)、 model auto-trigger 無効
# user-invocable: false                 # model auto-trigger only、 / menu に出ない
# allowed-tools: Read, Bash             # この skill 内で使える tool を絞る
# model: opus                           # 特定 model で実行
# effort: low                           # token budget hint
# context: fork                         # subagent (fork) で実行
# agent: general-purpose                # fork 時の agent type
# hooks: ...                            # skill 専用 hook
# paths: "**/*.py, **/*.ts"             # path-based gating (omit で LLM judgment ベース)
# shell: bash                           # `bash` | `powershell`
---

# Skill Title (英語、 sentence-case 推奨)

skill の意図を 1-2 文で。 何のための skill か (Why) / どう振る舞うか (What) を簡潔に。
body は **日本語可**。 ## headers は **英語推奨** (Process / Rules / Output / Related の 4 つを優先採用、 内容に合わない場合のみ他英語名)。

## Process

1. 手順 1
2. 手順 2
3. 手順 3

## Rules

- rule 1: 説明 + Why
- rule 2: 説明 + Why

## Output

skill 実行後の出力 / 振る舞いの形式 (該当する場合)。

## Related

- `sibling-skill-1` — 隣接 scope の skill
- `code-writing` — 永続ファイル汎用 rule (例: 「No dangling-prone references in persistent files」)

<!--
=== Writing Convention Cheatsheet ===

(永続ファイルから dangling-prone reference [端末固有 path / skill dir 外 file への file path citation / ephemeral tag 等] を入れない — `code-writing` Rules「No dangling-prone references in persistent files」 参照)

frontmatter:
  - description: 1 文英語、 文末 `.`、 quote `"..."`
  - when_to_use: TRIGGER + SKIP pair。 英語接続詞のみ。 trigger keyword は quoted 日本語 OK
  - 「等の評価語」 等の Japanese 接続詞を英文中に混ぜない

body:
  - ## headers: 英語 (Process / Rules / Output / Related 優先)
  - ### sub-headers: 英語 (日本語の概念名を扱う場合は subject だけ日本語: `### Defining 「具体的」`)
  - 段落 / bullet: 日本語可、 日本語 context では `「」` quote OK

Bad / Good 例:
  - 良い frontmatter: `Rules for X (categories in English).`
  - 悪い frontmatter (中途半端な日英 mix): `Rules for X (categories 日本語).`
  - 良い trigger: `TRIGGER when about to use evaluative terms like "大改造" / "軽微"`
  - 悪い trigger: `TRIGGER when about to use 「大改造」「軽微」 等の評価語`

description tighten 時:
  - frontmatter description を short にしたら、 削った詳細を body に必ず明文化
-->
