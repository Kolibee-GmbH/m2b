# Behavior catalog

The rules m2b keeps (B) and the defects a tool like it easily has and m2b must not (X), each with
the reason. The examples use invented data. A test that covers a rule says so in its docstring
(`Covers: B12`), and `scripts/check` fails while a rule has no test.

The rules stand in four parts, by what a rule is about:

| Part | Its rules are about | The page that describes it |
|---|---|---|
| [Core](behavior/core.md) | capture, the store and its backends, setup and configuration, what a session is given at its start and before a prompt, search, tasks and calendar, what holds for every add-on | [Getting started](getting-started.md), [Store format](store-format.md), [Configuration](configuration.md) |
| [Curation](behavior/curation.md) | the curation run: when it is due, its steps, the fence around a model step, the proposals and their answers, the review task, the commit of a run | [The curation run](curation.md) |
| [Band](behavior/band.md) | the core's mod: the band, the m2b pane, the slash commands, the model's two tools, and `m2b band`, the core's command for it | [The band](band.md) |
| [Worklog](behavior/worklog.md) | the worklog add-on | [The worklog add-on](addons/worklog.md) |

A rule stands in one part: the part of what it is about, not of the command that shows it. What
`m2b doctor` says about the band is a rule of the band, and what `m2b status` says about the
proposals is a rule of curation. In each part the behaviors come first and the defects after them.

An ID is a rule's name in the tests, in the docstrings of the code and in the rules that point to
one another. The IDs are counted across the parts, some numbers are not in use, and an ID stays
with its rule when the rule moves to another part. To find a rule by its ID:

```bash
grep -rn "^| B104 " docs/behavior/
```
