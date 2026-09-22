# agent-coord hook policy

Agent-coord uses hooks to surface unread messages while a session is active
and to give a session one chance to handle unread messages before it stops.
The inbox remains the source of truth when a reminder is missed or ignored.

## Contents

1. [Scope and invariants](#scope-and-invariants)
2. [Notification lifecycle](#notification-lifecycle)
3. [Stop continuation rule](#stop-continuation-rule)
4. [Hook contracts](#hook-contracts)
   - [Codex](#codex)
   - [Claude Code](#claude-code)
   - [Antigravity](#antigravity)
5. [No-op and failure outcomes](#no-op-and-failure-outcomes)
6. [Official sources](#official-sources)

## Scope and invariants

- The per-recipient inbox is the source of truth. A wake or injected reminder
  only calls attention to unread events; neither marks an event as handled.
  Acknowledgement advances the recipient's cursor.
- Deliver notifications while a session can still act: inject context at a
  model-input or completed-tool boundary, and use the client's wake channel
  when an idle session has no such boundary. Checks at these boundaries must
  return promptly and must not use a blocking decision to await a message.
- A hook with no actionable unread events must not stop a prompt, tool, or
  turn. Agent-coord does not register `PreToolUse` and does not gate edits.
- A `Stop` continuation asks the agent to `catchup`, handle relevant events,
  and `ack`. It is never a substitute for an inbox delivery and never grants
  authority beyond the user's instructions.

## Notification lifecycle

1. A committed event creates a delivery in each recipient's inbox. `wake_rows`
   selects only actionable unread deliveries: it excludes a recipient that has
   left, self-sent events, historical backfill, and an open request whose sender
   has left. A departed peer's final message can still wake the recipient; its
   reminder says that no reply to that peer is needed.
2. During an active turn, `UserPromptSubmit`, `PostToolUse`, or Antigravity
   `PreInvocation` adds an unread reminder at the next available boundary.
   Codex `SessionStart` also restores unread context after compaction. A
   reminder includes the sequence range and tells the agent to `catchup` and
   `ack`; it does not copy the full message into the hook result.
3. For an idle Codex session, the daemon submits one signed reminder through
   `codex queue --thread ... --message ...`. The queue is a wake channel, not a
   second inbox. A queued reminder occupies one slot until its prompt reaches
   `UserPromptSubmit`; newer unread events can be surfaced by that same prompt.
   An active Codex turn is not queued behind itself. Claude Code receives a
   wake through its session inbox socket. Antigravity has no push wake here and
   reads at its registered hooks.
4. The recipient reads the actual events with `catchup`, acts within its own
   permissions, then acknowledges the last handled sequence. `pending` and
   `pushed` describe notification attempts, not completed work. Unacknowledged
   events remain readable even after a reminder was surfaced.

## Stop continuation rule

Agent-coord may request a continuation only from a registered `Stop` hook and
only when `wake_rows` contains actionable unread events. The request is one
chance to process those events before ending the turn:

1. If the inbox has no actionable unread rows, or the host reports
   `stop_hook_active`, allow the stop.
2. Otherwise, if any outstanding row belongs to a range already continued by
   this session, allow the stop. This also prevents a later arrival from
   repeatedly continuing a turn while the earlier row is still unacknowledged.
3. Otherwise, persist `stop_blocked_through` at the last selected sequence and
   return the host's continuation response with a `catchup`/`ack` instruction.
   Once the old range is acknowledged, a genuinely new unread range can receive
   its own single continuation.

For Codex and Claude Code, the `Stop` continuation response is
`{"decision":"block","reason":"..."}`. At `Stop`, this means **continue the
turn**.[1][2] For Antigravity, the response is
`{"decision":"continue","reason":"..."}`.[3] Agent-coord never returns a
block decision from a prompt or completed-tool hook.

Claude Code ends the turn after eight consecutive `Stop` blocks.[2] The Codex
hooks reference does not specify a numeric `Stop` limit.[1] Antigravity's
changelog describes a configurable limit for consecutive continuations; its
hook reference does not give a number.[3][4] Agent-coord's one-continuation
rule is its own policy and does not rely on a host limit.

## Hook contracts

The "Host contract" column states the official host behavior, with its source
number. The "agent-coord behavior" column states this plugin's policy. Only
the listed events are registered by agent-coord.

### Codex

For ordinary Codex hooks, use the payload's `session_id` as the current thread.
For `SubagentStart` and `SubagentStop`, `session_id` names the parent and
`agent_id` names the child.[1] Agent-coord uses these payload IDs for hook
identity, not `CODEX_THREAD_ID`. A hook without a payload ID exits without a
blocking decision.

| Event | Host contract | agent-coord behavior |
|---|---|---|
| `SessionStart` | Adds startup context; also runs after compaction.[1] | Join or restore the session; on compaction, surface unread context without ending the active turn. Never block. |
| `SubagentStart` | Adds context to a starting subagent.[1] | Join the child session and record its parent. Never block. |
| `UserPromptSubmit` | `decision: "block"` rejects the prompt; `additionalContext` adds developer context.[1] | Mark the turn active, admit a queued wake if present, and add context for new unread. A stale wake or empty inbox does not reject the prompt. |
| `PostToolUse` | Adds context after a completed tool; can also block tool-result processing.[1] | Surface new unread during the active turn. Never block the tool result. |
| `Stop` | `decision: "block"` creates a continuation prompt for the same turn.[1] | Apply the one-continuation rule. Otherwise return `{"continue":true}` and mark the turn idle. |
| `Interrupt` | Runs for a user-interrupted main turn; cannot cancel the interruption or restart the turn.[1] | Clear that turn's active marker so later delivery can proceed. Do not immediately queue its old unread or block. |
| `SessionEnd` | Runs when the main session ends; its output cannot keep the thread open.[1] | Mark the session done and leave the ledger. Do not start an offline daemon or block. |
| `SubagentStop` | Can continue a child agent by returning `decision: "block"`.[1] | Leave the child session and return `{"continue":true}`; never continue it for notification alone. |

### Claude Code

| Event | Host contract | agent-coord behavior |
|---|---|---|
| `SessionStart` | Adds context when a session starts.[2] | Join and report peers/unread count. Never block. |
| `UserPromptSubmit` | `decision: "block"` discards the prompt; `additionalContext` adds context without rejecting it.[2] | Add a reminder for new unread; do not reject the user's prompt. |
| `PostToolUse` | Adds feedback or context after a tool completes.[2] | Surface new unread; never block the tool result. |
| `Stop` | `decision: "block"` prevents stopping and gives Claude a reason to continue.[2] | Apply the one-continuation rule. Otherwise exit successfully without a decision. |
| `SessionEnd` | Cannot prevent session termination. Its default timeout is 1.5 seconds; a plugin-provided hook timeout does not raise the overall budget.[2] | Leave the ledger without starting an offline daemon. Use the default timeout. |

### Antigravity

| Event | Host contract | agent-coord behavior |
|---|---|---|
| `PreInvocation` | `injectSteps` can add an ephemeral message before a model call.[3] | Join or attach the session and inject a reminder for new unread. Never block. |
| `Stop` | `decision: "continue"` re-enters the execution loop; other values allow the stop.[3] | Apply the one-continuation rule; otherwise return `{"decision":"stop"}`. |

## No-op and failure outcomes

| Situation | Required agent-coord result |
|---|---|
| No actionable unread at a hook boundary | Emit no reminder. Allow the current prompt, tool result, or stop. |
| Signed Codex queue prompt is stale, duplicated, or has no unread left | Admit the prompt without a hook block; emit no unread context. The already-queued prompt may still start an empty turn. |
| A queued Codex reminder is still waiting | Do not queue another reminder for that session; its admission can carry newer unread. |
| A `Stop` continuation did not lead to an `ack` | Do not block again for the same outstanding range. Keep the inbox intact for `catchup` or later context injection. |
| Hook identity is missing or the ledger connection fails | The hook exits successfully without a blocking decision. The failure does not acknowledge the inbox. |
| A push wake channel is unavailable | Leave unread deliveries intact for the next hook boundary or `catchup`; a failed push must not create a blocking hook response. |
| `SessionEnd` or `Interrupt` finds no daemon | Do not start one solely for cleanup. Do not block the host lifecycle event. |

## Official sources

1. OpenAI, *Codex Hooks*, <https://learn.chatgpt.com/docs/hooks>.
   UserPromptSubmit: “To block the prompt, return”; Stop: “automatically
   creates a new continuation prompt”; Interrupt: “Hook output can’t prevent
   the interruption”.
2. Anthropic, *Claude Code Hooks reference*,
   <https://code.claude.com/docs/en/hooks>. UserPromptSubmit: “prevents the
   prompt from being processed and erases it from context”; Stop: “after 8
   consecutive blocks”; SessionEnd: “default timeout of 1.5 seconds”.
3. Google, *Antigravity Hooks*, <https://antigravity.google/docs/hooks>.
   Stop: “Set to \"continue\" to prevent the agent from stopping and re-enter
   the execution loop”.
4. Google, *Antigravity Changelog*, <https://antigravity.google/changelog>.
   Stop-hook fix: “after a configurable number of consecutive continuations”.
