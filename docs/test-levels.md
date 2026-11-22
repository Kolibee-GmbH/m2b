# Test levels

Where each of the costly checks sits, the ones that start a real model, and what it checks there.
The rule behind it is in [Contributing](../CONTRIBUTING.md#test-levels): every check has one level,
the lowest that can show it, and a higher level checks nothing a lower one checks already. A new
model scenario or eval case gets a line here.

## Model scenarios

`scripts/e2e --level model` ([End-to-end scenarios](../CONTRIBUTING.md#end-to-end-scenarios)).
Where a scenario also has a stub version, the stub checks the chain of commands, hooks and files
with a scripted model, and the model version checks only what a real model or a real Claude Code
adds to it: how a model step files, or how Claude Code passes things on. That is why both stay.

| Scenario | Also at the stub level | What the model level checks |
|---|---|---|
| `E1-capture` | yes | a real ingest files a fact and a task, and a real second run over the empty inbox adds nothing |
| `E2-restart` | yes | a real ingest gives a capture with a follow-up its one task, and one with a link its task and its ref; reruns and crashes are the stub's |
| `E6-failing-step` | yes | with `claude` unreachable the model steps fail, the review names it and the next attempt waits |
| `E7-quiet` | yes | a real run files a quiet capture so that search finds it and the distillate and review never bring it up |
| `E10-fence` | yes | Claude Code's own permissions deny the lint skill its fix under the fence, and the step reports it |
| `E11-candidates` | yes | a real ingest files harvested candidates as facts, each with its evidence once |
| `E14-topics` | yes | a real ingest puts a customer's fact, a customer's work and the owner's own matter under the right headings |
| `E16-expiring-fact` | yes | a real ingest gives a fact with a day a file of its own with `until` |
| `E17-planted-capture` | yes | a real ingest files nothing from captures written to steer it, and files the owner's own |
| `E18-remember-beside-auto-memory` | yes | beside Claude Code's own memory a real session notes the owner's words in m2b, and Claude Code's memory stays empty |
| `E19-search-across-languages` | yes | a real session searches an English word with its German translation |
| `E21-earlier-values` | yes | a real ingest keeps a changed fact's earlier value with its day |
| `E22-recall-across-projects` | yes | promise 1: told in project A, asked in project B, answered |
| `E26-tick-a-task` | yes | a real session ticks a task through the todos skill, which an eval cannot run |
| `E27-session-hands-in` | yes | a real session in a terminal of the owner's hands in through the mod's tool |
| `E31-file-asks-first` | yes | Claude Code asks before `m2b capture-file`, and without a yes nothing is copied |
| `E32-file-captured` | yes | with the yes the capture skill copies the file with a note beside it |
| `E33-project-known` | yes | a real ingest files a project capture as a topic with its `Repository:` line, and a session in the clone gets it |
| `E34-session-read` | no | the reading of sessions reads an interactive session as typed |
| `E35-correction-kept` | no | promise 5: a correction kept in two repositories holds in a third |
| `E36-correction-read` | no | promise 5: a correction the reading of sessions finds holds in a third repository |
| `E37-fact-after-its-day` | no | promise 3: after its day the distillate says what holds now |
| `E39-start-stays-small` | no | promise 8: Claude Code hands the session the distillate within 8 KB and the lessons in an output of their own |
| `E40-task-on-friday` | no | promise 2: "remind me ... on Friday" gives one task due that Friday |
| `E41-project-elsewhere` | no | promise 6: a session in another repository knows where a kept project lies |
| `E42-words-kept` | no | promise 4: the fact file behind a distillate line points to the note with the owner's words |

Checked once, not twice:

- `E18` checks that a real session's note reaches m2b and Claude Code's memory stays empty; `E22`
  checks only the answer in the other project.
- `E16` checks that a real ingest files a fact with a day with `until`; `E37` checks what holds
  after the day: the distillate's line and the fact file, which no longer holds an end.
- `E33` checks the topic a project becomes and the start in its clone; `E41` checks only the answer
  in another repository.
- The eval `correction` checks that a session keeps a correction as a lesson; `E34` that the reading
  reads an interactive session; `E35` and `E36` check only what the third repository runs.
- The unit tests check that the distillate is cut at 8 KB and that the lessons have a block of their
  own; `E39` checks only what Claude Code hands the session.
- `E6` and `E10` check how a run reports a failed or a denied step. A promise case that runs a
  curation run checks that no review task was made, which is how the owner sees such a run.

## Eval cases

`claude plugin eval` ([Evals](../CONTRIBUTING.md#evals)): what one session answers or calls, with
m2b and without, for one prompt. What each case asks and when it passes is on
[Evals](evals.md); here only where it sits beside the scenarios.

| Cases | What they check | Beside them |
|---|---|---|
| `recall`, `details`, `outline`, `topic`, `no-invention`, `no-false-lead` | a session answers from the store, from a fact's details and a document's outline, gets a topic only when it is named, and says what it does not know | `E19` checks the search across languages, `E42` the chain behind a fact after a real run |
| `note`, `routing`, `correction` | a session keeps a note, a project's todo in the project, a correction as a lesson | `E18` the note beside Claude Code's memory, `E35` the lesson's effect in another repository |
| `propose-agreement`, `propose-asked`, `propose-known`, `propose-nothing`, `propose-person`, `propose-planted` | when a session hands in a proposal and when not | `E27` the tool in the owner's terminal |
| `no-leak`, `coding` | nothing of the owner's notes in a public repository; a coding task without notes, searches or proposals | |
| `no-leak-de`, `no-leak-plain`, `propose-person-de`, `propose-person-plain`, `propose-planted-de`, `propose-planted-plain` | the second and third wording of three suite cases, for promise 7 | |

## Model step measures

`scripts/ingest-eval` ([How well a model files an inbox](../CONTRIBUTING.md#how-well-a-model-files-an-inbox))
and `scripts/glean-eval` ([What a model finds in typed prompts](../CONTRIBUTING.md#what-a-model-finds-in-typed-prompts))
measure how well one model step judges a fixed input, per model. The scenarios above count no
quality: they check that a real step's filing lands as the store needs it.
