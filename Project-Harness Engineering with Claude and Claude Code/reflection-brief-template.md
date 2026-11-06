# Reflection Brief — Harness Engineering Capstone

**Name:** Marta Soares
**Date:** 06/11/2026

Replace each `→` with your answer. **Every answer cites at least one artifact from your own runs** — a run ID, file path, token count, claim outcome, or test count. Uncited answers do not pass. 3–6 sentences each unless noted. Paste short artifact snippets where they help.

**Environment**

- Model(s): claude-haiku-4-5-20251001, claude-sonnet-4-5-20250929, claude-opus-4-5-20251101
- OS / Python: 3.14.4
- Approx. API spend: $0.091

---

## Part 1 — Per-system

### System 1 — Agentic loop

1. **Loop control.** Quote the `stop_reason` sequence from one trace. Name the file and function that decides continue-vs-stop, and how.

On "system-1\runs\20261106_150040\traces\claim_05_auto_collision.jsonl", the first turn the "stop-reason" is "tool use", the second turn is "tool use" and the final third turn is "end turn".  Therefore, the sequence is  tool_use → tool_use → end_turn.

The function that decides the continue-vs-stop function is the run() function in "system-1\claims_intake\loop.py". This funtion branches based on the value of response.stop_reason. If response.stop_reason is "tool_use", the system appends the assistant message, runs each tool_use block through tool_executer, appends tool_result user message and calls continue to loop again. If the response.stop_reason is "end_turn", the systems return a FinalState which stops the loop. For any other values, the system raises an UnexpectedStopReason , so a  max_tokens  stop fails loudly instead of being treated as done.

2. **Anti-pattern.** Name one anti-pattern `test_antipatterns.py` checks for. What would break in your run if the loop used it?

The test test_no_integer_literal_iteration_cap_in_loop in "system 1\tests\test_antipatterns.py" checks that "system-1\claims_intake\loop.py" has for _ in range(<int literal>) and not while x < <int literal> as the stopping mechanism. It does this by walking the AST.

If the loop used it, the run would break because with something like range(2), the loop would have stopped after turn 2. The claim would have been classified and routed, but it would never have reached the end_turn turn that returns FinalState. The loop would end by falling off the cap, not by stop_reason.

3. **Tool design.** Pick two tools with overlapping inputs. How do the descriptions prevent misrouting? What did a structured tool error let the agent do that a generic string would not?

Two tools with overlapping inputs are route_to_adjuster  and  escalate_to_human , both in "system-1\claims_intake\tools.py". Both are terminal tools. Both take claim-type and summary-style inputs, and both end the claim.

The descriptions prevent misrouting because each description has an explicit trigger condition.
•  route_to_adjuster  is for "classification confidence is at least 0.6 and severity has been assessed".
•  escalate_to_human  is for "confidence is below 0.6 even after clarification", or when the claim can't be routed safely: multiple plausible types, missing facts, or policy disputes.
The  classify_claim  description backs this up: "If confidence is below 0.6, prefer escalate_to_human".
Both are labeled TERMINAL, say "Call this exactly once", and say the next response should be a brief confirmation ending in end_turn. That keeps the model from calling both.
The input schemas differ too.
•  route_to_adjuster  needs a  queue  enum and a short  claim_summary .
•  escalate_to_human  needs a  reason  and a full  structured_summary  with six required fields.
• A model that can't fill in those fields is pushed toward the other tool.
In the run, claim_05 (confidence 1.0) was routed. The low-confidence claim_06 was escalated.

4. **Your numbers.** Quote the turn count and cost for one claim. How does it differ from the README sample, and why?

As per the "system-1\runs\20261106_150040\screenshot1", the claim claim_04_neighbor_injury had two turns and the cost estimation was $0.0084. 

The cost was cheaper, about $0.0084 for 2 turns, because the work stopped early. A full claim like claim_05 used 3 turns and cost $0.0156.

### System 2 — Context strategy

