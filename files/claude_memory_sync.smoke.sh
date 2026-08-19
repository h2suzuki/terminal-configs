#!/bin/bash
# Smoke test for claude_memory_sync against a local file:// fixture.
# shellcheck disable=SC2016,SC2034,SC2317  # check() eval-expands single-quoted asserts; vars/fn used inside them
set -u
S="${TMPDIR:-/tmp}/claude_memory_sync-smoke"
CLI="$(dirname "$(readlink -f "$0")")/claude_memory_sync"
rm -rf "$S" && mkdir -p "$S"

pass=0; fail=0
ok()   { echo "PASS: $1"; pass=$((pass+1)); }
bad()  { echo "FAIL: $1"; fail=$((fail+1)); }
check(){ if eval "$2"; then ok "$1"; else bad "$1"; fi; }

git init --quiet --bare "$S/remote.git"
git clone --quiet "$S/remote.git" "$S/clone" 2>/dev/null
git -C "$S/clone" config user.name smoke
git -C "$S/clone" config user.email smoke@example.invalid

cat > "$S/surface.py" <<'EOF'
#!/usr/bin/env python3
import os, sys
with open(os.path.join(os.path.dirname(__file__), "calls.log"), "a") as f:
    f.write("\t".join(sys.argv[1:]) + "\n")
EOF

export CLAUDE_MEMORY_REPO="$S/clone" CLAUDE_MEMORY_SURFACE="$S/surface.py"
calls() { cat "$S/calls.log" 2>/dev/null; }

# 1. status on unborn clone
out=$("$CLI" --status 2>&1)
check "status: unborn clone reports ok+unborn" '[[ "$out" == *"state: ok"* && "$out" == *"unborn"* ]]'

# 2. first entry commit on unborn HEAD + bg push creates remote branch
mkdir -p "$S/clone/user/alice"
printf 'reminder: r\nkeywords: k\nmodels: fable-5\n\nbody\n' > "$S/clone/user/alice/feedback_t.md"
"$CLI" --commit "$S/clone/user/alice/feedback_t.md" >/dev/null 2>&1
rc=$?
sleep 2
check "commit: exits 0 on unborn HEAD" '[[ $rc -eq 0 ]]'
check "commit: upsert called with user scope" 'calls | grep -q "^--upsert	$S/clone/user/alice/feedback_t.md	user-alice$"'
branch=$(git -C "$S/clone" branch --show-current)
check "commit: bg push reached remote branch" '[[ -n "$(git -C "$S/remote.git" rev-parse --quiet --verify "refs/heads/$branch")" ]]'
check "commit: fix_perms opened entry file (666)" '[[ "$(stat -c %a "$S/clone/user/alice/feedback_t.md")" == 666 ]]'
check "commit: fix_perms opened scope dir (777)" '[[ "$(stat -c %a "$S/clone/user/alice")" == 777 ]]'
check "commit: fix_perms keeps clone top at 755" '[[ "$(stat -c %a "$S/clone")" == 755 ]]'

# 3. pull applies A/M/D from a second clone
git clone --quiet "$S/remote.git" "$S/b" 2>/dev/null
git -C "$S/b" config user.name smoke; git -C "$S/b" config user.email smoke@example.invalid
mkdir -p "$S/b/project/-proj-x" "$S/b/org"
printf 'reminder: p\nkeywords: k\n\nbody\n' > "$S/b/project/-proj-x/feedback_p.md"
printf 'reminder: o\nkeywords: k\n\nbody\n' > "$S/b/org/feedback_org.md"
printf 'reminder: r2\nkeywords: k\n\nbody\n' >> "$S/b/user/alice/feedback_t.md"
printf 'not-an-entry\n' > "$S/b/user/alice/README.md"
git -C "$S/b" add -A && git -C "$S/b" commit --quiet -m seed && git -C "$S/b" push --quiet
: > "$S/calls.log"
"$CLI" --pull >/dev/null 2>&1
check "pull: modified user entry upserted" 'calls | grep -q "^--upsert	$S/clone/user/alice/feedback_t.md	user-alice$"'
check "pull: new project entry upserted with enc scope" 'calls | grep -q "^--upsert	$S/clone/project/-proj-x/feedback_p.md	-proj-x$"'
check "pull: org entry upserted with NULL scope (no 3rd arg)" 'calls | grep -q "^--upsert	$S/clone/org/feedback_org.md$"'
check "pull: README ignored" '! calls | grep -q README'
check "pull: fix_perms opened pulled entry (666)" '[[ "$(stat -c %a "$S/clone/project/-proj-x/feedback_p.md")" == 666 ]]'

