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

m2b is one plugin, so the worklog is installed with it whether you use it or not. A worklog you
never turn on costs three things. Its files sit in the plugin's folder: its package and command,
the herdr recorder, two schemas and two skills. Claude Code lists those two skills,
`worklog-setup` and `worklog-verdict`, with their descriptions in every session, as it does for
every skill of the plugin. And one command runs at each session start, `m2b-worklog hook
session-start`: it asks the core whether the worklog is on, which reads this machine's
`config.json`, and ends without printing or writing anything. The core needs none of it: the
repository's check runs the core's tests against a copy of the plugin without the worklog's parts
([Contributing](../CONTRIBUTING.md#checks)).

Turning an add-on off keeps its settings, so its setup skill turns it on again with what was set
before. An add-on reaches the core only through the `m2b` command, the way an
[integration](integrations.md) does, and keeps what it needs to remember in the store under
`state/addons/<add-on>/`.

| Add-on | What it adds | Runs on | When |
|---|---|---|---|
| [worklog](addons/worklog.md) | a daily worklog with time spans per sphere of work and booking proposals; needs [herdr](https://herdr.dev) 0.9 or later | the curating machine only | records in herdr all the time; writes once a day, in the curation run before the inbox is filed |

Its page says what the add-on does and needs, how to set it up and turn it off, what it reads and
writes on the machine and in the store, its commands, and how you see that it runs.