5. **The reduction.** From `budget.json`: baseline tokens, assembled tokens, reduction %. Which section dominates the assembled context, and why keep it verbatim?

As we can see by the budget.json file:
• Baseline tokens: 38,708
• Assembled tokens: 16,759
• Reduction: 56.7%
The dominant section is active, at 15,789 of 16,759 tokens (about 94%). The other sections are case_facts 204, resolved_refund 378 and resolved_subscription 406.2

It is kept in verbatim because active is the unresolved work the agent is acting on now. It holds exact details such as IDs, amounts, dates and customer wording, and a lossy summary could drop or alter them and cause wrong actions.

6. **Summarize vs preserve.** State the rule for what gets summarized vs kept byte-exact, citing your per-section token numbers.

The rule for what gets summarized vs kept byte exact is:
Summarize a segment only if its issue is resolved (378 tokens as resolved_refund and 406 tokens as resolved_subscription), meaning its key facts (amounts, IDs, statuses, dates) have settled and are also kept in the case-facts block (204 tokens in case_facts). Keep a segment byte-exact if its issue is still active, because any turn-by-turn detail could still change the next action (15,789 tokens as active).

As we can see by the file "system-2\runs\20261106-154320\budget.json", the token numebrs are the following:

| Section               │ Treatment                                                     │ Tokens │
├───────────────────────┼───────────────────────────────────────────────────────────────┼────────┤
│ case_facts            │ Structured block; identifiers and status tokens kept verbatim │    204 │
├───────────────────────┼───────────────────────────────────────────────────────────────┼────────┤
│ resolved_refund       │ Summarized (12,344 input tokens to 378)                       │    378 │
├───────────────────────┼───────────────────────────────────────────────────────────────┼────────┤
│ resolved_subscription │ Summarized (11,485 input tokens to 406)                       │    406 │
├───────────────────────┼───────────────────────────────────────────────────────────────┼────────┤
│ active                │ Byte-exact                                                    │ 15,789 │
├───────────────────────┼───────────────────────────────────────────────────────────────┼────────┤
│ Assembled             │                                                               │ 16,759 
├───────────────────────┼───────────────────────────────────────────────────────────────┼────────┤

The baseline was 38,708 tokens, so the reduction is 56.7%. All of the savings come from the two resolved threads, which together fell from about 23,800 tokens to about 780, roughly 97%. The active segment is about 94% of the final context and that is accepted on purpose. Summarizing it could save more tokens, but it risks dropping details like the failure code or the new card's last four digits that the live issue still depends on.

7. **Facts block.** Compare `eval.jsonl` to `eval_control.jsonl`. Which question regressed, and what does that prove?

Q6 regressed. It passed in eval.jsonl and failed in eval_control.jsonl. It proves the in_progress token appears only in the case-facts block. Neither the verbatim active turns nor the resolved summaries contain it, so compression can't carry it. Without that block the value is lost, and the model paraphrases or guesses instead.

### System 3 — Claude Code config

8. **Path-scoped rules.** Quote the glob frontmatter from one rule file. Why is it better than a directory-level CLAUDE.md for cross-cutting conventions?

From "system-3\.claude\rules\tests.md" , the frontmatter is:
description: Conventions for test files (co-located *.test.ts and *.test.tsx)
paths:
  - "**/*.test.tsx"
  - "**/*.test.ts"

It is better than a directory-level CLAUDE.md for cross-cutting conventions because:

