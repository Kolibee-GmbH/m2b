# Writing a backend

m2b talks to three kinds of outside systems through one interface each. A backend is a class in
the core plugin, chosen by name in the configuration. To add one, implement the interface, give
it a name, register it, and run the contract tests every backend of its kind passes.

| Kind | Interface | Shipped backends | Chosen by |
|---|---|---|---|
| Store | `Store` in `plugins/m2b/src/m2b/store/base.py` | `folder`, `icloud` | `store.backend` in `config.json` |
| Tasks | `Tasks` in `plugins/m2b/src/m2b/tasks/base.py` | `markdown`, `apple-reminders` | `tasks.backend` in `store.json` |
| Calendar | `CalendarBackend` in `plugins/m2b/src/m2b/calendar/base.py` | `none`, `apple-calendar` | `calendar.backend` in `config.json` |

Tasks are chosen in the store, because every machine must see the same list; store and calendar
are chosen per machine.

## The rules every backend keeps

- **"Could not look" is never "nothing there".** A tasks backend that cannot reach its list raises
  `TasksUnreachableError`, a calendar that cannot be asked raises its unreachable error, a store
  that cannot list a folder raises. Callers report these as "could not read"; an empty answer is
  taken as true.
- **Ids are stable.** A task keeps its id across completing, reopening and every machine.
- **Every call has a timeout.** Backends that run a program take `timeout_seconds` from the
  settings; nothing may hang a session start.
- **Standard library only, Python 3.9.** A backend may run an external program (`reminders-cli`,
  `osascript`), recorded by absolute path in `executables`, but adds no Python dependency.
- **A file that is not downloaded is not read.** Store backends report such files as evicted;
  reading one would download it or hang.

## Steps

1. **Implement the interface.** Subclass the abstract class and implement every abstract method.
   For tasks: `check_reachable`, `items`, `completed_items`, `add`, `set_notes`, `complete`,
   `uncomplete`, `drop`, `delete`, `export`. The docstrings in `base.py` state what each must
   do; the markdown backend (`tasks/markdown.py`) is the shortest complete example.
2. **Name and register it.** Add the name to the tuple of allowed backends
   (`TASKS_BACKENDS` in `config/store_settings.py`, `STORE_BACKENDS` and `CALENDAR_BACKENDS` in
   `config/machine.py`) and a branch to the factory of its kind (`tasks/factory.py`,
   `store/factory.py`, `calendar/factory.py`).
3. **Pass the contract.** Each kind has a contract test class: `Contracts.TasksContract` in
   `tests/tasks_contract.py`, `Contracts.StoreContract` in `tests/store_contract.py`,
   `Contracts.CalendarContract` in `tests/calendar_contract.py`. Subclass it and say how to build a
   fresh, empty backend; for tasks with a method, for a store with the class attributes
   `make_store` (a constructor taking the root, a temp folder and the guard) and `copy_of_plan`
   (a name the backend's sync service gives a conflict copy of `plan.md`):

   ```python
   class MyTasksContractTest(Contracts.TasksContract):
       def make_tasks(self, folder: Path) -> Tasks:
           return MyTasks(folder / "list.json")
   ```

   A backend that talks to a real service gets a fake of that service for the unit tests, as
   `tests/fakes/` has for `reminders-cli`.
4. **Integration tests against the real service** run only when asked and only against
   resources whose names start with `sb-test-`, never against your own lists. `M2B_IT=1` turns
   them on; each names its test resource in a variable of its own, and a test whose variable is
   missing is skipped:

   ```bash
   M2B_IT=1 M2B_IT_REMINDERS_LIST=sb-test-inbox M2B_IT_ICLOUD_DIR="$HOME/Library/Mobile Documents/com~apple~CloudDocs/sb-test-store" scripts/check --quick m2b
   ```

   The calendar test creates and removes its own `sb-test-` calendar (account from
   `M2B_IT_CALENDAR_ACCOUNT`, `iCloud` by default); `M2B_IT_PROVIDER_DIR` points the store test at
   a folder of another sync provider.

5. **Setup and doctor.** If the backend needs answers at setup (a list name, an account), extend
   `parse_answers` in `setup.py` and the setup skill's questions; `m2b doctor` reaches it through
   `check_reachable` or `check_access` without changes.

`scripts/check` must end with `check: passed` before a pull request. See
[CONTRIBUTING.md](../CONTRIBUTING.md).
