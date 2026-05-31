# プロジェクト横断 preference

## Commit 自律則

commit 実行・保留・タイミング・粒度は LLM 自律で判断する。
ユーザーに commit 可否を毎回聞かない。なぜなら cheap & reversible — `git reset` / `revert` / `restore` で巻き戻せるから。

詳細・例外は `commit-discipline` skill 参照。

## user の名称

Session の対話相手のことは、H.S. と呼称する。user と呼ばない。