• It follows the file type, not the location. Tests are co-located with source ( Cart.tsx  next to  Cart.test.tsx ), so test files sit in  src/components/ ,  src/pages/ ,  src/api/  and  src/db/ . A directory CLAUDE.md would need a copy in every one of those folders. Those copies would drift apart over time. A single  **/*.test.ts(x)  glob covers all of them.
• It loads only when needed. The rule loads when Claude edits a matching file. Test conventions don't take up context during unrelated work.
• It layers on other rules. The test rules apply on top of the React or API rules when the file under test is in those directories. Directory-scoped files can't express "any test file, anywhere".
• It's easy to maintain and audit. The conventions live in one file under  .claude/rules/ , in git, with a  description  field. The project's  CLAUDE.md  says it prefers this approach for the same reason.

9. **Forked skill.** Quote the `context: fork` and `allowed-tools` lines. What does running forked + read-only buy you? What breaks without it?

From "system-3\.claude\skills\deploy-check\SKILL.md":

context: fork
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(git status:*)
  - Bash(git diff:*)
  - Bash(git log:*)
  - Bash(git rev-parse:*)
  - Bash(git ls-files:*)
  - Bash(gh pr view:*)
  - Bash(gh pr checks:*)

Running forked + read-only buy you:
• Clean main session. The check walks the tree, parses diffs and runs several enumeration passes. That output stays in the fork. Only the short  verdict  /  checks  summary returns to the main conversation.
• Safety by construction. The allowlist has  Read ,  Grep ,  Glob  and a few read-only  git  and  gh  commands. It has no  Write ,  Edit ,  git push  or deploy commands. A pre-deploy check can't change files, push or deploy, even if the model tries to. Every teammate also gets the same checks, because the skill is project-scoped.

What breaks without them:

• Without  context: fork : the main session fills with  git status  output, file lists and check traces. That output has no value once the verdict is known. It pushes useful context out and makes later work worse.
• Without  allowed-tools : the skill would inherit the session's normal permissions, or prompt for them. A "validation" run could then edit files, commit, push or trigger a deploy, which defeats the point of a gate. The  Bash(git ...:*)  patterns also limit shell access to specific read-only subcommands.

10. **Scope.** From the validator output: project-level vs user-level scope. Give one example of each from this config.

Project-level (in git, shared with the team)

• Example:  .claude/standards/testing.md , which is imported from  ./CLAUDE.md . It says tests are co-located and the DB layer must not be mocked. Every teammate's Claude session loads it. The same scope covers  ./CLAUDE.md ,  .claude/rules/  and  .claude/commands/review.md .

User-level (personal, on your laptop, never reaches teammates)

• Example: a personal  /morning  summary command, or your preferred commit-message style, in  ~/.claude/CLAUDE.md  or  ~/.claude/commands/ .  CLAUDE.md  also mentions a stricter personal variant of the deploy check,  ~/.claude/skills/deploy-check-strict/ .

### System 4 — Orchestration

11. **Push work down.** Defects the SQL query returned vs warm-tier total. Name the indexed query. Why does the model never see the full history?

The warm tier (system4\data\warm.sqlite ) holds 40 defects, spanning 2026-03-02 to 2026-04-29. With since = 2026-04-01T00:00:00Z , the defects_since query returned 17 of 40. That is the same since the tests use, and the result is below the LIMIT 50 cap. A model-side filter would have had to load all 40 rows.

The index query is on WarmStore.defects_since in shift_monitor\warm.py and runs  SELECT * FROM defects WHERE ts > ? ORDER BY ts DESC LIMIT ? . SQLite's query plan reports  SEARCH defects USING INDEX idx_defects_ts (ts>?) . SQLite does the filtering, ordering and limiting. Python does no filtering by severity, component or time.

The model never sees the full history because pipeline.gather_new_defects  calls the query with  limit=50 , so at most 50 rows reach the prompt. The older rows stay in SQLite. Only the short hot state, which is trimmed by  _trim_to_budget , and the small slice of new defects go into the prompt. Anything older is fetched on demand, for example with  fetch_by_id  or  top_components_for_month.

12. **Crash recovery.** The resume-vs-fresh decision and its staleness threshold (`recovery.py`). Why is a fresh start with an injected summary sometimes more reliable than resuming?

The decision.  decide(state, now)  returns  "resume"  or  "fresh" :

• No manifest steps →  fresh . There is nothing to resume.
•  state.complete  →  fresh . The prior run finished, so a new run starts clean.
• Otherwise it compares  now - last_step.ts  against  STALE_RESUME_THRESHOLD_MINUTES = 30 . A gap of 30 minutes or less →  resume . A longer gap →  fresh . The comparison is inclusive ( <= ).

The threshold. 30 minutes is about 1/16 of an 8-hour shift. Inside that window the partial run is still working on the same shift's data. Past it, the partial run is treated as stale.

A fresh start with an injected summary can be more reliable because:

• Stale context. After a long gap, the partial run's context no longer matches reality. New defects have arrived and earlier conclusions may be outdated. Resuming would build on that stale picture.
• Bad partial state. A crash can leave half-finished reasoning or tool output. Resuming carries that forward. A fresh start drops it.
• Verified inputs only. The fresh run gets only the findings the manifest has already recorded, as a short summary. It also gets the new defects since the last step ( test_us03_crash_recovery.py  checks the "New defects since last partial step" text). The model works from recorded facts instead of whatever the crashed run was thinking.
• Context size. The prompt stays small and bounded. A resumed run keeps all of its old history.

The tradeoff is that a fresh start redoes work after the last recorded step. The manifest summary keeps that cost small.

13. **Small state.** Byte size of your `hot_state.json`. Why does the budget matter for a system run once per shift, indefinitely?

The hot_state.json has 980 bytes.

The budget matters for a system that runs once per shift, indefinitely because:

• Every prompt pays for it. The hot state goes into every invocation, so its size is a fixed cost on every run.
• No natural ceiling. The system never stops. If the state can grow with each shift, it eventually crowds out the new defects and the instructions, and eventually overflows the context window.
• Enforced in two places.  write_atomic  raises a  ValueError  if the state is over budget.  _trim_to_budget  in  pipeline.py  drops alerts until the state fits.  recent_defect_hashes  is also capped at 20 ( MAX_RECENT_HASHES ).
• Bounded cost and reliability. A bounded state keeps token cost and latency steady and avoids context bloat. It also forces older detail into the warm and cold tiers, to be fetched only when needed

---

## Part 2 — Synthesis

*Graded on connecting two or more systems. Cite a named file/artifact from each.*

14. **Three layers.** Point to a file/artifact for each layer and justify.

Model:  system-4\shift_monitor\client.py , chosen in  bridge.py   main() 

•  AnthropicClaudeClient  is the live model, used with  --live .  RecordedClaudeClient  is the offline stand-in.
• The model is only a swappable  ClaudeClient.complete()  call. It has no tools, no state and no file access.
• The same pipeline runs against either one. That is why I could run the whole bridge without a key.

Harness:  system-3\CLAUDE.md  plus its  .claude\standards\*.md , injected by  ConventionsClient  in  bridge.py 

• The harness is everything wrapped around the model call that controls what it sees and does.
•  ConventionsClient  puts the standing conventions at the top of every prompt, so they apply the same way on every run.
•  hot_state.json  is also part of the harness.  HOT_STATE_BYTE_BUDGET  caps it at 5 KB ( write_atomic  rejects anything larger), and it is 447 bytes in this run.
• Upstream, system-1's  claims_intake\loop.py  and  tools.py  are a second harness. They constrain claim decisions to terminal tools (route or escalate), with a backstop. Their outputs are what  bridge.py  reads.

Orchestration:  system-4\shift_monitor\pipeline.py   run_shift , driven by  bridge.py   main() 

•  main()  strings the systems together: read the system-1 run, write the warm tier, run the shift, update the hot state.
•  run_shift  decides what the model sees. It takes the hot state, fetches new rows with the indexed  defects_since  query, builds the prompt, parses the reply and trims it to budget.
• State is tiered (hot, warm, scratchpad).  recovery.py 's resume-or-fresh logic applies to a crashed run, though  bridge.py  doesn't call it yet.

The model decides nothing about control flow. Orchestration moves the data, the harness sets the rules and limits, and the model only produces the analysis.

15. **Deterministic vs prompt.** Cite one behavior guaranteed in code (terminal tool, read-only allowlist, atomic write, byte budget) and one guided by prompt. When is each right?

Guaranteed in code: the byte budget and atomic write.

• Where:  HotState.write_atomic  in  system-4\shift_monitor\state.py  raises a  ValueError  if the state is over 5,120 bytes.  _trim_to_budget  in  pipeline.py  drops alerts before that point. The write goes to a temp file, then  fsync , then  os.replace .
• Result in system-5:  data\hot_state.json  is 447 bytes. No model reply can make it bigger than 5 KB, and a crash can't leave a half-written file.
• Right when the rule must hold every time, no matter what the model says. That means safety, size limits, data integrity and anything irreversible. Prompts can drift or be ignored, so code is the only reliable place for these.

Guided by prompt: the  ConventionsClient  conventions and the response shape.

• Where:  bridge.py 's  ConventionsClient  puts  system-3\CLAUDE.md  and its standards at the top of the prompt. In  pipeline.py , the prompt also asks the model for an "Updated hot state proposal" JSON block.
• Result in system-5: the model is only asked to follow those conventions and that format. Nothing enforces it. The fallbacks  _parse_hot_state_update  and  _short_summary_from_response  handle replies that don't follow the format.
• Right when the behavior is judgment-based or stylistic, such as tone, which findings matter, how to word a summary, or what counts as an alert. These can't be written as a fixed rule, and an occasional miss is tolerable.

None is right, we should se code when a failure is costly or unrecoverable, and use the prompt when flexibility matters more than certainty.

16. **Context, two faces.** Compare context management in System 2 (intra-session) and System 4 (cross-session) with cited numbers from both. Same principle, different mechanism — how?

System 2, intra-session ( runs\20261106-154320\budget.json ):

• A 48-turn transcript is cut from 38,708 to 16,759 tokens, a 56.7% reduction.
• Resolved issues are compressed. Refund goes from 12,344 to 378 tokens, and subscription from 11,485 to 406 tokens.
• A 204-token case-facts block sits at the top, and the active segment (15,789 tokens) stays verbatim at the bottom.
• Mechanism: prune, extract facts and summarize inside one context window. The rules are in  assemble.py , which sets the header order.

System 4, cross-session ( system-4 ):

• Hot state is capped at 5,120 bytes, and the run I did produced 980 bytes.
• It holds at most 20 recent hashes. Only up to 50 new rows come from the warm tier, and the query returned 17 of 40.
• Mechanism: state lives outside the model, in tiers. SQLite and the cold tier hold the history, and a small file is reloaded each shift.

Same principle, different mechanism:

• The principle: the model sees a small, curated slice and never the full history. Stable facts go first, bulk detail is compressed or left out, and what's relevant now stays exact.
• Where the history lives: System 2 compresses history that is already in the window. System 4 keeps history out of the window entirely and retrieves it by query.
• How the limit is enforced: System 2 uses a token budget it measures ( count_tokens ). System 4 uses a byte budget checked in code ( write_atomic ).
• What carries over: System 2's case facts correspond to System 4's hot state. Both are small and exact, and both go in every prompt. System 2's compressed summaries correspond to System 4's warm and cold tiers.

17. **Reliability you can't see in one run.** Name one behavior a test guarantees that a single successful run would not reveal. Why does it matter before shipping?

Why a single successful run wouldn't show it:

• My run of  bridge.py  and the earlier system-4 run both ended happily, with  hot_state.json  at 447 and 980 bytes. In those runs the cap was never reached. A passing run only proves the happy path works.
• This guarantee only shows up on a rare input, 21 or more hashes. A run would only reach it after many shifts in a row, so a cap that was missing or broken would stay hidden until much later.

Why it matters before shipping: this system runs once per shift, indefinitely. Without the cap, the hot state would grow until it passed the 5 KB budget. At that point  write_atomic  would raise and the shift would fail, or the prompt would balloon. That would hit production weeks in, possibly at 3 a.m. The test checks that limit now, in one fast call, before it can cause an outage.

18. **Blast radius.** Pick one system. What's the blast radius if it misbehaves, and what's the kill switch? Ground it in that system's tools, enforcement points, and state.

For system-4:

What a misbehaving model can actually damage:

•  data\hot_state.json . This is the only state the model's output can change. A bad reply can put wrong alerts, a wrong summary or wrong threshold statuses into it. The next shift then starts from that. That is the realistic harm: a wrong "all OK", or a false ALARM.
•  data\shift_scratchpad.jsonl . The pipeline appends one entry per shift. A bad run adds a wrong conclusion, but only as an append.
• Not reachable by the model:
•  warm.sqlite :  defects_since  is a read-only  SELECT . Nothing the model returns can modify it.
• Cold summaries:  ColdStore  builds them from SQL counts, not from model output.
• Manifest:  Manifest.append_step  is called by code, not by model text.

Enforcement points that limit the damage:

• Size and shape:  HotState  is a frozen pydantic model, and  write_atomic  rejects anything over 5,120 bytes.  _trim_to_budget  also drops alerts before that point.
• Atomic write: temp file,  fsync , then  os.replace . A crash leaves the old state or the new one, never a half-written file.
• Fallbacks: if the reply doesn't parse,  run_shift  keeps the previous alerts and thresholds instead of using bad data.
• Resume or fresh: a stale partial run starts fresh ( recovery.py ), so a bad partial state isn't carried forward.

What is not enforced: the content is not checked. Within 5 KB, a confidently wrong summary will be saved and fed into the next shift, and no code catches it.

Kill switch (nothing in the code does this automatically):

1. Stop it. Stop the shift scheduler, since this runs once per shift. There is no flag, and  --recorded-response  is a replay mode, not an off switch.
2. Roll back. Delete  data\hot_state.json .  _ensure_hot_state  rewrites a clean "(no prior shift)" state on the next run, and the warm tier keeps the real history.
3. Audit.  data\shift_scratchpad.jsonl  is append-only, so you can see which shift introduced the bad state.

---

## Part 3 — Honest assessment

19. **What broke.** One thing that failed first try in your environment, and how you fixed it. (If nothing, what you checked to be sure.)

I had to use the API credentials as an env variable directly on the terminal, instead of an .env file. i had to check the variables were weel defined for the ANTHROPIC_API_KEY and ANTHROPIC_BASE URL.

20. **What you'd change.** One architectural decision you'd make differently, grounded in what you observed.

What I observed.

• In system-1's run  20261106_150040 , 6 of 8 claims were escalated, and all six hit the same reason: "model ended its turn without a terminal action (deterministic backstop)". Those claims also have an empty  claim_type  in  summary.md . These are ordinary claims such as a kitchen fire and a stolen bike.
• In  claims_intake\loop.py , the loop returns as soon as  stop_reason == "end_turn" . The rule that exactly one of  route_to_adjuster  or  escalate_to_human  must run is checked afterwards, in  run.py . Before that, it is only a prompt instruction.
• The backstop is safe: a human sees every unrouted claim. But it turns a fixable model slip into human work, with 75% escalation.

What I'd do differently.

• Keep the backstop as the last resort. Before it, have the loop send one corrective message, such as "You must call route_to_adjuster or escalate_to_human", and run one more turn. I would also consider forcing a tool call with  tool_choice  on that retry.
• I'd also log the retry as its own trace event, so that fixing the root cause shows up in the data.

Why this is grounded in the other systems too.

• System-4's design pushes guarantees into code and keeps the model's role small. System-1 does that at the end (the backstop) but not in the loop itself.
• The cost is small. The whole run cost $0.0837, and one extra turn per failing claim is a fraction of that.
• The tradeoff is a bounded extra cost and a retry that could fail again, so the backstop must stay.
