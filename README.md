# AI Team — a squad of AI engineers that argues about your codebase (and, if you let it, ships code)

A small crew of AI agents — CTO, Senior Backend, Product/Frontend, QA/Security — reads
the real git history of your own repositories, finds a genuinely debatable commit or
design decision, and **argues about it**. No rigid turn-taking: a moderator agent decides
who speaks next based on who actually needs to respond. Every agent has real read access
to your code through tools (`git log`, `git diff`, `grep`, file reading) — claims have to
be backed by something you can point at, not vibes.

That's the core, and it runs in 5 minutes against any public GitHub repo with a single
OpenAI-compatible API key. The same repository also contains the author's own, much
larger experiment built on the identical philosophy: a **~200-persona autonomous virtual
engineering org** that runs unattended on a GitHub Actions schedule, opens real branches,
writes real code, runs real tests, and merges — with a human keeping final say on `main`.
Both are in this repo; which one you use depends on how much you want to hand off.

## Why this exists

Most "AI writes your code" tools optimize for agreement — one model, one pass, ship it.
The failure mode that actually costs teams money is different: nobody in the room had a
reason to push back. This project's bet is that **structured disagreement between
specialized personas, grounded in the literal code, catches more real problems than a
single fast model does** — the same reason human code review works. It's cheap to test:
point it at a repo, read the argument, see if it would have caught the thing your last
incident retro complained about.

## Who it's for

- **Solo founders / small teams without a code-review culture.** You're the only
  engineer, so nobody plays devil's advocate. This gives you four opinionated,
  code-grounded voices for the price of a few cheap-tier API calls.
- **Maintainers of public repos who want a standing second opinion** on architecture and
  risk, running on a schedule, without paying for a human reviewer's time on every commit.
- **Teams evaluating whether multi-agent orchestration is worth adopting** — this is a
  complete, working reference implementation (personas, tool-use, a moderator-driven
  group chat, cost controls) built on Microsoft's `agent-framework`, not a toy demo.
- **Anyone who wants to go further** — the advanced mode in this same repo shows the
  identical philosophy scaled to ~200 personas actually writing, testing, and merging
  code autonomously, which is the natural next step once the core discussion loop earns
  your trust.

## What's actually running today (scale)

| | |
|---|---|
| Core discussion team | 4 fixed personas (CTO, Backend, Product/Frontend, QA/Security) + 1 moderator + 1 "code scout" |
| Extended experimental roster | ~200 personas across `agents/global_elite.py`, `agents/global_elite_100.py`, `agents/expansion_geniuses.py`, `agents/engineering_fellows.py` — board meetings, an executive board, engineering squads, mentorship, research |
| Model routing | 225+ individually overridable role→model assignments (`config/models.py`), spread across GPT, DeepSeek, Grok, Kimi, Mistral, Llama — no single-vendor lock-in |
| Providers | Any OpenAI-compatible endpoint (OpenAI itself, OpenRouter, Groq, local vLLM/Ollama) out of the box; Azure AI Foundry as an alternative backend |
| Scheduled autonomy | 14 independent GitHub Actions workflows (`.github/workflows/`) — company-wide "pulse" discussions, individual/squad initiative, board meetings, HR check-ins, breakthrough proposals, GTM drafting, and more, each on its own cadence |
| Real engineering execution | Isolated `git worktree` per parallel task (not a shared branch), automatic test execution before merge, a 4th "Review Gate" agent doing pytest + fuzzing, CTO-escalation instead of a human blocking every merge |
| Safety limit | Every discussion is capped (`MAX_MESSAGES`, default 24) — a hard stop against runaway argument loops and runaway API cost |

None of this is a mockup — it's the actual system the author runs daily against a
production SaaS codebase, with real bugs found and fixed by it (missing retry wrappers,
a broken concurrency guard, a phase-transition bug that silently failed to persist to
disk, a structural isolation bug that kept senior read-only agents from ever seeing ideas
generated elsewhere in the org).

## How it works

