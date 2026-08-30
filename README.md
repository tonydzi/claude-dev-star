# Dev Star

**A strategy radar for your Claude Code sessions — not another cost tracker.**

Plenty of great dashboards tell you *how many tokens you burned and what it cost*
(ccusage, claude-usage, claude-radar, token trackers). Dev Star answers a different
question:

> **Where is my effort actually going — and is it moving me forward, or just keeping
> the lights on?**

![Dev Star demo](docs/demo.png)

It reads your local Claude Code transcripts, classifies each session into a *direction*
with deterministic keyword rules (no LLM calls, nothing leaves your machine), and draws
a star: one spike per direction, spike length = share of output tokens.

- **Gold spikes** move you forward: sales, product, content, research.
- **Grey spikes** are support work: infra, maintenance, ops.
- A forward direction starving below 10% gets a **pulsing red ring** — that's the spike
  you should be feeding.

The verdict line at the top is the whole point: *"48% of your effort moves you forward;
52% keeps the lights on. Starving: Sales, Content."* If you run tens or hundreds of
sessions a week, this is the drift you can't see from inside any single session.

## Install & run

No dependencies, Python 3.8+:

```bash
curl -O https://raw.githubusercontent.com/tonydzi/claude-dev-star/main/dev_star.py
python3 dev_star.py
```

Open `dev-star.html` in a browser. That's it.

```
python3 dev_star.py --n 200            # bigger window (default: last 50 sessions)
python3 dev_star.py --config my.json   # your own directions & keywords
```

## Make the directions yours

The defaults (sales / product / content / research / infra / ops) fit a small product
team. Your goals are different — edit them. `--config` takes a JSON of the same shape
as `DEFAULT_DIRECTIONS`:

```json
{
  "thesis":   {"label": "PhD thesis",      "forward": true,  "kw": ["chapter", "experiment", "citation"]},
  "teaching": {"label": "Teaching",        "forward": true,  "kw": ["lecture", "grading", "syllabus"]},
  "admin":    {"label": "Uni admin",       "forward": false, "kw": ["form", "committee", "email"]}
}
```

`forward: true` means "this moves me toward my actual goals". The star doesn't judge
what your goals are — it just shows you whether your sessions agree with them.

## The machine-readable half

`dev-star.json` is written next to the HTML: every session with its direction, tokens
and title, plus the per-direction aggregate. Feed it back to your agents (drop it in a
CLAUDE.md pointer or read it at session start) so they also know where the effort is
going before they start building something new.

## How it counts

- Only **output tokens** (the work Claude actually produced), deduped by `message.id` —
  Claude Code repeats the usage block on every record of a message, so naive summing
  overcounts significantly.
- Classification is by keywords over the session title + first user message. Ties go to
  the highest hit count; sessions with no hits land in "Other". It's deliberately dumb,
  transparent, and editable — no LLM judge, so it's free and reproducible.
- Sub-agent sidechains are excluded from the first-message sniffing but their tokens
  count toward the session that spawned them.

## Roadmap

- Task graveyard: surface long-untouched tasks from your tracker with a
  revive / reconsider / bury verdict (we run this internally on our Obsidian task
  registry; a generic adapter needs a frontmatter contract).
- Multi-machine merge: per-host JSON + one fleet-wide star (we run this across 6
  machines; the merge is in our internal version and will land here next).

---

Built by [Palo Alto AI Research Lab](https://github.com/tonydzi) —
we run an autonomous multi-machine Claude Code fleet and publish the parts that
generalize. Issues and PRs welcome; if you try it on 100+ sessions we'd love to see
your star.
