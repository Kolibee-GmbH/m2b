# The band

The band is where m2b speaks to you inside Claude Code: a few rows above the prompt and one line
below it. It is part of m2b and needs no setup of its own; it starts once m2b is set up on the
machine.

```text
 [ keep ] [ drop ] Remember? Sam brings the plywood on Saturday
 [ keep ] [ drop ] Still current? Planning the trip to Porto
 [ ok ] m2b: review  1 fact changed: Sam
   lint: broken link in people/sam.md
   the whole review: /m2b-review
╭──────────────────────────────────────────────────────────────╮
│ >                                                            │
╰──────────────────────────────────────────────────────────────╯
 ⚠ m2b: 2 in inbox · curated 21:36
```

## What it shows

- **Memory candidates**, "Remember? ...": facts proposed for the distillate with
  `m2b tasks add --candidate`.
- **"Still current?" questions**: items under "Current" in the distillate that have gone quiet.
- **The review**: the open review task of the last curation run. When the run changed facts in
  the distillate, one row names them by what they are about (`2 facts changed: Sam, Dana`); the
  other findings follow as written. `ok` closes the review task, with the same 5 seconds and
  `undo` as keep; until then the review comes back after every run, so a changed fact is never
  missed. A review a run rewrote after the band drew it is not closed: the band says so and shows
  the new one.
