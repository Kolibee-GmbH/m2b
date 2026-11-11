# Add-ons

m2b is one plugin with one add-on in it: `worklog`. It is off
until its own setup skill turns it on, and an add-on that is off runs no curation step, prints
nothing at session start and draws nothing. Which ones are on is kept per machine, in
`~/.config/m2b/config.json`:

```bash
m2b addons list
m2b addons on worklog
m2b addons off worklog
```

Turning an add-on off keeps its settings, so its setup skill turns it on again with what was set
before. An add-on reaches the core only through the `m2b` command, the way an
[integration](integrations.md) does, and keeps what it needs to remember in the store under
`state/addons/<add-on>/`.

| Add-on | What it adds | Runs on | When |
|---|---|---|---|
| [worklog](addons/worklog.md) | a daily worklog with time spans per sphere of work and booking proposals; needs [herdr](https://herdr.dev) 0.9 or later | the curating machine only | records in herdr all the time; writes once a day, in the curation run before the inbox is filed |

Its page says what the add-on does and needs, how to set it up and turn it off, what it reads and
writes on the machine and in the store, its commands, and how you see that it runs.
