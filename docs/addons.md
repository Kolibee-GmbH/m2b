# Add-ons

m2b is one plugin with four add-ons in it: `band`, `backup`, `herdr` and `worklog`. Each is off
until its own setup skill turns it on, and an add-on that is off runs no curation step, prints
nothing at session start and draws nothing. Which ones are on is kept per machine, in
`~/.config/m2b/config.json`:

```bash
m2b addons list
m2b addons on backup
m2b addons off backup
```

Turning an add-on off keeps its settings, so its setup skill turns it on again with what was set
before. An add-on reaches the core only through the `m2b` command, the way an
[integration](integrations.md) does, and keeps what it needs to remember in the store under
`state/addons/<add-on>/`.

| Add-on | What it adds | Runs on | When |
|---|---|---|---|
| [band](addons/band.md) | memory candidates, "Still current?" questions and the review above the prompt, and a status line | every machine where it is on | in each session, about once a minute and after each of your turns |
| [backup](addons/backup.md) | a local snapshot of the store and the task list | the curating machine | after each curation run, as its last step |
| [herdr](addons/herdr.md) | the other agent sessions open in herdr, at session start | every machine where it is on, in sessions started in a herdr pane | at session start |
| [worklog](addons/worklog.md) | a daily worklog with time spans per sphere of work and booking proposals | the curating machine only | records in herdr all the time; writes once a day, in the curation run before the inbox is filed |

Each page says what the add-on does and needs, how to set it up and turn it off, what it reads and
writes on the machine and in the store, its commands, and how you see that it runs.