- **Proposals from your sessions**: while a curation run's reading of your sessions has proposed
  something you have not answered ([curation](curation.md#reading-your-sessions)), one row says
  how many, `3 proposals from your sessions`, however many there are. `show` on it opens them in
  the m2b pane, where you keep or drop each ([below](#the-proposals-from-your-sessions-in-the-pane)).
- **Tasks due today or overdue**: your own tasks, not the curator's, in at most three quiet rows
  below the candidates (`due today: Call Dana`, `overdue: Return the drill`), without buttons;
  today's first, then the overdue ones, the most recent first. They stand there while
  `band.due_tasks` is `list` on this machine: `m2b settings set band.due_tasks list` turns them
  on, `count` and `off` leave these rows out.

Candidates and questions share at most three rows, the due tasks have three, and the review shows
at most three findings, each followed by "and N more" when there are more; the proposals are one
row, between the candidates and the due tasks: what asks for keep or drop stands together, above
what only tells. The band is empty, and
takes no room, while there is nothing to show.

While the m2b pane sits beside the chat, which holds the same rows, the band steps back to one
line, and where the pane is not in view it has one row more, for what this session was given:
[the band beside the pane](#the-band-beside-the-pane).

**Keep and drop are buttons: click them with the mouse.** Keep completes the task; drop marks it
dropped and completes it; nothing else changes, and the next curation run reads which one you
chose.

A click writes nothing for 5 seconds. The row shows what it will do and offers `undo`:

```text
 [ undo ] dropping: Remember? Sam brings the plywood on Saturday
 [ keep ] [ drop ] Still current? Planning the trip to Porto
```

`undo` takes the click back, and the task stays as it was. After the 5 seconds the band reads the
list again and writes: an item another session settled meanwhile is left alone, and the band says
so in one line. Closing the session, or a crash, within those seconds writes nothing either, so a
click is never half done; the item is simply still there next time. The click is written also when
the row has left the band meanwhile, pushed below the first three or replaced by an error line.
Until the band has read the list after the write, the row offers nothing to click, for at most
3 minutes.

The band draws every text as one plain line: escape sequences and control characters a capture
brought along from terminal output are left out, line breaks and tabs become spaces. The texts of
a proposal are the exception: there each such character is written out (`\x1b`, `\u202e`) instead
of left out, and so is every other character a terminal draws with no width (zero-width
characters, soft hyphens, variation selectors, tag characters), because keep keeps the text as it
is stored, and a part the pane left out would be kept unseen.

## When a curation run fails

Each open session shows one line for a few seconds, once per failed run: `m2b: the curation run of
2026-03-14 18:00 failed; its review task says why, and /m2b-review shows it`. A reload of the
plugins does not show the same run again; a run that succeeds shows nothing, and neither does an
interrupted one, which the status line names. The status line says
`last run failed, see review` until the next run succeeds.

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
request. To note with the model's help, for instance with a follow-up date, ask the model: it uses
the tool below, or the skill `/m2b:capture` where the mod does not run.

## This session, what waits and today, in the pane

`/m2b-pane` opens the m2b pane in the view it starts in, with three parts. (`/m2b` alone is not
this command: Claude Code runs the skill `/m2b:m2b` for it, which asks the model what m2b is.)

![A Claude Code session in the fullscreen layout after /m2b-pane: the m2b pane sits beside the chat in its start view. In this session: the topic Northwind with 2 facts and 1 current item and "show", the distillate printed whole at the start, and "leave m2b out" of the project folder. Waits for you: 3 proposals from your sessions with "show", a "Still current?" question with keep and drop, the review row "1 fact changed: Sam" with ok, and "show" for the whole review. Today: one task due today and one overdue. Below them "settings". Left of the pane the band above the prompt is one line that counts what waits, and the status line stands below the prompt](images/pane.png)

As text, another session:

```text
┌──────────────────────────────────────────────────────────────┐
│ In this session                                              │
│ [ show ] Northwind: 3 facts, 1 current                       │
│ [ show ] Acme Ltd: 1 fact                                    │
│ The distillate was printed whole at the start.               │
│ [ leave m2b out ] of /home/alex/code/lumen                   │
│ 1 note written in this session                               │
│ Waits for you                                                │
│ [ show ] 1 proposal from your sessions                       │
│ [ keep ] [ drop ] Remember? Dana prefers tea                 │
│ [ ok ] m2b: review                                           │
│ [ show ] the whole review                                    │
│ Today                                                        │
│ due today: Buy screws                                        │
│ overdue: Return the ladder                                   │
│ [ settings ]                                                 │
└──────────────────────────────────────────────────────────────┘
```

- **In this session** says what m2b put into this session: each topic whose facts it got, at its
  start because the project path names it or before a prompt that named it, with the facts lines
  and current items the topic held at that moment, and `show` for
  [its lines](#a-topics-lines); how the start printed the distillate (whole,
  cut to fit, or none because there was none to read); the folder the distillate is turned off
  under, where it is, and the button that
  [leaves m2b out of the session's folder](#leaving-m2b-out-of-a-folder) or turns it on again; and
  how many notes the session wrote through
  `/m2b-note` and the note tool. A note written with `m2b capture` in a shell is not counted.
  `/clear` and a compaction begin the list of topics again, as the context no longer holds what
  came before. A session this machine holds no note of, one that started under an earlier m2b or
  without m2b's hooks, is said to be not known, which does not say it was given nothing.
- **Waits for you** holds what the band holds, without its limit of three rows: one row for the
  proposals from your sessions, every memory candidate and "Still current?" question with keep
  and drop, and the open review with `ok`. They work as in the band, undo included. `show` on the
  proposals turns the pane to [them](#the-proposals-from-your-sessions-in-the-pane), `show` under
  the review to [the whole review](#the-whole-review-and-search-in-a-pane); `back` above that view,
  Escape or `/m2b-pane` turn it [back](#back-to-the-start-view).
- **Today** lists your own tasks due today, then the overdue ones, the most recent first, while
  `band.due_tasks` is `list`; otherwise it says that tasks due are not shown.

The first part is asked for each session by itself, with
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
where the pane has `show`. It waits up to two seconds for a fresh answer about the session, and
without one the text says that m2b has not looked yet.

### A topic's lines

`show` beside a topic turns the pane to that topic: its facts and its current items, read with
`m2b distillate topic` at the press. m2b keeps the names and counts of what it gave a session and
not the lines, so these are the lines the distillate holds now; a curation run since the session
got the topic may have changed them, and the view says so. `back`, Escape or `/m2b-pane` lead
[back](#back-to-the-start-view).

The lines are your facts, often about a customer. The band keeps them while the pane shows them
and drops them when you go back, close the pane, turn it to another view or type `/clear`. They
are not in the session's state, which other plugins can read; no command of the band answers with
them as text, they are written to no file, and nothing of them is handed to the model: where
Claude Code cannot show a pane, `/m2b-pane` lists the topics with their counts, as before. In a
shell, `m2b distillate topic <name>` prints them, as `m2b search` prints what it finds.
A topic the distillate no longer holds is said, and so is a distillate m2b could not read, with
the reason.

### Leaving m2b out of a folder

Below what the session was given stands `leave m2b out` with the session's folder: its project
root as Claude Code names it to the band, which a `cd` in a shell command does not move. m2b's
hooks decide by the project folder Claude Code names to them, which is this folder where a session
starts. The folder is shown whole: a character that would not draw, a line break or a space at its
end is written out (`\x0a`, `\x20`), so the folder you read is the folder the press turns off. It is the answer to seeing one
customer's facts in a session that is about something else. A press waits five seconds with
`undo`, as keep and drop do, and then runs `m2b distillate off` for that folder: on this machine,
sessions that start there or below get no distillate, no routing rule and no topic facts. This
session keeps what its context already holds and gets no more topics, and the part says so.

Where the distillate is off, the button is `turn on` beside the folder it is off under, which may
lie above the session's; it runs `m2b distillate on` for that folder, with the same undo. When
m2b could not write, the part says why until your next press or prompt. With an installed m2b
that does not name the session's folder there is no button to leave m2b out: the band never
guesses which folder a press would turn off.

### Every setting, in the pane

`settings` at the end of the start view, or `/m2b-settings`, turns the pane to the settings of
m2b: every setting of this machine, of the store and of the owner, as `m2b settings` lists them
([Configuration](configuration.md#every-setting-in-one-list)), each a row with its title and its
value.

![The pane beside the chat after /m2b-settings: "back", then every setting as a row with "open", its title and its value, 19 under "This machine", 6 under "The store, for every machine" and 6 under "The owner, for every machine", among them the machine's name, the store folder, the model of curation and whether sessions hand in proposals; left of the pane the band draws all its rows](images/settings.png)

`open` on a row turns the pane to the setting's card:

```text
┌──────────────────────────────────────────────────────────────┐
│ Settings · 15 of 31                                          │
│ [ previous ] [ next ] [ list ]                               │
│ Curation paused                                              │
│ this machine · curation.paused                               │
│ now: off                                                     │
│ This machine starts no curation run by itself, none at a     │
│ session start and none from a schedule. m2b curate --force   │
│ still runs one, and captures keep reaching the inbox.        │
│ [ turn on ]                                                  │
└──────────────────────────────────────────────────────────────┘
```

`previous` and `next` walk through every setting in the order of the list, so starting at the
first card takes you through all of them once; `list` returns to the list, and Escape does the
same from a card and leads on to the start view from the list. Escape pressed twice within half a
second on a card stops at the list. A card says what the setting does and its default where the
value differs from it. In a pane narrower than 41 columns a row of the list is the title with the
value below it, and `list` stands below `previous` and `next`.

With the keyboard in the pane, Tab moves the focus from button to button and Enter presses the
one that has it. The band asks Claude Code to put the focus where the walk goes on: on `next`
when a card is opened from the list or reached with `next` (on the last card on `previous`), on
`previous` when you walk back (on the first card on `next`), and on the row of the card you left
when `list` returns to the list. So Enter on `next`, pressed again and again, takes you through
every setting. The band never puts the focus on a switch: Tab to it. After the press the focus
is on `undo`, and after `undo`, or once the five seconds are over, on the button that leads on
(`next`, on the last card `previous`). Escape hands the keyboard back to the prompt.

![The pane beside the chat, driven with the keyboard. After /m2b-settings, Tab twice puts the focus on the first row and Enter opens its card, "Settings · 1 of 31"; Enter on "next", eight times, walks card by card to "Model of curation", which reads "now: haiku". Tab twice reaches "set to sonnet"; Enter turns it into "undo setting curation.model to sonnet", and Enter on "undo" takes the press back. Reached with Tab twice again, pressed and left alone, it is written after five seconds: the card reads "now: sonnet", "default: haiku" and offers "set to haiku". Tab and Enter on "list" return to the list, whose row now reads "Model of curation: sonnet"](images/settings-walk.gif)

<sub>One real Claude Code session on a demo machine with invented notes, recorded by `scripts/readme-demo --only settings-walk`. Only keys are typed and no model is asked; the five seconds a press waits run as recorded.</sub>

Eight settings are switches: `curation.read_sessions`, `curation.paused`, `curation.git_commit`,
`band.due_tasks`, `band.topics`, `sessions.propose`, `curation.model` and your `language`. Their cards offer the
other values to press (`turn on`, `turn off`, `set to sonnet`). A press writes nothing for five
seconds and offers `undo`, as keep and drop do; then the band runs `m2b settings set` and reads
the list again, so the card shows what is true now. What the command refuses stands on the card
in its own words. One change at a time: while one waits or is written, no other card offers a
switch. Leaving the card within the five seconds, with `previous`, `next`, `list` or Escape,
takes the press back, as leaving the settings does. A change that is already being written goes
on; the list says which one is under way, and reads again when it has ended. Every other setting
is shown with the command or the skill that changes it; the pane has no field to type into and
changes no path, no program and no time limit.

`sessions.propose` is the one switch a session's shell does not turn on: the command refuses
where `CLAUDECODE` is set, as Claude Code sets it there. A press on its card does turn it on.
Where the pane is drawn in a terminal, in the desktop app or in VS Code, the card offers
`turn on`, below a line that says so, and the press waits its five seconds like every other; the
band then runs the command with that variable empty, for this one press and no other. In the
mobile app, and on a surface the band does not know, the card names the command for a terminal
of your own and offers nothing that turns it on. On every surface the card says that every
machine sharing the store needs an m2b that knows handing in, and it offers `turn off` where the
setting is on, beside a line that a session gets the tool when it starts or its plugins are
reloaded. Nothing checks who made a press: what it rests on, and what it does not hold against,
is in
[Security](../SECURITY.md#what-a-session-hands-in).

A setting of a file that could not be read (a store out of reach, no profile yet) is listed as
`not read` with the reason. On a machine that does not curate, the settings of the curation run
are dimmed and say that they do nothing here. When the list cannot be read again after a change,
the pane keeps the list it had and says so above it.

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
`show` on the band's row for this session shows it at once.

On the main screen, where a pane is a block above the prompt that takes rows from the
conversation, nothing opens by itself: `/m2b-pane` opens the pane there, as a dialog that Escape
closes. Nothing opens in a curation run, nor before m2b is set up, and only a terminal's drawing
opens the pane: in the desktop app and the other surfaces, `/m2b-pane` does.

Closing the pane beside the chat on its start view is kept on this machine: from then on it does
not open by itself, in this session or a later one, until you open it again with `/m2b-pane`, one of
the band's other commands or `show` in the band. Closing the block above the prompt keeps nothing.

### The band beside the pane

The pane's start view holds every row of the band with its buttons. So while the pane sits beside
the chat in that view and is the pane shown there, the band above the prompt draws one line at
most:

```text
 Waits for you: 2 to keep or drop, 1 proposal from your sessions, the review
```

The line is the first there is of: why a press wrote nothing, which the start view does not show;
that this session runs an older band than the installed m2b; an error reading the tasks or the
proposals; and else the counts of what needs an answer, candidates and questions together, then
the proposals, then the open review. The tasks due need no answer and stand in the pane. With
none of these the band draws nothing.

The pane's other views hold only some of the rows. While it is turned to the review, a search,
the proposals or a topic, the band draws its rows as on its own, until `back` or Escape lead to
the start view again.

Where the pane is not in view, the band draws what it draws on its own, and one row more while
this session was given at least one topic:

```text
 [ keep ] [ drop ] Remember? Dana prefers tea
 [ show ] 2 topics given to this session
```

`show` opens the pane in its start view. That is your own open, so Claude Code places the pane at
any width: under the fullscreen layout from 110 columns beside the chat, where it stays, and
elsewhere as a dialog that Escape closes, on a terminal the block above the prompt. A session
that was given no topic, that m2b holds no note of or has not looked at yet has no such row;
`/m2b-pane` says which it is. Where no pane can be shown, or Claude Code refuses to open one, the
band says so and names `/m2b-pane`, which answers with the lines.

What each way of running Claude Code gets:

| Layout | The pane | The band |
|---|---|---|
| fullscreen, wide (from 144 columns, from 110 once you opened the pane) | beside the chat, opened by itself | one line at most; every row while the pane is turned to another view |
| fullscreen, narrower | open and undrawn until the terminal is wider; `show` in the band or `/m2b-pane` shows it now | every row, and the row for this session |
| the main screen, any width | only when asked, as a block above the prompt | every row, and the row for this session; while the block shows, without that row |
| beside the chat but narrow (a body of 24 to 40 columns) | every line wraps; topics by name and count, a topic's lines after `show` | one line at most |
| the desktop app | as the app seats it; minimized to its small form, three counts and no button | one line at most beside the docked pane, every row beside the small form |
| `claude -p`, no surface | none | none; `/m2b-pane` answers as text |

The small form says how many topics this session was given, how many things wait for you and how
many tasks are due today and overdue, or what m2b could not look at in place of a count. A click
may not reach it, so keep, drop and `ok` stay in the band there.

The band knows where the pane sits from the pane's own last drawing on the same surface, and asks
Claude Code whether the pane is still open, drawn and the one shown. Whenever that is not certain
(the pane closed, Claude Code says it is not drawn, another plugin's pane is the tab in front),
the band draws every row. It is drawn again at once when the pane is first drawn in a seat, moves
to another, turns to another view or closes; what else changes, such as another plugin's pane
coming in front, it sees with its own next drawing. Claude Code says whether the pane is drawn and
shown for the session as a whole: with a terminal and the desktop app on one session, the band of
one can go by the pane of the other.

### Back to the start view

`/m2b-review`, `/m2b-search`, `/m2b-proposals`, `/m2b-settings` and `show` or `settings` in the
start view turn the pane to their view and give it the keyboard. Escape there, the pane's close
mark or the `back` button above the view lead back to the start view; the pane stays open. From
the card of a setting they lead to the list of the settings first. Beside the chat it then stays
without closing on Escape, so an Escape at the empty prompt does not take it away, and an Escape
pressed twice within half a second leads back once and closes nothing. Above the prompt the pane
stays a dialog, and a later Escape closes the block.

With the keyboard in the pane, the band asks Claude Code to put the focus where a second Enter
writes nothing: on `back` after `show` or `settings` turned the pane, and after `back` on the
button that led there (on `settings` where that button is gone, as after the last proposal was
answered). Outside the settings the band moves no focus within a view: after keep it is on
`undo`.

## The whole review, and search, in a pane

The band keeps to a few rows. `/m2b-review` opens the m2b pane beside the conversation with the
last curation run in full: its state and times, every finding of the review task whole, paths
included, and every candidate and "Still current?" question with keep and drop, which work as in
the band, undo included. Each changed fact gets two lines: what it is about with its fact file,
then the fact as it reads now, the added words in green and the removed ones in red and struck
through; below them where each copy of the facts from before a run lies, one for every run the
open review covers, and how many notes it filed.

![The pane after /m2b-review: the last curation run with its times, the review row "1 fact changed: Sam", the fact about Sam with the old day struck through in red and the new one in green, where the facts from before the run lie, and a "Still current?" question with keep and drop; below the pane the band with its rows and the status line](images/review.png)

As text, a review with more findings and a click within its undo:

```text
┌──────────────────────────────────────────────────────────────┐
│ Last curation run: succeeded, 2026-03-14 18:00 to 18:02      │
│ [ ok ] m2b: review  1 fact changed: Sam                      │
│   Sam (sam.md)                                               │
│     Sam Rivers (carpenter), neighbour, has a van             │
│   facts before the run: ~/.local/state/m2b/memory-before-run/│
│ 20260314T170005Z; 2 notes filed                              │
│   lint: broken link in people/sam.md                         │
│   ingest: eleven captures were not filed because their photos│
│ are not downloaded; a copy of the run log is at ~/.local/stat│
│ e/m2b/runs/20260314T170200Z.jsonl                            │
│ [ keep ] [ drop ] Remember? Sam brings the plywood           │
│ [ undo ] dropping: Remember? Dana prefers tea                │
│ [ keep ] [ drop ] Still current? Planning the trip to Porto  │
└──────────────────────────────────────────────────────────────┘
```

`/m2b-search <text>` shows the hits of `m2b search` in the same pane, each with its file and line
and the line itself, without a model turn; a text that starts with a dash is searched as written.
A word also matches inside longer words, so `Velo` finds `Developer` too; `/m2b-search --word Velo`
matches whole words only. The hits come as `m2b search` orders them: from memory first, then the
archive, then the inbox, in both the newest note first.
Files not downloaded from iCloud Drive are counted below the hits. Both commands run at once, also
while a turn is working, and read through `m2b` only; the pane writes nothing but keep and drop.
Where Claude Code cannot show a pane, for instance with no terminal attached, the command answers
with the content as text instead, its first 20 lines, each cut at 200 characters; that text stays
in the conversation the model reads. A search without hits answers in one line and opens no pane,
and one with more hits than `m2b` can hand over asks for a narrower search. The pane takes its data from the same refresh as the band, so it
follows the next curation run within a minute. It asks for the keyboard when it opens over an
empty prompt, so the arrows scroll a long review; Escape, the close mark and `back` above the view
lead [back to the start view](#back-to-the-start-view).

## The proposals from your sessions, in the pane

`/m2b-proposals`, or `show` on the band's row, opens the m2b pane with what waits for your answer:
each proposal with its text, what kind of thing it is (with the due day of a commitment and the
topic, where it has one), the words it was taken from and their day: `said on` before words you
typed, `pasted on` before words from text you pasted into a prompt, which may be someone else's.

![The pane after /m2b-proposals: three proposals from the sessions, each with keep and drop, its kind, a due day for the commitment, and the words it was taken from with the day they were said; above them "back" and "keep all"; below the pane the band with its rows and the status line](images/proposals.png)

As text, other proposals, one of them within its undo:

```text
┌──────────────────────────────────────────────────────────────┐
│ 3 proposals from your sessions                               │
│ [ keep all ]                                                 │
│ [ keep ] [ drop ] Dana is head of IT at Northwind.           │
│   person, topic Northwind                                    │
│   said on 2026-03-04: "Dana runs IT at Northwind"            │
│ [ undo ] dropping: Call Sam about the ladder.                │
│   commitment, due 2026-03-06                                 │
│   said on 2026-03-04: "I still have to call Sam"             │
│ [ keep ] [ drop ] The spare key is in the shed.              │
│   personal                                                   │
│   said on 2026-03-05: "the spare key is in the shed"         │
│ 1 answer waits for the next curation run, which files what   │
│ you kept                                                     │
└──────────────────────────────────────────────────────────────┘
```

Keep and drop work as on a candidate: a click writes nothing for 5 seconds and offers `undo`, then
the band runs `m2b proposals keep <id>` or `m2b proposals drop <id>`, which adds your answer to
the store. `keep all` keeps the proposals the pane showed when you clicked it, without those a
session handed in, which you keep or drop on their own, and without those you
clicked on their own; one a curation run added a moment before is not kept unseen. Nothing is
filed by the click: the next curation run writes a capture for each proposal you kept and files
it, and the last line says how many answers wait for it. The row in the band and the pane follow
at once.

![The pane beside the chat, driven with the keyboard. After /m2b-pane the start view counts 3 proposals from your sessions; Tab to their "show" and Enter turn the pane to them, with the focus on "back". Tab twice reaches "keep" of the first, "Send Dana the photos of the shed."; Enter turns the row into "undo keeping: Send Dana the photos of the shed.", and Enter on "undo" brings keep and drop back. Kept again and left alone, the proposal is written after five seconds: the pane counts 2 proposals and says that 1 answer waits for the next curation run, and the band left of it counts 2 as well. Shift+Tab twice and Enter on "back" return to the start view, which now counts 2 proposals](images/pane-answers.gif)

<sub>One real Claude Code session on a demo machine with invented notes, recorded by `scripts/readme-demo --only pane-answers`. Only keys are typed and no model is asked; the five seconds a press waits run as recorded.</sub>

When `m2b` refuses an answer, because another machine answered that proposal the other way first,
or cannot write it, what it says stands in the pane and in the band until your next prompt. After
`keep all`, where another answer already stands, it names the first such proposal by its text, and
what could be kept is kept. When the proposals
cannot be looked at, for instance because the answers folder is not downloaded from iCloud Drive,
both say that in one line with the command that fetches it, and show no proposal: could not look
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
| `mcp__m2b__search` | `m2b search --json --any -- <terms>` | `terms`, each a phrase of its own, `whole_words`, and `question_language`, the language the question was asked in |

Their descriptions, which the model reads, carry the rules of the skills `/m2b:capture` and
`/m2b:search`: what may be noted (never documents of customers or confidential statements about
third parties), the text stays in your words, and an answer holds only what the hits hold. A test
holds the core rules of each description to the skill's own sentences. The skills stay as they
are; where the tools are offered, they name the tool as the first way, and where the mod does not
run they work through their commands as before. A calendar entry still goes through the skill.
Both descriptions, about 5,000 characters together, are in the prompt of every session the mod
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

**Permission.** Claude Code lists the tools under these names and decides on a call as it does
for an MCP tool: a rule `mcp__m2b__note` or `mcp__m2b__search` (or `mcp__m2b` for both) in
`permissions.allow`, `ask` or `deny` of your settings applies to them. A rule you set for the
skill's command applies to the tool too: with `Bash(m2b capture:*)` in `permissions.ask` or
`deny`, the note tool asks or is refused the same way, and `Bash(m2b search:*)` does that for
search. Where no such rule, no hook, setting or organization limit decides and Claude Code would
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
already says, never documents of customers or confidential statements about third parties); that
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

Below the prompt, one line sums up the brain, such as `2 in inbox · curated 21:36`: the captures
waiting for the next run, and when the last successful run ended. Claude Code puts the plugin's
name and a ⚠ in front of every plugin's status line; the ⚠ is not a warning (Claude Code 2.1.322
offers plugins no way to leave it out). Every state the line can show is in
[The curation run](curation.md#the-status-line).

## After an update

A session keeps the band it started with, while `m2b` itself is always the installed version. When
the session's band is the older one, it says so in one line:

```text
 this session runs the band of m2b 0.3.0 while m2b 0.3.1 is installed: run /reload-plugins
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
one stands. `leave m2b out` and `turn on` in the pane call `m2b distillate off` and
`m2b distillate on` with the folder, which change `distillate.skip_under` in the machine config;
`show` beside a topic calls `m2b distillate topic --json`, which reads `memory/MEMORY.md`. Every open session asks about once a
minute and after each of your turns, so the answer is shared between sessions for 55 seconds in
`~/.local/state/m2b/band-view.json`; an answer of a shape the band does not know, or stamped later
than now, is not used. However many turns end while `m2b` is slow, at most one more refresh waits.
That folder holds titles, findings and the proposals with the words they stand on, so m2b keeps it readable by
you only. At each session start
it writes `~/.local/state/m2b/band-seen.json`, which `m2b doctor` reads. That you closed the pane
beside the chat by hand is one value, `paneClosedByHand`, in the store Claude Code keeps for the
plugin under its own configuration folder. Apart from keep and drop, which
change that one task in your task list (with the `markdown` backend, its file in `tasks/` of the
store) or add your answer to a proposal as an empty file in `state/core/proposal-answers/`, it
writes nothing in the store.

`m2b band --json` reaches and reads the task list once (with Apple Reminders, two calls to
`reminders`) and sorts the open tasks by their marker, adds the answer of `m2b proposals --json`,
and adds the answer of `m2b status --json`, reusing that one look at the task list for its check
of the backends. With invented tasks:

```json
{
  "version": "0.3.0",
  "tasks": {
    "candidates": [{"id": "c1", "title": "Remember? Sam brings the plywood", "notes": "m2b:candidate", "due": null, "completed": false, "completed_at": null, "dropped": false, "marker": "candidate"}],
    "questions": [],
    "reviews": []
  },
  "proposals": {
    "proposals": [{"id": "0c1d2e3f4a5b", "kind": "person", "text": "Dana is head of IT at Northwind.", "quote": "Dana runs IT at Northwind", "day": "2026-03-04", "topic": "Northwind", "due": null, "source": "typed", "tool": null, "by": null}],
    "answered": 0
  },
  "status": {"machine_id": "alex-laptop", "inbox": {"count": 2, "evicted": 0}, "run": {"state": "succeeded", "last_succeeded_at": "2026-03-14T21:36:00+01:00"}, "backends": {"store": {"state": "reachable", "detail": ""}, "tasks": {"state": "reachable", "detail": ""}, "calendar": {"state": "not configured", "detail": ""}}}
}
```

`version` is the installed core's, which the band compares with its own. `status` holds more
fields than shown, as `m2b status --json` does. When the task list cannot be
read, `tasks` is `{"error": "<why>"}` and `status` still answers. The checks of the backends are
kept for five minutes, so at most every five minutes the answer waits for the calendar too, here
for at most 10 seconds whatever `calendar.timeout_seconds` says; a calendar that does not answer
by then is reported as not reachable. `--tasks-only` leaves `proposals` and `status` out.

`proposals` lists what a reading of your sessions proposed or a session handed in and still waits for your answer (one
without an answer for 14 days no longer does), the earliest said first, and in `answered` how many answers wait for the next curation run. Each
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

The status line under the prompt. When m2b cannot answer, or the band's own refresh fails, it says
`could not look` instead of an old state. An empty band is normal while there is no candidate, no
question and no open review.
