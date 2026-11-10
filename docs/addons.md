# Add-ons

m2b is one plugin with two add-ons in it: `band` and `worklog`. Each is off
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
| [band](addons/band.md) | memory candidates, "Still current?" questions and the review above the prompt, and a status line | every machine where it is on | in each session, about once a minute and after each of your turns |
| [worklog](addons/worklog.md) | a daily worklog with time spans per sphere of work and booking proposals | the curating machine only | records in herdr all the time; writes once a day, in the curation run before the inbox is filed |

Each page says what the add-on does and needs, how to set it up and turn it off, what it reads and
writes on the machine and in the store, its commands, and how you see that it runs.

## Add-ons that were removed

m2b 0.2.0 had two more add-ons. Both were removed in 0.3.0:

- `herdr` listed the other agent sessions open in herdr at session start. It never read or wrote
  the store, so it did not belong in a second brain; herdr shows those sessions itself.
- `backup` kept a local mirror of the store after each curation run. It had no way back and could
  miss files iCloud Drive had not downloaded, so it is gone until a backup with a way back replaces
  it. The folder it wrote is left as it was. Until then, keep the store safe with Time Machine or a
  copy of the store folder.

A `config.json` that still names either loads as before, and the entry is ignored. To remove it:

```bash
m2b addons off herdr
m2b addons off backup
```