# 4. rename handled as delete+upsert
git -C "$S/b" mv project/-proj-x/feedback_p.md project/-proj-x/feedback_q.md
git -C "$S/b" commit --quiet -m rename && git -C "$S/b" push --quiet
: > "$S/calls.log"
"$CLI" --pull >/dev/null 2>&1
check "pull: rename deletes old path" 'calls | grep -q "^--delete	$S/clone/project/-proj-x/feedback_p.md	-proj-x$"'
check "pull: rename upserts new path" 'calls | grep -q "^--upsert	$S/clone/project/-proj-x/feedback_q.md	-proj-x$"'

# 5. deletion on remote propagates to index
git -C "$S/b" rm --quiet org/feedback_org.md && git -C "$S/b" commit --quiet -m del && git -C "$S/b" push --quiet
: > "$S/calls.log"
"$CLI" --pull >/dev/null 2>&1
check "pull: remote deletion -> --delete NULL scope" 'calls | grep -q "^--delete	$S/clone/org/feedback_org.md$"'

# 6. retire: file removed, committed, index delete, pushed
: > "$S/calls.log"
"$CLI" --retire "$S/clone/user/alice/feedback_t.md" >/dev/null 2>&1
rc=$?
sleep 2
check "retire: exits 0" '[[ $rc -eq 0 ]]'
check "retire: file removed from clone" '[[ ! -e "$S/clone/user/alice/feedback_t.md" ]]'
check "retire: index --delete called" 'calls | grep -q "^--delete	$S/clone/user/alice/feedback_t.md	user-alice$"'
git -C "$S/b" pull --quiet 2>/dev/null
check "retire: deletion pushed to remote" '[[ ! -e "$S/b/user/alice/feedback_t.md" ]]'

# 7. pull failure is fail-open; push failure sets stamp
git -C "$S/clone" remote set-url origin "$S/nonexistent.git"
"$CLI" --pull >/dev/null 2>&1
check "pull: bad remote still exits 0 (fail-open)" '[[ $? -eq 0 ]]'
printf 'reminder: z\nkeywords: k\n\nbody\n' > "$S/clone/user/alice/feedback_z.md"
"$CLI" --commit "$S/clone/user/alice/feedback_z.md" >/dev/null 2>&1
sleep 2
check "push failure: stamp created" '[[ -e "$S/clone.push-failed" ]]'
out=$("$CLI" --status 2>&1)
check "status: reports commits to push + push failing" '[[ "$out" == *"to push"* && "$out" == *"push failing since"* ]]'

# 8. missing clone: fail-open pull, hard-fail full
export CLAUDE_MEMORY_REPO="$S/absent"
"$CLI" --pull  >/dev/null 2>&1; check "missing clone: pull exits 0" '[[ $? -eq 0 ]]'
"$CLI" --full  >/dev/null 2>&1; check "missing clone: full exits 1" '[[ $? -eq 1 ]]'
"$CLI" --status >/dev/null 2>&1; check "missing clone: status exits 1" '[[ $? -eq 1 ]]'

echo "----------------------------------------"
echo "smoke: $pass passed, $fail failed"
exit $((fail > 0))
