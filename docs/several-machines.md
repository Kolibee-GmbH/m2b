# Several machines

One store can serve several machines, for example a desktop and a laptop that both see the same
folder in iCloud Drive. Every machine captures, searches and lists tasks. **One machine curates**:
`store.json` names it, and only it files the inbox, so two runs never edit the same file.

| | Every machine | The curating machine only |
|---|---|---|
| capture, search, todos, rediscover | yes | |
| the distillate at session start | yes | |
| curation runs (at session start or scheduled) | | yes |
| the worklog's step in the curation run | | yes |
| worklog recording in herdr | | yes |

## Joining a store

On the second machine:

1. Add the marketplace and install the plugin, as in [Getting started](getting-started.md#in-claude-code),
   and wait until the store's folder is there.
2. Run `/m2b:m2b setup` and point it at the same folder. Setup sees `store.json`, `profile.json` and
   `memory/`, downloads what it needs, and joins: it asks only what the store does not answer
   already and changes nothing in it.
3. Answer that this machine does not curate.

The machine gets its own `~/.config/m2b/config.json` and launcher. The task list comes from
`store.json`, so both machines use the same one.

## Moving curation

To make this machine the curating one, for example when the old one is retired:

```bash
m2b curate take-over
```

It writes this machine into `store.json`. It refuses while the run record says the other machine
is running a curation and that run is not past its time limit, so two machines never curate at
once. Every run checks `store.json` first, so the other machine's next run stops before it
changes anything; its worklog recording turns off at its next session start. Add-ons are
turned on per machine: run their setups (such as `/m2b:worklog-setup`) again on the new
curating machine; `take-over` lists the add-ons that were on in the last run.

## When the curating machine is away

The session start on every machine prints one line when the curating machine has not run for more
than three days. Captures keep landing in the inbox meanwhile; nothing is lost, they are filed
when a run happens.

## Machines on different versions

Update the curating machine first. A machine whose m2b knows an older store format than the store
has reads the store and captures into it, but refuses to curate it and says to update m2b; its
`m2b doctor` names the format as the problem. The curating machine, once updated, migrates the
store at the start of its next run.
