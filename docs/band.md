# The band

The band is m2b's row in a Claude Code session: it says how many things wait for you and has the
one button that opens the m2b pane. In a terminal it is the end of the hint line below the
prompt, in the desktop app a row above the prompt, unless the setting
[`band.place`](#where-it-stands) says otherwise. It is part of m2b and needs no setup of
its own; it starts once m2b is set up on the machine.

```text
 m2b  4 wait for you  1 overdue  2 due today  [ open ]
╭──────────────────────────────────────────────────────────────╮
│ >                                                            │
╰──────────────────────────────────────────────────────────────╯
```

## What it shows

The row begins with `m2b` and has one button, `open`, which shows
[the m2b pane](#this-session-what-waits-and-today-in-the-pane). Everything you answer is there:
the band holds no button that writes. Claude Code lets you fold the band away (Ctrl+X, then
Ctrl+A) and no plugin can unfold it, so nothing stands only in the band. Where the row is longer
than its line, its counts are cut at their end and `m2b` stays whole.

- **How many things wait for your answer**, `4 wait for you`: memory candidates
  ("Remember? ...", proposed with `m2b tasks add --candidate`), "Still current?" questions about
  items of the distillate that have gone quiet, "Still needed?" questions about lessons that went
  quiet, proposals from your sessions
  ([curation](curation.md#reading-your-sessions)) and the open review of the last curation run,
  each counted as one. The pane lists them with keep, drop and `ok`.
- **How many proposals your sessions handed in**, `1 handed in`, while they wait for a curation
  run to take them in ([What a session hands in](curation.md#what-a-session-hands-in)). They
  are counted apart from what waits for you: nothing of them can be answered before that run.
  On the machine that curates the count stands at full strength, and `curate now` in the pane
  starts the run; on any other machine it is stepped back. While a run is under way the row
  says nothing of them, and after it they are among what waits for you.
- **Your tasks due today or overdue**, your own, not the curator's, as this machine shows them:

  | `band.due_tasks` | The band |
  |---|---|
  | `count` (without an entry) | `1 overdue  2 due today` in the row |
  | `list` | below the row the first three by name, today's first, then the overdue ones, the most recent first, then `and 2 more`; counted as with `count` where the band stands [below the prompt](#where-it-stands) |
  | `off` | none |

  ```text
   m2b  4 wait for you  [ open ]
        due today Call Dana
        overdue   Return the drill
  ```

  `overdue` is drawn in the color of an error and `due today` in the color of a warning; the
  title stands at full strength. `m2b settings set band.due_tasks list` changes it, and so does
  a press on `list` under `Tasks in the band` in [the settings](#every-setting-in-the-pane). The
  pane lists the tasks whatever the band shows.
- **How many topics m2b gave this session**, `2 topics`, only while `band.topics` is on
  (`m2b settings set band.topics true`, or `on` under `Topics in the band` in the settings). The
  pane names them either way.

The colors are your theme's: `m2b` in the color Claude Code uses for what it remembers, what
waits in the color of a warning.

In place of the counts the row is one sentence where m2b could not read the task list or the
proposals, or where `open` could show no pane. What m2b says to a press in the pane stands in the
pane, where the press was made. While nothing waits, no task is to show and nothing is wrong,
the row is `m2b` and `open` alone, or there is none, as [`band.place`](#where-it-stands) says.

`open` is your own open of the pane, so Claude Code places it at any width: under the fullscreen
layout from 110 columns beside the chat, where it stays, and elsewhere as a dialog that Escape
closes, on a terminal the block above the prompt. Where no pane can be shown, or Claude Code
refuses to open one, the band says so and names `/m2b-pane`, which answers with the lines.

The band draws every text as one plain line: escape sequences and control characters a capture
brought along from terminal output are left out, line breaks and tabs become spaces. The texts of
a proposal are the exception: there each such character is written out (`\x1b`, `\u202e`) instead
of left out, and so is every other character a terminal draws with no width (zero-width
characters, soft hyphens, variation selectors, tag characters), because keep keeps the text as it
is stored, and a part the pane left out would be kept unseen.

### Where it stands

`band.place` in the machine config says where the band stands on this machine.
`m2b settings set band.place above` changes it, and so does a press on a value under
`Where the band stands` in [the settings](#every-setting-in-the-pane). A value you set holds in
every session, in a terminal and in the desktop app alike.

| `band.place` | The band |
|---|---|
| without an entry | below the prompt in a terminal, above it in the desktop app and on every other surface |
| `above` | its row above the prompt in every session, calm while it has nothing to say |
| `waiting` | its row above the prompt only while it has something to say: a count, a task or a sentence |
| `below` | nothing above the prompt; the hint line below the prompt ends in the band |

Without an entry the band picks its place by where the session is drawn. Only a terminal draws
what the band adds to the hint line, so with `below` the desktop app shows nothing of m2b: there
it stands above the prompt. `m2b config get band.place` answers `null` then, and the settings say
`below in a terminal, else above`. Once you set a value, nothing in the pane turns it back into
no entry; `m2b config set band '{"due_tasks": "count", "topics": false}'` writes the section
without it, with the values you keep for the other two.

With `above`, the row is calm while nothing waits, no task is to show and nothing is wrong: `m2b`
and `open` alone, both dim.

```text
 m2b  [ open ]
╭──────────────────────────────────────────────────────────────╮
│ >                                                            │
╰──────────────────────────────────────────────────────────────╯
```

The pane is then one press away in every session: a click on `open`, or Ctrl+X, then Tab, which
puts the focus on the button, and Enter. With `waiting` the band draws nothing while the row
would be calm and takes no room; `/m2b-pane` opens the pane.

With `below`, m2b draws nothing above the prompt. The hint line below the prompt, where Claude
Code says `? for shortcuts`, ends in the band: after Claude Code's own text stand `m2b`, the
counts in their colors and the way into the pane.

```text
  ? for shortcuts  m2b  4 wait for you  1 overdue  2 due today  [ open ]
```

The way into the pane is the button `open` under the fullscreen layout, where a mouse click
presses it. No key reaches a button below the prompt, and outside the fullscreen layout no click
does either, so there the line names the command `/m2b-pane`, dim, where the button would stand.

![A Claude Code session on the main screen with band.place set to below: nothing of m2b stands above the prompt. The hint line below the prompt reads "manual mode on", "? for shortcuts" and "1 agent" in the dim text of Claude Code and ends in "m2b", "1 waits for you", "1 overdue" and "1 due today" in their colors and the command /m2b-pane, dim](images/band-below.png)

<sub>One real Claude Code session on a demo machine with invented notes, recorded by `scripts/readme-images --only band-below` in a terminal of 130 columns. Nothing is typed and no model is asked.</sub>

m2b draws its part only where the line has room for it, and never cuts Claude Code's text. The
room is counted with Claude Code's hint and with 27 cells for the label of the session's mode,
which Claude Code draws before the hint: the widest one, `bypass permissions on`. Where the line
has not room for every count, the last give way first and `…` stands for them:

```text
  ? for shortcuts  m2b  4 wait for you  …  /m2b-pane
```

Where not even the first count has room beside that mark, and where the width of the line is not
known, the line stays Claude Code's, which adds m2b's words at its end, dim, and cuts them where
the line ends:

```text
  ? for shortcuts · m2b 4 wait for you · 1 overdue · 2 due today · /m2b-pane
```

While nothing waits, the line ends in `m2b` and the way into the pane alone (`m2b · /m2b-pane`
in Claude Code's own line). A sentence in place of the counts stands at the end of the line too.
The hint line is one line, so your tasks due are counted there and never listed: with
`band.due_tasks` set to `list` the band below the prompt counts them as with `count`. What another
plugin added to the hint line stays, before m2b's part.

Before m2b's first answer in a session the band draws nothing, wherever it stands.

## When a curation run fails

Each open session shows one line for a few seconds, once per failed run: `m2b: the curation run of
18:00 failed; its review task says why, and /m2b-review shows it` (the time for a run of today,
the date for one before). A reload of the
plugins does not show the same run again; a run that succeeds shows nothing, and neither does an
interrupted one, which the status line names. The status line says
`last curation run failed` until the next run succeeds.

## Noting without the model

`/m2b-note <text>` writes the text into the inbox at once, through `m2b capture`, and answers with
one line that shows how it begins:

```text
> /m2b-note Sam brings the plywood on Saturday, the long boards too
  noted: Sam brings the plywood on Saturday, the long board…
```

No model turn runs for it, so it costs no model turn and does not wait: Claude Code runs the
command also while a turn is working. The text goes in as typed, quotes and dashes included, with the
source `claude`, as a capture through the skill would; the next curation run files it. Without
text it writes nothing and says what it needs; when `m2b` fails, the line says why, starting with
`not noted:`. The confirmation stays in the conversation, where the model reads it in its next
request.

`--due` before the text also makes a task due that day, as a follow-up of `m2b capture` does:
`today`, `tomorrow` (on your machine's clock) or a day as `YYYY-MM-DD`.

```text
> /m2b-note --due tomorrow Call Sam about the long boards
  noted: Call Sam about the long boards; a task is due 26 Nov
```

Where the task list does not answer, the note is written all the same, and the line says in m2b's
words that the task follows with the next curation run. A day that is none of these forms writes
nothing and names them. To note with the model's help, for instance with a day said in words
("next Friday"), ask the model: it uses the tool below, or the skill `/m2b:capture` where the mod
does not run.

The pane's overview has the same at its top: a field `note`, and below it the day of a task for
the note, `no day` until you press `today`, `tomorrow` or `in a week`. Tab walks from the row of
tabs into the field. Enter keeps the text after the five seconds of `undo` every press that writes
has; then the field is empty, the day is `no day` again, and "This session" counts the note.
Below the values stands what the write said, in the error color where nothing was written, and a
note that was not written goes back into the field, unless you typed something there meanwhile. What
you type stays in the field over the band's reads and the end of a turn, and when you close the
pane with Escape and open it again; it is in no state another plugin reads, only a hook on the
pane's input sees it ([SECURITY.md](../SECURITY.md#what-you-type-into-the-pane)).

## This session, what waits and today, in the pane

`/m2b-pane` opens the m2b pane in the view it starts in, its overview, with
[the row of tabs](#the-tabs) at its top, the field `note` below it
([Noting without the model](#noting-without-the-model)) and four parts below that. (`/m2b` alone is not this command: Claude Code runs the skill
`/m2b:m2b` for it, which asks the model what m2b is.)

![A Claude Code session in the fullscreen layout after /m2b-pane: the m2b pane sits beside the chat, under the tabs Overview, Proposals 3, Review, Tasks, Facts and Settings. Below them stands the field "note" with "what to keep" in it and the day of a task for the note, "no day" marked, then today, tomorrow and in a week. The part "Waits for you", framed in the warning color, counts 5: 3 proposals from your sessions, in the tab Proposals; a "Still current?" question with keep and drop; the review of the last curation run with ok and "1 fact changed: Sam". The part "Today" names one task due today and one overdue, and the part "This session" begins below it. Left of the pane the band above the prompt is one row, "m2b 5 wait for you" with the button "open", and the two tasks below it](images/pane.png)

As text, another session:

```text
┌──────────────────────────────────────────────────────────────┐
│ [ Overview ] [ Proposals 1 ] [ Review ] [ Tasks ] [ Facts ]  │
│ [ Settings ]                                                 │
│                                                              │
│ note: what to keep                                           │
│ ● no day [ today ] [ tomorrow ] [ in a week ]                │
│                                                              │
│ ╭──────────────────────────────────────────────────────────╮ │
│ │ Waits for you                                          3 │ │
│ │ 1 proposal from your sessions                            │ │
│ │ in the tab Proposals                                     │ │
│ │ Remember? Dana prefers tea                               │ │
│ │ [ keep ] [ drop ]                                        │ │
│ │ Review of the last curation run                          │ │
│ │ [ ok ] 1 fact changed: Dana                              │ │
│ │ The whole review is in the tab Review.                   │ │
│ ╰──────────────────────────────────────────────────────────╯ │
│ ╭──────────────────────────────────────────────────────────╮ │
│ │ Today                                                    │ │
│ │ due today Buy screws                                     │ │
│ │ overdue   Return the ladder                              │ │
│ ╰──────────────────────────────────────────────────────────╯ │
│ ╭──────────────────────────────────────────────────────────╮ │
│ │ This session                                             │ │
│ │ [ Northwind ] 3 facts, 1 current                         │ │
│ │ [ Acme Ltd ] 1 fact                                      │ │
│ │ This session started with all your facts.                │ │
│ │ m2b is on in this folder.                                │ │
│ │ /home/alex/code/lumen                                    │ │
│ │ [ turn off here ]                                        │ │
│ │ 1 note written in this session                           │ │
│ ╰──────────────────────────────────────────────────────────╯ │
│ ╭──────────────────────────────────────────────────────────╮ │
│ │ m2b                                                      │ │
│ │ 2 in inbox · curated 18:02                               │ │
│ │ Waiting for the next curation run: 1 proposal handed in  │ │
│ │ by a session, 1 answer of yours.                         │ │
│ │ [ curate now ]                                           │ │
│ ╰──────────────────────────────────────────────────────────╯ │
└──────────────────────────────────────────────────────────────┘
```

The parts stand in this order, what needs you first. The frame and title of **Waits for you** are
in the warning color while something waits, with the number that waits beside the title; a part
with nothing in it is one dim line, a count of none is not said, and in a pane narrower than 36
columns a bar down the left stands in for each frame. Where nothing waits and nothing is due,
**Waits for you** and **Today** are one dim line without a frame:
`Nothing waits for you, nothing due today.` A row is its text and, on the line below,
what you can press.

- **Waits for you** holds what the band counts: one row for the proposals from your sessions,
  every memory candidate, "Still current?" and "Still needed?" question with keep and drop, and the open review
  with `ok`. The tab `Proposals` turns the pane to
  [them](#the-proposals-from-your-sessions-in-the-pane), the tab `Review` to
  [the whole review](#the-whole-review-and-search-in-a-pane); the tab `Overview`, Escape or
  `/m2b-pane` turn it [back](#back-to-the-start-view). What m2b says to a press that wrote nothing,
  such as a candidate another session settled meanwhile, stands here in the error color.

  **Keep and drop are buttons: click them, or walk to them with Tab and press Enter.** Keep
  completes the task; drop marks it dropped and completes it; nothing else changes, and the next
  curation run reads which one you chose. When the run changed facts in the distillate, the
  review's row names them by what they are about (`2 facts changed: Sam, Dana`); `ok` closes the
  review task, and until then the review comes back after every run, so a changed fact is never
  missed. A review a run rewrote after it was drawn is not closed: m2b says so and shows the new
  one.

  A press writes nothing for 5 seconds. The row shows what it will do and offers `undo`:

  ```text
   Remember? Sam brings the plywood on Saturday
   [ undo ] dropping
   Still current? Planning the trip to Porto
   [ keep ] [ drop ]
  ```

  `undo` takes the press back, and the task stays as it was. After the 5 seconds m2b reads the
  list again and writes: an item another session settled meanwhile is left alone, and the part
  says so. Closing the session, or a crash, within those seconds writes nothing
  either, so a press is never half done; the item is simply still there next time. Until m2b has
  read the list after the write, the row offers nothing to press, for at most 3 minutes.
- **Today** lists your own tasks due today, then the overdue ones, the most recent first,
  whatever the band shows of them: `due today` in the warning color, `overdue` in the error
  color, each title at full strength. The tab `Tasks` lists
  [every open task](#all-your-open-tasks), with a mark `○` before each to tick it.
- **This session** says what m2b put into this session: each topic whose facts it got, at its
  start because the project path names it or before a prompt that named it, as a button that
  bears the topic's name and leads to [its lines](#a-topics-lines), with the facts lines and
  current items the topic held at that moment beside it; how the session started, in one
  sentence: `This session started with all your facts.`, `... with your facts, cut to fit.`, or
  `... without facts: the distillate is empty.`; whether m2b is on in the session's
  folder, with the button that [turns it off there](#turning-m2b-off-in-a-folder) or on again;
  and how many notes the session wrote through `/m2b-note` and the note tool. A note written with
  `m2b capture` in a shell is not counted. `/clear` and a compaction begin the list of topics
  again, as the context no longer holds what came before. A session this machine holds no note
  of, one that started under an earlier m2b or without m2b's hooks, is said to be not known,
  which does not say it was given nothing.
- **m2b** says how m2b itself stands. While all is well it is one dim line about curation:
  `curating` during a run, else how many notes wait in the inbox, where any do, and when m2b
  last curated, and `curation paused` where this machine starts no run by itself. What is wrong
  stands above it in the error color, each with its reason: a curation run that failed, a
  calendar m2b could not reach, an inbox it could not read. A session that still runs an older
  m2b than the installed one says so here and names `/reload-plugins`. Where an editing copy of a
  fact file on this machine differs from its fact file and you have not kept it
  ([What m2b knows](#what-m2b-knows)), a line says `1 edited copy not kept yet` in the color of
  what waits, above the line about curation, since `curate now` does nothing for it; it names no
  file, and you find the copy in its fact file's view. Below it stands each lesson
  you kept, as its sentence, and below that, dim, the day you kept it and how it does since, as
  `m2b status` counts it (`kept 20 Nov, not corrected again`); a lesson you corrected Claude on
  again says `corrected again 2 times: not working` in the color of what waits.

  On the machine that curates the store, the button `curate now` stands below the line about
  curation. A press writes nothing for five seconds: the row offers `undo` beside
  `starting a curation run`, as after keep and drop. Then the band runs
  `m2b curate --force --detach --json` once, which starts one curation run in the background,
  also while curation is [paused](curation.md#pausing). The part says `curating` at once and has
  no button while a run is under way, whoever started it; after the run the line names the new
  time and the button is there again. A press that started no run says why above the line about
  curation, in the error color, until your next press on the button or your next prompt:
  `No curation run started: a curation run is already running on this machine`, for one. On a
  machine that does not curate, the part has no button and says which machine does
  (`Curation runs on tower-1.`); where m2b cannot tell which machine curates, it has neither.
  The button says nothing of what a run costs ([Cost and privacy](cost-and-privacy.md)).

  Between the line about curation and the button, one sentence says what waits for the next run:
  the proposals sessions handed in, which the run takes in, and your answers to proposals, which
  it files, each only where it waits
  (`Waiting for the next curation run: 2 proposals handed in by sessions, 1 answer of yours.`).
  It stands there on every machine and not while a run is under way. Of what sessions handed in
  it says the number alone: they are no row of "Waits for you", since they wait for the run, not
  for you, and the band's row counts them apart, `1 handed in`
  ([What a session hands in](curation.md#what-a-session-hands-in)). Where m2b could not count
  them, the part says `m2b could not look at what sessions handed in.` in the error color.

What **This session** says is asked for each session by itself, with
`m2b band --json --session <id> --session-only`, which reads one small file on this machine and
no task list, and is told the session's project root: when the session starts, and once more five seconds later if m2b did not know the
session yet; three seconds after you send a prompt, so a topic that came in with it shows while
the turn still works; after a compaction; when a turn ends and when you type `/m2b-pane`. It is kept
in the session's own state and is not part of the answer the open sessions share. After `/clear`
the session goes on under a new id: the part says that m2b has not looked yet until, a second or
a few later, it has asked for the new one. When m2b could not look, the part says so with the reason;
with an installed m2b older than the band, which does not know the question, it says to update
m2b and to run `/reload-plugins`.

Where Claude Code cannot show a pane, `/m2b-pane` answers with the same lines as text, at most 20 of
them and without any character that draws nothing, and names `/m2b-proposals` and `/m2b-review`
where the pane names their tabs; the sentence about what waits for the next run is not among
them. It waits up to two seconds for a fresh answer about the session, and
without one the text says that m2b has not looked yet.

### A topic's lines

A topic's button turns the pane to that topic: its facts and its current items, read with
`m2b distillate topic` at the press. m2b keeps the names and counts of what it gave a session and
not the lines, so these are the lines the distillate holds now; a curation run since the session
got the topic may have changed them, and the view says so. A fact whose line names its fact file
is a row you press, ending in `›`, that opens the file as a fact in the tab `Facts` does, under a
tab beside the topic's; the topic's tab leads back to the lines as they were drawn, with the focus
on that fact. A current item is its words and since when it holds, and a row that opens the note
it rests on ([What m2b knows](#what-m2b-knows)). The topic stands under a seventh tab
that bears its name while the pane shows it; the tab `Overview`, Escape or `/m2b-pane` lead
[back](#back-to-the-start-view).

The lines are your facts, often about a customer. The band keeps them while the pane shows them
and drops them when you go back, close the pane, turn it to another view or type `/clear`. They
are not in the session's state, which other plugins can read; no command of the band answers with
them as text, they are written to no file, and nothing of them is handed to the model: where
Claude Code cannot show a pane, `/m2b-pane` lists the topics with their counts, as before. In a
shell, `m2b distillate topic <name>` prints them, as `m2b search` prints what it finds.
A topic the distillate no longer holds is said, and so is a distillate m2b could not read, with
the reason.

### Turning m2b off in a folder

The part "This session" says `m2b is on in this folder.` and names the session's folder: its
project root as Claude Code names it to the band, which a `cd` in a shell command does not move.
m2b's hooks decide by the project folder Claude Code names to them, which is this folder where a
session starts. The folder is shown whole and breaks only between its folders: a character that
would not draw, a line break or a space at its end is written out (`\x0a`, `\x20`), so the
folder you read is the folder the press turns off. `turn off here` is the answer to seeing one
customer's facts in a session that is about something else. A press waits five seconds with
`undo`, as keep and drop do, and then runs `m2b distillate off` for that folder: on this machine,
sessions that start there or below get no distillate, no routing rule and no topic facts. This
session keeps what its context already holds and gets no more topics, and the part says so.

Where m2b is off, the part says `m2b is off under this folder.` and names the folder it is off
under, which may lie above the session's; `turn on here` runs `m2b distillate on` for that
folder, with the same undo. When m2b could not write, the part says why until your next press or
prompt. With an installed m2b that does not name the session's folder there is no button to turn
m2b off: the band never guesses which folder a press would turn off.

### Every setting, in the pane

The tab `Settings`, or `/m2b-settings`, turns the pane to the settings of
m2b: every setting of this machine, of the store and of the owner, the ones `m2b settings` lists
([Configuration](configuration.md#every-setting-in-one-list)), in four parts by what you want
from m2b: **What m2b shows**, **What m2b reads**, **Curation** and **About this setup**.

![The pane beside the chat after /m2b-settings, under the tab Settings. The part "What m2b shows" holds "Where the band stands" with the values above, below and waiting, above marked as the one in force, "Tasks in the band" with off, count and list, list marked, and "Topics in the band" with on and off, off marked. The part "What m2b reads" begins with "Curation reads your sessions", on and off with off marked, where the lower edge of the picture ends. Below each title stands what the setting does](images/settings.png)

In the first three parts a setting is its title, below it what it does, and below that its values
side by side. The value in force is marked with `●` and is no button; every other value is a
button that sets it. The top of the view:

```text
┌──────────────────────────────────────────────────────────────┐
│ [ Overview ] [ Proposals ] [ Review ] [ Tasks ] [ Facts ]    │
│ [ Settings ]                                                 │
│                                                              │
│ ╭──────────────────────────────────────────────────────────╮ │
│ │ What m2b shows                                           │ │
│ │ Where the band stands                                    │ │
│ │ The band is m2b's row in a session, with the button that │ │
│ │ opens the pane: above keeps it above the prompt, also    │ │
│ │ while nothing waits; waiting draws it there only while   │ │
│ │ something waits or a task is due; below puts it at the   │ │
│ │ end of the hint line under the prompt and leaves the     │ │
│ │ space above free. Below the prompt no key reaches the    │ │
│ │ button and a mouse click only under the fullscreen       │ │
│ │ layout: /m2b-pane opens the pane. Not set, it is below   │ │
│ │ in a terminal and above in the desktop app, where        │ │
│ │ nothing draws the hint line's end; a value you set holds │ │
│ │ everywhere.                                              │ │
│ │ ● below in a terminal, else above [ above ] [ below ]    │ │
│ │ [ waiting ]                                              │ │
│ │                                                          │ │
│ │ Tasks in the band                                        │ │
│ │ Your tasks due today or overdue in the band: off shows   │ │
│ │ none there, count says how many, list names the first    │ │
│ │ three, which a band below the prompt counts as well. The │ │
│ │ pane lists them whatever this says.                      │ │
│ │ [ off ] ● count [ list ]                                 │ │
│ │                                                          │ │
│ │ Topics in the band                                       │ │
│ │ The band says how many topics m2b gave the session. The  │ │
│ │ pane names them whatever this says.                      │ │
│ │ [ on ] ● off                                             │ │
│ ╰──────────────────────────────────────────────────────────╯ │
└──────────────────────────────────────────────────────────────┘
```

A value the file holds that is none of the switch's own, such as a `curation.model` set with
`m2b config set`, stands first, marked. Two settings of these parts are no switch, the curating
machine and the folders m2b is left out of: each shows its value, marked, and below it the
command that changes it (`change: m2b curate take-over`).

**About this setup** is one row: the button `23 settings` and beside it `that only inform or are
changed by a command`. A press on it turns the view to that group alone, under a seventh tab that
bears its title: each setting as its title with its value, and below it what changes it, the
command, the setup skill, where it is edited by hand, or that m2b keeps it.

```text
 Store folder: /home/alex/Notes
   change: m2b config set store.path <folder>
 Kind of store: folder
   set up with /m2b:setup
 Store format: 3
   kept by m2b, never changed by hand
```

That view has no button below the tabs. The tab `Settings` leads back to the other settings, and
Escape to the overview.

With the keyboard in the pane, Tab moves the focus from button to button and Enter presses the
one that has it. The band never puts the focus on a value: Tab to it. After the press the focus
is on `undo`. After `undo`, and once the five seconds are over, it is on the nearest button that
sets nothing, the tab `Overview` above the first setting or the row of `About this setup` below
the last, so Enter pressed once more never sets a value. After a press on that row it is on the
tab `Settings`. Escape hands the keyboard back to the prompt.

![The pane beside the chat, driven with the keyboard. After /m2b-settings, fourteen Tabs put the focus on "sonnet" beside the marked "haiku" under "Model of curation"; Enter puts "undo" and "changing to sonnet" where the values stood, and Enter on "undo" takes the press back, with the focus on "23 settings", the row of "About this setup" below the settings. Five Shift+Tabs lead back to "sonnet"; pressed again and left alone, it is written after five seconds: the row reads "haiku" as a button and "sonnet" marked, and the focus is on "23 settings" again. Enter there opens the seventh tab "About this setup" with 23 settings that only inform or are changed by a command, the store folder, the kind of store and the machine's name among them, each with what changes it](images/pane-settings.gif)

<sub>One real Claude Code session on a demo machine with invented notes, recorded by `scripts/readme-demo --only pane-settings`. Only keys are typed and no model is asked; the five seconds a press waits run as recorded.</sub>

Ten settings are switches: `curation.read_sessions`, `curation.paused`,
`curation.run_after_answers`, `curation.git_commit`,
`band.place`, `band.due_tasks`, `band.topics`, `sessions.propose`, `curation.model` and your
`language`. Their
values are the buttons. A press on one writes nothing for five seconds: where the values stood
is `undo` and what the press does, as after keep and drop.

```text
 Topics in the band
 The band says how many topics m2b gave the session. The pane
 names them whatever this says.
 [ undo ] turning on
```

Then the band runs `m2b settings set` and reads the list again, so the view shows what is true
now. What the command refuses stands above the setting's values in its own words
(`not changed: …`) until your next press. One change at a time: while one waits or is written,
the values of every setting are text and no button. Leaving the values within the five seconds,
with a tab, the row of `About this setup` or Escape, takes the press back, and so does a command
that turns the pane. A change that is already being written goes on; its setting says what is
written, and the list is read again when it has ended. Every other setting is shown with the
command or the skill that changes it; this view has no field to type into and changes no path, no
program and no time limit.

`sessions.propose`, titled `Sessions hand in proposals`, is the one switch a session's shell
does not turn on: the command refuses where `CLAUDECODE` is set, as Claude Code sets it there. A
press on its `on` does turn it on. Where the pane is drawn in a terminal, in the desktop app or
in VS Code, `on` is a button, below a line that says so, and the press waits its five seconds
like every other; the band then runs the command with that variable empty, for this one press
and no other. In the mobile app, and on a surface the band does not know, `on` is text and no
button, and the line names the command for a terminal of your own. On every surface the setting
says that every machine sharing the store needs an m2b that knows handing in; where it is on,
`off` is a button, and a line says that a session gets the tool when it starts or its plugins
are reloaded. Nothing checks who made a press: what it rests on, and what it does not hold
against, is in [Security](../SECURITY.md#what-a-session-hands-in).

What m2b could not read (a store out of reach, no profile yet) stands above the parts, one line
per reason that names the file, and a setting of such a file says `not read` where its values
would stand. On a machine that does not curate, each part that shows a setting of the curation
run says that these do nothing here, and their titles are dimmed; `About this setup` says it
once it is opened. When the list cannot be read again after a change, the pane keeps the list it
had and says so above it.

The values hold folders, your name and what your store is called. The band keeps them for the
pane's drawing alone: they are not in the session's state, which other plugins can read, and
`/m2b-settings` answers one line without a value. It takes no value either, whatever follows its
name: a value changes by a press and in no other way. Where Claude Code cannot show a pane, the
command reads nothing and names `m2b settings`, which lists the settings in a terminal.

### It opens by itself beside the chat

Under the fullscreen layout Claude Code seats a pane beside the conversation. There the band opens
the m2b pane by itself, with its first drawing on the terminal in a session: in the start view,
without taking the keyboard, and Escape does not close it. After `/clear` it does so once more. Claude Code draws a pane nobody asked for only on a
terminal wide enough for it (from 144 columns, from 110 once you have opened the pane yourself);
below that the pane stays open undrawn and appears when you widen the terminal, and `/m2b-pane` or
`open` on the band's row shows it at once.

On the main screen, where a pane is a block above the prompt that takes rows from the
conversation, nothing opens by itself: `/m2b-pane` opens the pane there, as a dialog that Escape
closes. Nothing opens in a curation run, nor before m2b is set up, and only a terminal's drawing
opens the pane: in the desktop app and the other surfaces, `/m2b-pane` does.

Closing the pane beside the chat on its start view is kept on this machine: from then on it does
not open by itself, in this session or a later one, until you open it again with `/m2b-pane`, one of
the band's other commands or `open` in the band. Closing the block above the prompt keeps nothing.

### The band and the pane

The band is the same row wherever the pane is: it counts, the pane lists and answers. Beside a
docked pane, `open` gives the pane the keyboard.

What each way of running Claude Code gets, with the band's row where
[`band.place`](#where-it-stands) has it:

| Layout | The pane | The band |
|---|---|---|
| fullscreen, wide (from 144 columns, from 110 once you opened the pane) | beside the chat, opened by itself | its row |
| fullscreen, narrower | open and undrawn until the terminal is wider; `open` in the band or `/m2b-pane` shows it now | its row |
| the main screen, any width | only when asked, as a block above the prompt | its row |
| beside the chat but narrow (a body of 24 to 40 columns) | every line wraps, and below 36 columns a bar stands in for each frame; topics by name and count, a topic's lines after a press on its button | its row |
| the desktop app | as the app seats it; minimized to its small form, three counts and no button | its row |
| `claude -p`, no surface | none | none; `/m2b-pane` answers as text |

The small form says how many things wait for you, how many tasks are due today and overdue and
how many topics this session was given, or what m2b could not look at in place of a count. A
click may not reach it: `open` in the band shows the pane with its buttons.

### The tabs

One row of tabs stands above every view of the pane, always in this order: `Overview`, the view
the pane starts in; `Proposals`, with the number that wait; `Review`; `Tasks`; `Facts`; `Settings`. The tab of the
view you look at is drawn in the accent, and a press on it reads that view again, the open tasks
or the facts as they are now; every other turns the pane to its view. While the pane holds the
keyboard, each of the six has its first letter as its key: `o`, `p`, `r`, `t`, `f`, `s`. A letter
typed into a field of the pane is typed there and turns nothing; no other tab and no other
button has a letter. A topic's
lines, a fact's file, a note a current item rests on, the hits of a search and the settings of
`About this setup` stand under a seventh tab, which
is there only while the pane shows them. A note or a document a fact rests on stands under an
eighth, beside the seventh, which then bears the fact's file and leads back to it; a fact's file
opened from a topic's lines stands under an eighth too, beside the seventh, which then bears the
topic's name and leads back to its lines. A fact's file, while its view is shown, has a tab that is
a button in the accent, as the shown one of the six is: a press on it reads the file again, and
the band its counts, so you see what became of [its editing copy](#what-m2b-knows). Every other
tab beside the six, while its view is shown, is its name alone and no button. No view has a
button that leads back: the tabs are the one way from a view to another. `Tasks` and `Facts` have
no command of their own; their tabs open them. Where the pane is too narrow for the row, it breaks
between two tabs.

### All your open tasks

The tab `Tasks` shows every open task of your list, read with `m2b todos --json` the moment you
turn the pane to it, in groups by when each is due: `Overdue`, `Today`, `Next 7 days`, `Later`
and `Without a date`, a group with no task left out. Each row is the mark `○`, when the task is
due, in the color the part "Today" gives it (`overdue`, `due today`, otherwise the day,
`Thu 20 Nov`), and its title, on as many lines as the title takes. A press on the mark writes
nothing for five seconds and turns the row into `[ undo ] completing` with the title below, as
keep does; then, if the task is still open in your list, it is ticked, the tab reads the list
again and the band its counts. A task another session ticked or dropped in those seconds is left
alone, and the row says so. Where your task list
refuses, the row stays and says why. A task file m2b cannot read is named above the groups, under
`Not listed`, and the other tasks stand below it. The review, the memory candidates and the questions are not
here: they wait under "Waits for you" in the overview. The titles are held by the pane alone, for
as long as the tab is shown, and never in the session's state, which other plugins can read.

### What m2b knows

The tab `Facts` shows what m2b knows, read with `m2b distillate topics --json` the moment you
turn the pane to it, in two parts named by when a session gets them. **Every session starts
with** holds the facts outside any topic, each a row you press to open its fact file where its
line names one (it ends in `›`), and the current items, each as its words and since when it holds. **When a prompt names them** holds every topic as a button with its
counts (`2 facts, 1 current`); a press opens [its lines](#a-topics-lines) as the button in "This
session" does, with the focus on the tab `Facts`, which leads back.

Above the two parts stands a field `search`, also while the distillate is read and where it could
not be. Type what to look for and press Enter: the store is searched as
[`/m2b-search`](#the-whole-review-and-search-in-a-pane) searches it, with `searching…` below the
field meanwhile. Hits turn the pane to the search's view under the seventh tab `Search`, with the
focus on the tab `Facts`, which leads back to the field with your text as it was. No hit says
`no hits for <text>` below the field, a search m2b could not make says why in the error color, and
the pane stays on `Facts`. Until Enter, what you type is in no state another plugin reads; the
search's view then holds its words and hits as the view of `/m2b-search` does
([SECURITY.md](../SECURITY.md#what-you-type-into-the-pane)). A session that starts, and the
conversation after `/clear` or a resume, start with the field empty.

A press on a fact opens its file, read with `m2b source --json --viewer` at the press, under a tab
that bears the file's name without `.md`: its lines, the day it stops being true where it has one,
its earlier values, and **What it rests on**, the notes and documents behind it, each with its day,
what it is, a document's original file name and its first line. The first eight are listed, and a
line says how many more there are.

`correct` under the file's title opens a field `what is right`. Type how the fact should read and
press Enter: after the five seconds of `undo` the words go into the inbox as a correction of that
file (`m2b capture --about`), and the next curation run applies them to it. Until then the view
says that the correction waits, with your words, and on the machine that curates `curate now`
stands below them, which starts that run; on another machine the line names the machine whose run
it waits for, and nothing can be pressed. What m2b refused to keep goes back into the field with
`not kept:` and why, in the error color. What you typed stays in the field when you leave the
view, Escape included, and is there again when you open the same file; each fact file has a draft
of its own.

`edit` beside `correct` is for a fact a sentence cannot set right: it makes a copy of the fact file
with `m2b store edit` and opens it in the system's text editor, where the session has a screen
([m2b store edit](commands.md#the-stores-files)). You edit the copy, never the fact file: a
curation run alone writes `memory/`. The copy lies on this machine, outside the store, and the view
names its path below the buttons, the path alone where no editor opened, as in a session without a
screen. Save it in the editor, then press the tab of the fact's file, which reads the file again:

```text
 Dana
 [ correct ] [ edit ]
 your copy differs from the fact file
 /home/alex/.local/state/m2b/edits/dana.md
 [ keep the edit ] [ discard ]
 My sister. Birthday on 3 March. Would love a good
 fountain pen.
```

Until you save, the view says `an editing copy is open` with `discard`; once the copy differs,
`your copy differs from the fact file` with `keep the edit` and `discard`; where a curation run
changed the fact file since the copy was made, `the fact file changed since you opened the copy`
with `discard` alone, since keeping it would put your copy over that change. `keep the edit` and
`discard` wait five seconds with `undo`, as every press that writes. Kept, the copy goes into the
inbox as an edit of that file and is removed from this machine; the view says
`your edit waits for the next curation run`, with `curate now` on the machine that curates. That
run puts your text in place as the fact file, only while the file is still as the copy found it,
and brings its line in the distillate in step ([Correcting what a run filed](curation.md#correcting-what-a-run-filed)).
A copy that is empty is not kept and stays for `discard`. A press m2b refused, as while a curation
run is under way or for a fact file not downloaded, says why in the error color and makes no copy.
A copy you saved and did not keep is counted in the overview's part "m2b".

Each entry under **What it rests on** that m2b could read is a row you press, ending in `›` as a fact does. It turns the
pane to that note or document,
read with `m2b source --json --viewer`, under a tab beside the fact file's that bears a document's
or a picture's original file name, or else what it is and its day (`note 2026-10-12`). **What it
is** says what it is and when it was captured and holds the words as you captured them; **What
stands on which page** holds a document's outline, and **What the curation run added** the lines
the run wrote below your words. The tab of the fact's file leads back to the file as it was drawn,
with the focus on the row you pressed.

A current item leads to the notes it rests on, here and in a topic's lines. Where it rests on one
note, the item itself is a row you press, ending in `›`. Where it rests on several, a button for
each stands below it, in the order the distillate names them, bearing the day the note was
captured in your time zone (`17 Nov`, the year where it is not this one), and the time as well
where two fall on one day (`17 Nov 11:45`). An item that names no note has none. The note's file
name is not drawn in the line.

```text
 Current
 Alex builds the shed with Sam, the roof is next (since
 2026-11-17) ›
 The offer for Acme is out, an answer is due in December
 (since 2026-11-02)
 [ 2 Nov ] [ 17 Nov ]
 Sorting the old photos for the family album (since
 2026-11-10)
```

The press opens the note, document or picture in the same view under a seventh tab, which reads
`note` while m2b reads it and then what it is and its day, or a document's or a picture's
original file name. No fact file
stands above it: the tab `Facts` leads back, and from a topic's lines the tab the topic was
opened from.

A PDF or a picture has `open the file` in **What it is**, where a press would open it: the file is
on this machine and the session has a screen (on a Mac a session that does not run over SSH, on
Linux one with a display). The press runs `m2b store open`, which hands the file to the system's
viewer, with `open` on a Mac and `xdg-open` on Linux; the pane stays as it is and says
`Opened in the system’s viewer.`, or why m2b could not open it. Where the file does not open, the
view has no button and names where the file lies and why. A file of any other kind is never
started, since a viewer for it could run what it holds
([m2b store open](commands.md#the-stores-files)).

A fact's file, a note or a document that is not downloaded to this machine says so, with the
command that fetches it; an entry under **What it rests on** that is not on this machine, could
not be read or names no note of the archive says so and is no row to press. What these views show, your facts and your own words in a note, is held by the pane alone
while they are shown, never in the session's state, which other plugins can read: turning the pane
away from them or closing it drops it.

### Back to the start view

`/m2b-review`, `/m2b-search`, `/m2b-proposals`, `/m2b-settings`, a tab, a topic's button,
a fact's row, an evidence entry's row and a search from the field `search` turn the pane to their
view and give it the keyboard. Escape there, the pane's close
mark or the tab `Overview` lead back to the start view; the pane stays open. From
`About this setup` under its own tab they lead there too, and the tab `Settings` to the other
settings. Beside the chat it then stays
without closing on Escape, so an Escape at the empty prompt does not take it away, and an Escape
pressed twice within half a second leads back once and closes nothing. Above the prompt the pane
stays a dialog, and a later Escape closes the block.

With the keyboard in the pane, the band asks Claude Code to put the focus where a second Enter
writes nothing: after a press on a tab, on that tab, so the focus is the one mark in the row and
Enter pressed again reads the view again, and the view you left is its tab or its letter away;
after a press on a topic's button on `Overview` above its lines; after a fact's row or a topic's
button in the tab `Facts` on that tab; after an evidence entry's row on the tab of the fact's
file, and from there back on that row; after a fact's row in a topic's lines on the topic's tab,
and from there back on that row; after a current item's row or a note's button below it on the
tab `Facts`, or for an item in a topic's lines on the tab the topic was opened from; after a search
from the field `search` that found hits on the tab `Facts`; after `edit` on the tab of the fact's
file; after `correct` in the field `what is right`; after a day below the field `note` in that field; after keep, drop,
`ok`, a task's mark, `turn off here`, `curate now`, Enter in the field `note` or `what is right`,
`keep the edit` or `discard` on the row's `undo`. After `open the
file` it stays on that button, which writes nothing. Once an answer is written its row is gone,
and the focus stands on the row that moved up.

## The whole review, and search, in a pane

The band only counts. `/m2b-review`, or the tab `Review`, turns the m2b pane to the last
curation run in full, in two parts. **Last curation run** says how it went and when, in one line
(`succeeded, 18:00 to 18:02`; for a run before today its date), in the error color where it
failed, then what it changed: each changed fact gets two lines, what it is about with its fact
file, then the fact as it reads now, the added words in green and the removed ones in red and
struck through; below them where each copy of the facts from before a run lies, one for every run
the open review covers, and how many notes it filed, and every finding of the review task whole,
paths included. **Waits for you** holds the review with `ok` and every candidate and "Still
current?" question with keep and drop, which work as in the overview, undo included.

![The pane after /m2b-review, under the tab Review: the part "Last curation run" reads "succeeded" with its time, then the fact about Sam with the old day struck through in red and the new one in green, and where the facts from before the run lie; the part "Waits for you" begins below it. Under the pane the band is one row, "m2b 5 wait for you" with the button "open", and one task due today and one overdue below it](images/review.png)

As text, a review with more findings and a click within its undo:

```text
┌──────────────────────────────────────────────────────────────┐
│ [ Overview ] [ Proposals ] [ Review ] [ Tasks ] [ Facts ]    │
│ [ Settings ]                                                 │
│                                                              │
│ ╭──────────────────────────────────────────────────────────╮ │
│ │ Last curation run                                        │ │
│ │ succeeded, 18:00 to 18:02                                │ │
│ │ Sam (sam.md)                                             │ │
│ │   Sam Rivers (carpenter), neighbour, has a van           │ │
│ │ facts before the run; 2 notes filed:                     │ │
│ │ ~/.local/state/m2b/memory-before-run/20260314T170005Z    │ │
│ │   lint: broken link in people/sam.md                     │ │
│ │   ingest: eleven captures were not filed because their   │ │
│ │   photos are not downloaded; a copy of the run log is at │ │
│ │   ~/.local/state/m2b/runs/20260314T170200Z.jsonl         │ │
│ ╰──────────────────────────────────────────────────────────╯ │
│ ╭──────────────────────────────────────────────────────────╮ │
│ │ Waits for you                                          4 │ │
│ │ Review of the last curation run                          │ │
│ │ [ ok ] 1 fact changed: Sam                               │ │
│ │ Remember? Sam brings the plywood                         │ │
│ │ [ keep ] [ drop ]                                        │ │
│ │ Remember? Dana prefers tea                               │ │
│ │ [ undo ] dropping                                        │ │
│ │ Still current? Planning the trip to Porto                │ │
│ │ [ keep ] [ drop ]                                        │ │
│ ╰──────────────────────────────────────────────────────────╯ │
└──────────────────────────────────────────────────────────────┘
```

`/m2b-search <text>` shows the hits of `m2b search` in the same pane, under a tab of their own
and the search in words (`3 hits for plywood`), each with its file and line and the line itself
below it, without a model turn; a text that starts with a dash is searched as written.
A word also matches inside longer words, so `Velo` finds `Developer` too; `/m2b-search --word Velo`
matches whole words only. The hits come as `m2b search` orders them: from memory first, then the
archive, then the inbox, in both the newest note first.
Files not downloaded from iCloud Drive are counted below the hits. Both commands run at once, also
while a turn is working, and read through `m2b` only; these two views write nothing but keep, drop
and `ok`.
Where Claude Code cannot show a pane, for instance with no terminal attached, the command answers
with the content as text instead, its first 20 lines, each cut at 200 characters; that text stays
in the conversation the model reads. A search without hits answers in one line and opens no pane,
and one with more hits than `m2b` can hand over asks for a narrower search. The pane takes its data from the same refresh as the band, so it
follows the next curation run within a minute. It asks for the keyboard when it opens over an
empty prompt, so the arrows scroll a long review; Escape, the close mark and the tab `Overview`
lead [back to the start view](#back-to-the-start-view).

## The proposals from your sessions, in the pane

`/m2b-proposals`, or the tab `Proposals`, turns the m2b pane to what waits for your answer:
each proposal with its text, below it keep and drop with what kind of thing it is beside them
(with the due day of a commitment and the topic, where it has one), and then the words it was
taken from and their day: `said on` before words you
typed, `pasted on` before words from text you pasted into a prompt, which may be someone else's.
A lesson's proposal has three more lines: its kind, for what and, for a command, the words it fires
on and the kept lesson it would replace; where you said it in a second session too, the words you said there; and what
becomes of a file that already says it: `stated already in`, `adds to` or `fixes` that file.

![The pane after /m2b-proposals, under the tab Proposals 3: the part "Proposals from your sessions", framed in the warning color, with "keep all" and then each proposal as its text, keep and drop with its kind beside them, a due day for the commitment, and below them the words it was taken from with the day they were said. Under the pane the band is one row, "m2b 5 wait for you" with the button "open", and one task due today and one overdue below it](images/proposals.png)

As text, other proposals, one of them within its undo:

```text
┌──────────────────────────────────────────────────────────────┐
│ [ Overview ] [ Proposals 3 ] [ Review ] [ Tasks ] [ Facts ]  │
│ [ Settings ]                                                 │
│                                                              │
│ ╭──────────────────────────────────────────────────────────╮ │
│ │ Proposals from your sessions                           3 │ │
│ │ [ keep all ]                                             │ │
│ │ Dana is head of IT at Northwind.                         │ │
│ │ [ keep ] [ drop ] person, topic Northwind                │ │
│ │   said on 2026-03-04: "Dana runs IT at Northwind"        │ │
│ │ Call Sam about the ladder.                               │ │
│ │ [ undo ] dropping                                        │ │
│ │   said on 2026-03-04: "I still have to call Sam"         │ │
│ │ The spare key is in the shed.                            │ │
│ │ [ keep ] [ drop ] personal                               │ │
│ │   said on 2026-03-05: "the spare key is in the shed"     │ │
│ │ 1 answer waits for the next curation run, which files    │ │
│ │ what you kept                                            │ │
│ │ [ curate now ]                                           │ │
│ ╰──────────────────────────────────────────────────────────╯ │
└──────────────────────────────────────────────────────────────┘
```

Keep and drop work as on a candidate: a click writes nothing for 5 seconds and offers `undo`, then
the band runs `m2b proposals keep <id>` or `m2b proposals drop <id>`, which adds your answer to
the store. `keep all` keeps the proposals the pane showed when you clicked it, without those a
session handed in, which you keep or drop on their own, and without those you
clicked on their own; one a curation run added a moment before is not kept unseen. The count in
the band and the pane follow at once. A lesson proposed for one project has a third button, `keep for every project`, which runs
`m2b proposals keep --every-project <id>` once the 5 seconds are over.

Nothing is filed by the click: a curation run writes a capture for each proposal you kept and
files it. Once an answer is written and no proposal waits any more, with at least one keep among
the answers that wait, the band asks m2b for that run
(`m2b curate --detach --after-answers --json`), and the view says
`A curation run is under way: it files what you kept.` The store decides, so answers given in
other sessions and on other machines count like this one's. Drops alone start no run, a machine
you [paused](curation.md#pausing) starts none, and `curation.run_after_answers` set to `false`
turns the start off ([When it runs](curation.md#when-it-runs)). Such a run is a whole curation
run, with every step ([Cost and privacy](cost-and-privacy.md#what-a-run-costs)).

While answers wait and no run is under way, the last line says how many, and on the machine that
curates `curate now` stands below it, whatever the setting says: a round answered in part, a
paused machine and the setting turned off all leave answers waiting, and the press files them
now, as it does [in the overview](#this-session-what-waits-and-today-in-the-pane). A start that
began no run says why above the line (`No curation run started: …`). On a machine that does not
curate, the line names the machine whose run the answers wait for
(`1 answer waits for the next curation run on tower-1, which files what you kept`) and there is
no button.

![The pane beside the chat, driven with the keyboard. After /m2b-pane the overview, below its field "note", counts 3 proposals from your sessions; the letter p, the key of the tab "Proposals 3", turns the pane to them. Six Tabs reach "keep" of the first, "Send Dana the photos of the shed."; Enter puts "undo" and "keeping" where keep and drop stood, and Enter on "undo" brings them back. Kept again and left alone, the proposal is written after five seconds, the tab reads "Proposals 2", and below the two proposals left the view says "1 answer waits for the next curation run, which files what you kept" with the button "curate now". The letter o, the key of the tab "Overview", returns to the overview, which now counts 2 proposals and 4 things that wait, and the band left of the pane reads "4 wait for you"](images/pane-answers.gif)

<sub>One real Claude Code session on a demo machine with invented notes, recorded by `scripts/readme-demo --only pane-answers`. Only keys are typed and no model is asked; the five seconds a press waits run as recorded.</sub>

When `m2b` refuses an answer, because another machine answered that proposal the other way first,
or cannot write it, what it says stands in that view, in the error color, until your next press
there or your next prompt. After
`keep all`, where another answer already stands, it names the first such proposal by its text, and
what could be kept is kept. When the proposals
cannot be looked at, for instance because the answers folder is not downloaded from iCloud Drive,
the band and the pane say that in one line with the command that fetches it, and show no proposal: could not look
is never "nothing waits". For the same reason the pane says that m2b has not looked yet until the
band's first answer has arrived. Where Claude Code cannot show a pane, `/m2b-proposals` answers as
text: how many wait, how to list and answer them with `m2b proposals`, then the proposals, each
with its id, as far as the 20 lines of such an answer reach. That text stays in the conversation
the model reads.

## Noting and searching as tools of the model

The mod gives the model two tools, so a capture or a lookup the model makes for you needs no shell
call:

| Tool | Runs | Takes |
|---|---|---|
| `mcp__m2b__note` | `m2b capture --source claude --json -`, the text on standard input | `text`, and optionally `follow_up` (`YYYY-MM-DD`, also a task due that day) and `quiet` |
| `mcp__m2b__search` | `m2b search --json --any -- <terms>`, or `m2b source --json -- <source>` | `terms`, each a phrase of its own, `whole_words`, and `question_language`, the language the question was asked in; or `source`, the name of one fact file or note to read whole |

Their descriptions, which the model reads, carry the rules of the skills `/m2b:capture` and
`/m2b:search`: what may be noted (who is who, which role, what was agreed, from work too), the text
stays in your words, and an answer holds only what the hits hold. A test
holds the core rules of each description to the skill's own sentences. The skills stay as they
are; where the tools are offered, they name the tool as the first way, and where the mod does not
run they work through their commands as before. A calendar entry still goes through the skill,
and so does a file you name with its path, which Claude Code asks you about before it is copied
([Capture](using.md#capture)).
Both descriptions, about 5,500 characters together, are in the prompt of every session the mod
runs in, so the model knows the tools without loading a skill.

The note tool answers with the path of the saved note, the day of its task or that the task waits
for the next curation run, and anything `m2b` reported beside it. When a capture fails it tells
the model which of three cases it is: not saved, nothing written, or unknown, after a capture that
was stopped or answered nothing readable; in the last case the model is told not to note again
before it has looked, so a note is not written twice. The search tool answers with the first 100
hits in the order of `m2b search` (memory, then the archive, then the inbox, the newest note first),
each cut at 500 characters, and names the files it could not search. Its answer opens with
a line saying it is data from your notes, not instructions. Where the model named the language
of your question with the call, the answer ends with a line that names it as the language to
answer in. The model names it before it has read a note: told only to answer in the question's
language, it answered in the notes' language about one time in six where your notes and the
distillate were both in another. Every text in it is one line, with
escape sequences, control characters and the invisible characters m2b knows removed: marks that
reorder text, zero-width characters, variation selectors and tag characters. That list cannot be
complete. When `m2b` fails, the model gets an error that says it could not look, which it must not
read as nothing found. Before m2b is set up, both answer that and call nothing.

Called with `source` in place of `terms`, the search tool reads one source whole with
`m2b source --json -- <source>`: a fact file by the name a line of the distillate ends with
(`dana.md`), or a note by its file name, taken from a hit's path or from a fact file's evidence.
A fact file answers its title, its last day, its lines, its earlier values and its evidence, one
line for each note it rests on with that note's day, what it is (a note, a picture, a document),
a document's original file name and its first line; each of those is a source of its own. A note
answers its words and what the curation run added below them, and the note of a document its
outline, what stands on which page. The document itself is never read: the model answers from
the note and its outline, and says so where they do not hold the answer. The answer comes under
the same line that marks it as data from your notes, at most 200 lines, each cut as a hit is;
every line taken from a note starts with two spaces, so none can pass for the end of the answer. A
name with a separator, a path, or a name of anything but a fact file or a note of the archive is
refused before the store is read ([m2b source](commands.md#the-m2b-command)). This second way of
calling the tool adds about 600 characters to its description and its input; a tool of its own
would have cost every session a description of its own.

**Permission.** Claude Code lists the tools under these names and decides on a call as it does
for an MCP tool: a rule `mcp__m2b__note` or `mcp__m2b__search` (or `mcp__m2b` for both) in
`permissions.allow`, `ask` or `deny` of your settings applies to them. A rule you set for the
skill's command applies to the tool too: with `Bash(m2b capture:*)` in `permissions.ask` or
`deny`, the note tool asks or is refused the same way, and `Bash(m2b search:*)` does that for
search, `Bash(m2b source:*)` for reading a source. Where no such rule, no hook, setting or organization limit decides and Claude Code would
only ask because nothing allows the tool, the mod lets the call run, as the skills run their own
`m2b` commands without asking. For a note it does so only when the note is in your own words:
every word of it is in one prompt you submitted in this session, in any order ("remember that Sam
brings the plywood" and the note "Sam brings the plywood."). An addition of up to four words in
square brackets, as in "He [Sam] brings the plywood", does not have to be in the prompt, as long
as the additions together hold fewer words than the rest of the note has different ones. A note
with invisible format characters in it, other than the joiners emoji and some scripts need, is
never taken as yours. A prompt counts when you
typed it, sent it over Remote Control or started a headless run with it; a prompt from a plugin,
another session or a notification does not, and neither does one further back than the last 100
or text beyond the first 50,000 characters of a prompt. For any other note Claude Code asks as it
does for a tool nothing allows. This keeps text the model read somewhere, a web page for one, from
becoming a note nobody saw; it does not cover the `capture` skill's command, which runs without
asking for any text. To let every note run without asking, put `mcp__m2b__note` in
`permissions.allow`. A deny of the session's mode, such as `dontAsk`, stands; in plan
mode Claude Code keeps its own verdict; where an application embedding Claude Code answers the
asks itself, it still does.

Letting the call run also means that nothing else is asked about it: not the classifier of auto
mode, not a `PermissionRequest` hook of yours, and not a person. An organization that allows only
its managed rules (`allowManagedPermissionRulesOnly`) is not visible to the mod; such an
organization adds a managed `ask` or `deny` rule for these names. To be asked each time, put
`Bash(m2b capture:*)` in `permissions.ask`. To keep the model from noting at all, put both
`mcp__m2b__note` and `Bash(m2b capture:*)` in `permissions.deny`: the first refuses the tool, the
second the skill's command, which the model would otherwise use instead.

## Handing in a proposal, a tool you turn on

With `sessions.propose` set to `true` in the machine config
([Configuration](configuration.md#configjson-this-machine)), the mod gives the model a third tool:

| Tool | Runs | Takes |
|---|---|---|
| `mcp__m2b__propose` | `m2b proposals add -`, one JSON object on standard input | `kind` (`person`, `agreement`, `commitment` or `personal`), `text`, the fact as one sentence, `quote`, the words of the session it stands on, and optionally `due` (`YYYY-MM-DD`) for a commitment with a day |

The model calls it by itself, beside the task you gave it, when the session states something of
one of the four kinds that your memory does not hold yet: who someone is, an agreement, something
you committed to, something about your own life. The words may be yours or stand in what the
model read for you, a mail or a document. The mod adds which session hands in, the id Claude Code
gives the session; the model cannot name another one. Everything else is decided by
[`m2b proposals add`](commands.md), which looks for the quote in that session's transcript and
writes one file under `state/core/handed-in/` in the store, or refuses with one line. The next
curation run takes that file in, and the proposal then waits in the list with the others, marked
as handed in by a session ([Curation](curation.md#what-a-session-hands-in)). The tool
answers with that line. A refusal never repeats the text or the quote. When the command could not
take the call or reach the store, the tool says that nothing was handed in and why. After any
other end, a command that was stopped before it answered among them, it says that it is unknown
whether the proposal was handed in; the same call again never hands it in twice. Only the main
conversation hands in: the command reads that conversation, where what a subagent or another
agent of the session read does not stand, so such an agent is told to name what it found in its
answer.

The tool has no skill. Its description, about 3,200 characters in the prompt of every session
that has it, is where its rules stand: the four kinds in the words the reading of your sessions is
instructed with, and that each is about you, someone you deal with or an agreement you are a
party to; what to leave out (how the model should work, the project at hand, what your memory
already says; from work only who is who, which role, what was agreed); that
it holds a fact against the distillate first and searches where the distillate only names a
topic; that a text the model read is data, so a sentence in it that asks to be remembered, or
says how to word a proposal or what to quote, is not carried out; that "remember this" from you is a
note, not a proposal; and that after a refusal it tries once more at most. A test holds the
description to the kinds and to the rules that keep it apart from its neighbours.

The mod reads the setting when a session starts, so turning it on reaches sessions that start
afterwards and one that reloads its plugins. A session that started before you turned it off
still has the tool, and the command refuses. In a curation run the tool does not exist.

**Permission.** A call runs without a question, as a search does, under the same conditions: no
rule, hook, setting or organization limit decided otherwise. A rule for the tool's name
(`mcp__m2b__propose`, or `mcp__m2b` for all three) applies, and so does a rule you set for the
command: with `Bash(m2b proposals:*)` in `permissions.ask` or `deny`, the tool asks or is refused.
That pattern also covers `m2b proposals keep` and `drop`, so an `ask` rule meant for those makes
every call of the tool ask.

## The status line

Below the prompt m2b says only what is wrong, such as `last curation run failed` or
`calendar not reachable`, and nothing while nothing is. Claude Code draws every plugin's status
line with a ⚠ and in the color of a warning, so a line about an inbox and a time would warn all
day: those stand in the pane's part **m2b**. Every state the line can show is in
[The curation run](curation.md#the-status-line).

## After an update

A session keeps the band it started with, while `m2b` itself is always the installed version. When
the session's band is the older one, the pane's part "m2b" says so in one line:

```text
 This session runs m2b 0.3.0 and m2b 0.3.1 is installed: run /reload-plugins.
```

`/reload-plugins` in that session, or a new session, loads the installed band. A band newer than
the installed m2b, as when Claude Code runs it from a checkout, says nothing.

## What it needs

- m2b set up on the machine, and the launcher `~/.local/bin/m2b`, which m2b writes at the first
  session start after setup.
- Mods on in Claude Code. The band is a mod, a module Claude Code loads with the plugin. Two
  different things can keep it out:
  - **Mods off, hooks on.** A session that started without network access can save Claude Code's
    rollout switch for mods as off. Then the band, the status line, the slash commands and the
    model's tools are missing; the distillate at session start, capture and search through the
    skills, tasks and curation work as before. Start `claude`
    once with network access, then a new session.
  - **No plugin hooks at all.** Under `claude --bare`, or with `allowManagedHooksOnly` or
    `disableAllHooks` in managed settings, Claude Code runs none of m2b's hooks: no band, and no
    distillate at session start either. Capture, search and tasks still work through the skills,
    and curation runs where it is scheduled.
- With Apple Reminders, access to Reminders for the terminal Claude Code runs in, or the band shows
  one error line instead of the tasks.

`m2b doctor` tells the two apart. m2b's own session-start hook and the band each note when a
session started them, and the line `band` compares the two: `seen` when the latest session ran the
band, `not seen` with the first case when that session ran m2b's hooks but not the band, `not seen`
with the second case when no session has run m2b's hooks since setup. Right after setup it can say
`not seen` until the next session starts.

## What it reads and writes

It runs only while `~/.config/m2b/config.json` and the launcher exist. At a session's start it
reads that file for one key, `sessions.propose`. Each refresh is one `m2b`
call, `m2b band --json`; keep and drop call `m2b tasks complete` and `m2b tasks drop`, after
reading the list again with `m2b band --json --tasks-only`; keep and drop on a proposal call
`m2b proposals keep` and `m2b proposals drop`, which refuse an answer themselves where another
one stands. `turn off here` and `turn on here` in the pane call `m2b distillate off` and
`m2b distillate on` with the folder, which change `distillate.skip_under` in the machine config.
`curate now` calls `m2b curate --force --detach --json`, which starts a curation run in the
background; once an answer to a proposal is written and none waits any more, the band calls
`m2b curate --detach --after-answers --json`, which starts one only where a kept proposal waits
for a run. What that run reads and writes is in [The curation run](curation.md).
A topic's button calls `m2b distillate topic --json`, which reads `memory/MEMORY.md`, and so does
`m2b distillate topics --json` for the tab `Facts`. A fact's row, an evidence entry's row and a current item's way to its note
call `m2b source --json`,
which reads one fact file in `memory/` or one note in `corpus/`, and `open the file` calls
`m2b store open`, which starts the system's viewer on a PDF or a picture of the archive. In a
fact's file, `correct` calls `m2b capture --about` with the fact file's name, `edit` calls
`m2b store edit`, which writes the editing copy into `~/.local/state/m2b/edits/` and starts the
system's text editor on it, and `keep the edit` and `discard` call it with `--keep` and
`--discard`. The field `note` calls `m2b capture`, with `--follow-up` for its day, and the field
`search` calls `m2b search --json`. The tab
`Tasks` reads your task list with `m2b todos --json`, and a task's mark calls `m2b tasks complete` after
reading the list again. The
settings are read with `m2b settings --json`, and a press on a value calls `m2b settings set`,
which writes the machine config or, for your language, `profile.json` in the store. Every open session asks about once a
minute and after each of your turns, so the answer is shared between sessions for 55 seconds in
`~/.local/state/m2b/band-answer.json`; an answer of a shape the band does not know, or stamped later
than now, is not used. An answer of a session that could not read the tasks stays with that session:
it is not shared, and one that lies there is not used, since another session may reach the task list,
for one where an app starts Claude Code without the access to Reminders your terminal has.
However many turns end while `m2b` is slow, at most one more refresh waits.
That folder holds titles, findings and the proposals with the words they stand on, so m2b keeps it readable by
you only. At each session start
it writes `~/.local/state/m2b/band-seen.json`, which `m2b doctor` reads. That you closed the pane
beside the chat by hand is one value, `paneClosedByHand`, in the store Claude Code keeps for the
plugin under its own configuration folder. Apart from keep, drop, `ok` and a task's mark, which
change that one task in your task list (with the `markdown` backend, its file in `tasks/` of the
store) or add your answer to a proposal as an empty file in `state/core/proposal-answers/`, a
note, a correction or a kept edit, each a new capture in `inbox/`, and a press on a value of
`Language` in the settings, it writes nothing in the store.

`m2b band --json` reaches and reads the task list once (with Apple Reminders, two calls to
`reminders`) and sorts the open tasks by their marker, adds the answer of `m2b proposals --json`,
and adds the answer of `m2b status --json`, reusing that one look at the task list for its check
of the backends. With invented tasks:

```json
{
  "version": "0.3.0",
  "band": {"place": null, "due_tasks": "count", "topics": false},
  "tasks": {
    "candidates": [{"id": "c1", "title": "Remember? Sam brings the plywood", "notes": "m2b:candidate", "due": null, "completed": false, "completed_at": null, "dropped": false, "marker": "candidate"}],
    "questions": [],
    "reviews": [],
    "due_by_today": [{"id": "t7", "title": "Call Dana", "notes": "", "due": "2026-03-14", "completed": false, "completed_at": null, "dropped": false, "marker": null, "overdue": false}]
  },
  "proposals": {
    "proposals": [{"id": "0c1d2e3f4a5b", "kind": "person", "text": "Dana is head of IT at Northwind.", "quote": "Dana runs IT at Northwind", "day": "2026-03-04", "topic": "Northwind", "due": null, "source": "typed", "tool": null, "by": null}],
    "answered": 0,
    "handed_in": 0
  },
  "status": {"machine_id": "alex-laptop", "curating_machine": "alex-laptop", "this_machine_curates": true, "inbox": {"count": 2, "evicted": 0}, "run": {"state": "succeeded", "last_succeeded_at": "2026-03-14T21:36:00+01:00"}, "backends": {"store": {"state": "reachable", "detail": ""}, "tasks": {"state": "reachable", "detail": ""}, "calendar": {"state": "not configured", "detail": ""}}},
  "edits_not_kept": 0
}
```

`version` is the installed core's, which the band compares with its own. `band` is the section
of that name in the machine config: where the band stands, how it shows your tasks due and
whether it counts the session's topics. `tasks.due_by_today` names your own tasks due today or
overdue, the earliest first, whatever the band shows of them; with `band.due_tasks` set to `list`, `tasks.due` names
them too. `status` holds more
fields than shown, as `m2b status --json` does; `curating_machine` and `this_machine_curates`
say which machine curates the store and whether it is this one, the machine on which the pane's
part "m2b" has `curate now`. When the task list cannot be
read, `tasks` is `{"error": "<why>"}` and `status` still answers. The checks of the backends are
kept for five minutes, so at most every five minutes the answer waits for the calendar too, here
for at most 10 seconds whatever `calendar.timeout_seconds` says; a calendar that does not answer
by then is reported as not reachable. `edits_not_kept` counts the editing copies of fact files on
this machine that differ from what they were made from (`m2b store edit`), read from this
machine's state folder alone, a number and never a file's name. `--tasks-only` answers `tasks` alone.

`proposals` lists what a reading of your sessions proposed or a session handed in and still waits for your answer (one
without an answer for 14 days no longer does), the earliest said first, in `answered` how many answers wait for the next curation run, and in `handed_in` how many proposals sessions handed in wait for a run to take them in (`null` where their folder could not be listed), their number alone. Each
names where its words stand in `source` (`typed`, `pasted`, `tool` for a tool's result or `agent` for an
answer of Claude), the tool in `tool` where it is a tool's result, and in `by` who proposed: `session`
for one a session handed in, null for one a reading found. When
that cannot be looked at (the proposals file or the answers folder is not downloaded, a newer m2b
wrote the proposals file, the store is out of reach), `proposals` is `{"error": "<why>"}` and the
other parts still answer. An entry of the proposals file that is not in the form, or holds half a
character, is left out.

With `--session <id>` the answer has one more part, `session`: what m2b gave the session with that
id, as this machine noted it when it gave it.

```json
"session": {
  "id": "0a1b2c3d-1111-4222-8333-444455556666",
  "known": true,
  "topics": [{"name": "Northwind", "facts": 3, "current": 1}],
  "distillate": {"at_start": "whole", "off_under": null, "folder": "/home/alex/code/lumen"}
}
```

`topics` are the topics whose facts the session got since its last start, at that start because
the project path names them or before a prompt that named them, each with the facts lines and
current items its block held at that moment; a curation run that changed the topic since does not
change the numbers. `/clear` and a compaction are a start too: the context no longer holds what
came before, so the list begins again, as it does for the topics that come in once per session.
`distillate.at_start` says how that start printed the distillate: `whole`, `cut` to fit the
start, `none` where there was none to read, and `null` where the start noted nothing of it.
`distillate.off_under` is the folder the distillate is turned off under (`m2b distillate off`),
as it is now, for the folder Claude Code names as the project or else the one the command runs
in; a session that got topics before it was turned off still holds them. `distillate.folder` is
that folder, with its links followed: the band hands it to `m2b distillate off`, so the button in
the pane turns off the folder this answer is about. A session this machine
holds no note of (the note is removed once it was not written for seven days, an m2b before these
notes wrote none, and neither does a session without m2b's hooks) is `"known": false` with no
topics, which does not say it was given nothing; a topic noted by an earlier m2b comes with
`null` for its numbers. A value that is not 1 to 128 letters, digits and dashes is answered with
`"session": {"error": "not a session id"}`, and a folder that cannot be looked at with an error
of its own; the other parts still answer. The notes are kept on this machine under
`~/.local/state/m2b/topics/`, one small file per session.

With `--session-only` beside `--session`, the answer is `version` and `session` alone, and the
command reaches no task list, no calendar and no store: the band asks it for every session by
itself, while the rest of the answer is one the open sessions share. Without `--session`, and
together with `--tasks-only`, it is refused.

While a review task is open, `tasks.review` names the changes of the facts the last runs made, as
the curation run kept them for the review: per change its `kind` (`rewrote`, `removed`,
`file_removed`, `file_emptied`), the fact `file`, a short `topic`, the statement `before` and
`after`, and `parts`, the statement word by word, each `same`, `added` or `removed`; `copies` names
each copy of `memory/` from before a run and the notes filed with it; `paragraphs` are the
review's paragraphs these stand for, which the band leaves out of the findings it draws. Only
changes whose paragraph the open review task still holds are named, so a review another machine's
run rewrote is never drawn with this machine's older changes.

## Where it lives

In `plugins/m2b/hooks/`: `register.tsx` and its helpers, loaded through `"modules"` in
`hooks/hooks.json`. Its tests are in `plugins/m2b/tests/band/` and run with
`scripts/check --quick band`.

## How you see it runs

A session the band runs in shows it once m2b has answered: at the end of the hint line below the
prompt in a terminal, as a row above the prompt in the desktop app, unless
[`band.place`](#where-it-stands) says otherwise. With `above`, the row stands above the prompt
everywhere. While all is well and nothing waits, the row is
`m2b` and `open` alone and the status line is empty: no candidate, no question, no proposal, no
open review, no task due to show and, with `band.topics` on, no topic given to the session. With
`band.place` set to `waiting` there is no row then, and with `below` the hint line below the
prompt ends in `m2b` and the way into the pane. `/m2b-pane` opens the pane whenever the band runs, and `m2b doctor`
says in its line `band` whether the latest session ran it. When m2b cannot answer, or the band's own refresh fails, the status line says
`could not look` instead of an old state.
