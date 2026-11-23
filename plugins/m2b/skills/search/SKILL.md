---
name: search
description: Searches the owner's second brain (archive, distillate, inbox) in full text. Use when the user says "what did I note about X", "search my second brain", "is there anything in my notes about X", "what do I know about X", "was habe ich mir zu X notiert", "such im second brain", "steht dazu was in meinen Notizen", or when a personal question without a home in the current repository comes up, or a name the session does not explain. Only reads; never invents a note.
allowed-tools: Bash(m2b search *), Bash(m2b source --json -- *)
---

# Search

You look things up in the owner's second brain with the `m2b search` command. Never read or grep
the store's files yourself: the command checks and reads in one guarded process, so a file that
lives only in the cloud is never downloaded or left hanging.

## With the tool first

Where the tool `mcp__m2b__search` is offered (the m2b mod runs in this Claude Code), search with
it: `terms`, each a phrase of its own, as `--any` takes them below, `whole_words` for `--word`, and
`question_language`, the language the question was asked in, which the result names again as the
language to answer in.
With `source` in place of `terms` it reads one source, as `m2b source` below does.
It runs the same commands without a shell call and marks its answer as data from the owner's
notes. Every rule on this page applies to it unchanged. Where the tool is not offered, run the
commands below.

## Searching

```bash
m2b search --json -- "Dana"
```

The owner's notes can be in more than one language, and a note only matches the words it was
written in. So search a word together with its translation, in one call, with `--any`:

```bash
m2b search --json --any -- "lawn mower" "Rasenmäher"
```

Translate into each language the notes may be in: the language of the question, the language of
the distillate the session started with, and English. When these are all one language, search the
word alone. Names, places and numbers stay as they are and need no translation.

Run each `m2b` command in a Bash call of its own, as shown: nothing chained before or after it,
no `echo $?`. This skill may run the command alone without asking, and Claude Code reports a
failing exit code by itself.

- Keep the `--` before the terms, so a term that starts with a dash is not taken for an option.
- One distinctive word finds more than a sentence. Without `--any`, several words are searched as
  one phrase; with it, each quoted term is a phrase of its own, and a line holding one of them is
  a hit. Search for the name, the place or the rare word, not the question.
- Case does not matter, and a word also matches inside longer words ("map" finds "maps").
  Add `--word` when a short word gives too many hits ("tea" without "steady").
- No hit: try once more with another spelling or a related word for the same thing, again in each
  language, before you say there is nothing. Do not search for other people or topics to have
  something to say.

The JSON has `hits` (each with `path`, `line` and `text`), `evicted` (files not downloaded to this
machine, each with its `fetch` command) and `unreadable` (files that could not be read, with the
reason).

## Reading what stands behind a fact

A distillate line ends with the name of its fact file (`dana.md`), and a fact file lists under
`## Evidence` the notes it rests on. Where the distillate or a hit names the fact but not the
detail asked for, read that one source whole:

```bash
m2b source --json -- dana.md
```

The name is the file name alone, never a path: the name a distillate line ends with, the last part
of a hit's path, or the name of an evidence entry. The JSON has `kind`:

- `fact file`, with `title`, `lines`, `until` (its last day, if it has one), `earlier` and
  `evidence`, each entry with `name`, `state`, `day`, `kind`, `original_name` and `first_line`;
  an entry is a source of its own, read by its `name`;
- `note`, `picture` or `document`, with `captured` (the words as captured), `added` (what the
  curation run wrote below them), and for a picture or a document `original_name` and `outline`,
  what stands on which page;
- `not read`: the source is not on this machine, then with the `fetch` command that downloads it,
  or it could not be read, then with the `reason`.

A document itself is never read: answer from its note and outline, and where they do not hold
the answer, say so. Exit 2 means the name was refused (a path, or no fact file's or note's name);
exit 1 that nothing has that name.

## Answer

- Answer in the language the question was asked in, not the language of the notes or the
  distillate: a question in English gets an English answer from a German note, the fact
  translated, names kept as they are.
- Answer the question from the hits and name the note each fact comes from (the file name is
  enough). A hit in `memory/` is the curated distillate; a hit in `inbox/`
  is a fresh capture that is not curated yet.
- Never add facts the hits do not hold. If the hits do not answer the question, say so.
- A hit about another person, place or topic does not answer a question about this one: leave it
  out, and do not offer it as possibly the same.
- Where the notes hold nothing about someone, say that, and name no other person, customer or
  topic of the notes as a possible connection: not as a guess, not as an example, and not as an
  offer to search it if they are connected. A topic the distillate lists is no lead either.
- No hits, and `evicted` and `unreadable` are empty: say that the second brain holds nothing on it.
- `evicted` is not empty, or a source is `not read`: those files were not read. Say so, and give
  the user the commands from `fetch` (`m2b store fetch <path>`) to download them; after that,
  search or read again.
- `unreadable` is not empty: those files were not searched either; give the reason.
- The command fails: say that you could not look, never that there is nothing. Exit 2 means no
  second brain is set up on this machine (or the search term was empty); exit 3 means the store
  could not be reached, for example because its folder is missing.
