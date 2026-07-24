# AI Team — an autonomous team of AI "geniuses" that argues about your codebase

A small crew of AI agents (CTO, Senior Backend, Product/Frontend, QA/Security)
reads the real git history of your own repositories, finds a genuinely
debatable commit or design decision, and argues about it — no rigid
turn-taking, a moderator decides who speaks next based on who actually
needs to respond, and every agent has real read access to your code
through tools (`git log`, `git diff`, `grep`, file reading).

The philosophy: **real disagreement, not polite small talk.** Every
agent has a stable point of view and professional pride — a CTO who
cares about the architecture surviving growth, a backend senior who
doesn't believe "it works" until they've checked the code, a product
voice who keeps dragging the conversation back to the end user, a
paranoid QA/security engineer whose job is to be inconvenient. They are
required to argue *from the actual code*, not in the abstract.

This started as a private tool for one solo founder's own project. This
fork strips out everything project-specific so **you can point it at
your own repo(s)** — cheaply, with any OpenAI-compatible model provider,
without needing an Azure account.

## Structure

```
ai-team/
├── config/
│   ├── models.py            # which model plays which role
│   ├── client_factory.py    # model provider (OpenAI-compatible, or Azure AI Foundry)
│   └── custom_agents.yaml.example  # add participants without touching Python
├── agents/
│   ├── team.py               # the core four personalities
│   ├── custom_agents.py      # loader for your own custom agents / DISABLE_ROLES
│   └── _shared_context.py    # reads context/company_context.md for every agent
├── tools/
│   ├── repo_tools.py         # git clone/log/diff/grep/read for agents
│   └── context_builder.py    # auto-drafts company_context.md from your repos
├── context/
│   ├── company_context.template.md  # generic starting point, copy & fill in
│   └── company_context.md    # the author's own filled-in example (BLD System)
├── workflows/
│   └── discussion.py         # builds the GroupChat + topic scout
├── main.py
├── requirements.txt
└── .env.example
```

Everything else in `agents/`/`workflows/` (board meetings, executive
board, a ~200-person extended "genius" roster, engineering task
execution, etc.) is the author's own experimental extension of the same
philosophy to a bigger virtual company. It still works, but it's tuned
for the author's own Azure AI Foundry model catalog and isn't the focus
of this fork — see [Beyond the core discussion](#beyond-the-core-discussion-advanced)
below if you want to explore it.

## Install

```bash
cd ai-team
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Setup (5 minutes, no Azure needed)

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Set `TARGET_REPOS` to your own repo(s):
   ```bash
   TARGET_REPOS=myapp=github.com/you/myapp.git
   ```
   Multiple repos: `TARGET_REPOS=api=github.com/you/api.git,web=github.com/you/web.git`
   Public repos need nothing else. Private repos need `GITHUB_TOKEN`
   (classic PAT, scope `repo`).

3. Get an API key from [platform.openai.com](https://platform.openai.com)
   (or any OpenAI-compatible provider — OpenRouter, Groq, a local
   vLLM/Ollama server) and set `OPENAI_API_KEY` (+ `OPENAI_BASE_URL` if
   it isn't OpenAI itself). `MODEL_PROVIDER=openai` is already the
   default in `.env.example` — this is the only credential you need.

That's it — no Azure account, no `az login`, no deployment names to match up.

## Run

```bash
python main.py
```

What happens:
1. Your repositories are cloned (or pulled if already present) into `./repos`.
2. If `context/company_context.md` doesn't exist yet, it's **auto-drafted**
   from each repo's README and file structure (see
   `tools/context_builder.py`) — you don't have to write anything by
   hand to get started. Open the file afterwards and fill in what the
   auto-draft can't know (business priorities, architectural invariants,
   known issues) — the team gets noticeably sharper once you do.
3. A "Code Scout" model looks at recent commits across all your repos
   and formulates one specific, debatable question.
4. The discussion starts — agent messages print in real time as they arrive.
5. It stops when the moderator decides the team reached a conclusion,
   or after 24 messages (`MAX_MESSAGES` in `workflows/discussion.py` —
   a safety limit against endless arguing / runaway API cost).

## Add or remove participants — no code required

**Add someone:** copy `config/custom_agents.yaml.example` to
`config/custom_agents.yaml`, describe the agent (id, model, personality
instructions), run `main.py` again. See the example file for the format
— the personality prompt is the part that matters most; look at
`agents/team.py` for what a well-written one looks like (a stable
opinion, a concrete trigger for disagreeing with specific other roles,
a requirement to ground claims in the actual code).

**Remove someone from the built-in four:**
```bash
DISABLE_ROLES=product_frontend,qa_security python main.py
```
(or set `DISABLE_ROLES` in `.env`). Works for custom agents too.

## What you'll definitely want to tune

- **Message limit** (`MAX_MESSAGES` in `workflows/discussion.py`) —
  start small (10-12), see how the argument goes, raise it later.
- **`context/company_context.md`** — the single biggest lever for
  quality. The auto-draft is a floor, not a ceiling; a few paragraphs of
  real business/architecture context turn generic commentary into
  sharp, specific pushback.
- **Personalities** (`agents/team.py`) — if the discussion feels too
  polite, sharpen the concrete disagreement triggers between roles.
- **Cost**: each agent with tools can make several `read_file`/`grep_repo`
  calls per turn — that adds up on top reasoning models fast. The
  defaults in `.env.example` are already the cheap tier
  (`gpt-5.4-mini`/`gpt-5.4-nano`); raise individual roles (`MODEL_CTO`,
  `MODEL_QA`, etc.) once you like the discussion logic and want more depth.

## Beyond the core discussion (advanced)

The repository also contains the author's own, much larger experiment:
an autonomous virtual company of ~200 AI "geniuses" (board meetings,
an executive board, engineering squads that actually write and commit
code on branches, mentorship, lab sessions, GTM drafting, and more —
see the `main_*.py` entry points and `context/company_context.md` for
the fully worked example). It's real, working code, and the same
philosophy (real disagreement, honesty over pleasant reports, discussion
and implementation as separate modes, a human always has final say on
`main`) — but its model assignments in `config/models.py` are tuned to
the author's own Azure AI Foundry catalog (specific deployment names,
some third-party models via Azure AI Model Inference). If you want to
run these modes on `MODEL_PROVIDER=openai`, override the roles you need
via the `MODEL_XXX` environment variables documented in `.env.example`
and `config/models.py`.

## Logical next step

Right now a discussion's outcome just prints to the console and is
lost. Once you're happy with the discussion logic, the natural next
step is persisting it — e.g. to `decisions/<date>.md`, or as a GitHub
Issue via the `gh` CLI / GitHub API — so the team's arguments become
tracked decisions instead of a conversation into the void.