```
main.py
  └─ workflows/discussion.py
       1. clone_or_update_repos()      — sync TARGET_REPOS locally
       2. find_discussion_topic()      — a "Code Scout" model reads git log
                                          across all repos, picks ONE debatable
                                          commit/change, formulates ONE question
       3. build_team()                 — instantiate the 4 (or custom) personas,
                                          each with git/grep/read tools
       4. GroupChatBuilder + moderator — moderator agent decides who replies next
                                          (mentioned-by-name > direct question >
                                          contradicts someone's domain > default)
       5. stop when the moderator calls consensus/deadlock, or MAX_MESSAGES hit
```

Personalities live in `agents/team.py` and are the part that actually matters: each one
has a stable point of view, a concrete trigger for disagreeing with a specific other
role, and an explicit instruction to verify claims against the code via tools before
agreeing or objecting. A CTO who's watched elegant solutions die when the original author
left; a backend senior who doesn't believe "it works" until they've read the diff; a
recent-grad product voice whose job is dragging the room back to the end user; a QA/
security engineer whose job is to be inconvenient. None of them write code in discussion
mode — they only get `write_file` access in the (opt-in) execution modes.

## Quickstart

```bash
git clone <this repo> ai-team && cd ai-team
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

In `.env`, set two things:

```bash
TARGET_REPOS=myapp=github.com/you/myapp.git   # your repo(s); comma-separated for more
OPENAI_API_KEY=sk-...                          # or any OpenAI-compatible provider
```

Public repos need nothing else. Private repos need `GITHUB_TOKEN` (classic PAT, `repo`
scope). Then:

```bash
python main.py
```

First run auto-drafts `context/company_context.md` from your repo's README and file
structure if it doesn't exist yet — you get a working discussion with zero manual setup.
Open that file afterward and fill in real business/architecture context; it's the single
biggest lever for discussion quality.

## How to scale it up

Everything below is additive — none of it requires touching the core discussion loop:

- **Add a participant** — copy `config/custom_agents.yaml.example`, describe id / model /
  personality, done. No Python.
- **Remove a built-in role** — `DISABLE_ROLES=product_frontend,qa_security python main.py`.
- **Point it at more repos** — `TARGET_REPOS=api=...,web=...,infra=...`; the Code Scout
  reads git log across all of them and can pick a cross-repo question.
- **Swap the model tier per role** — every role has its own `MODEL_*` env var
  (`.env.example` documents all of them); start on the cheap tier (`gpt-5.4-mini`/`-nano`),
  raise individual roles once the discussion logic earns it.
- **Swap the provider entirely** — `MODEL_PROVIDER=openai` (default, works with any
  OpenAI-compatible endpoint including local vLLM/Ollama) or `MODEL_PROVIDER=azure_foundry`
  (needed only if you want non-GPT models like DeepSeek/Grok/Kimi via Azure AI Model
  Inference, used by the extended roster).
- **Go from "discuss" to "execute"** — the same repo's `workflows/engineering_task.py`
  and `main_engineering.py` show the full pattern for letting an agent actually branch,
  write, test, and merge, with per-task `git worktree` isolation and a lock scoped only
  to the merge step (not the whole task) so multiple agents can work the same repo in
  parallel without racing.
- **Go from "one team" to "a company"** — `main_board.py`, `main_executive.py`,
  `main_company_pulse.py`, and friends, plus their `.github/workflows/*.yml` counterparts,
  show how to run the same philosophy unattended on a schedule with dozens of personas
  instead of four. This part is tuned for the author's own model catalog; expect to
  override role→model assignments for your own providers (documented in
  `config/models.py` and `.env.example`).

## Honest limitations

- The extended ~200-persona roster and its GitHub Actions workflows assume an
  Azure AI Foundry catalog for several roles; getting it running on pure
  `MODEL_PROVIDER=openai` means overriding those roles yourself — the core 4-agent
  discussion doesn't have this problem.
- A discussion currently just prints to the console / posts to Telegram; nothing persists
  it as a tracked decision yet (e.g. `decisions/<date>.md` or a GitHub Issue) — this is
  the most obvious next contribution.
- This is a young, single-maintainer project, not a mature framework — expect rough
  edges outside the path the author has actually run in production.

## License

MIT — see [LICENSE](LICENSE).
