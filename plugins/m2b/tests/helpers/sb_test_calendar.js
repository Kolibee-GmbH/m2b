// Creates and removes the calendar the macOS integration test writes into; tests only.
//   osascript -l JavaScript sb_test_calendar.js create <name> [<account>]
//   osascript -l JavaScript sb_test_calendar.js remove <name>
// Any name not starting with "sb-test-" is refused before the calendar store is opened, so the
// owner's own calendars are never touched. The calendar goes into the account named (default
// "iCloud"); remove deletes every calendar with exactly that name, and its events with it.
ObjC.import('EventKit');
ObjC.import('Foundation');

const PREFIX = 'sb-test-';
const FULL_ACCESS = 3;

function reply(ok, value) {
  return JSON.stringify(ok ? {ok: value} : {error: value});
}

function calendarsNamed(store, name) {
  const found = store.calendarsForEntityType($.EKEntityTypeEvent);
  const named = [];
  for (let i = 0; i < Number(found.count); i++) {
    const calendar = found.objectAtIndex(i);
    if (ObjC.unwrap(calendar.title) === name) {
      named.push(calendar);
    }
  }
  return named;
}

function sourceTitled(store, title) {
  const sources = store.sources;
  for (let i = 0; i < Number(sources.count); i++) {
    if (ObjC.unwrap(sources.objectAtIndex(i).title) === title) {
      return sources.objectAtIndex(i);
    }
  }
  return null;
}

function run(argv) {
  const op = argv[0];
  const name = argv[1] || '';
  if (!name.startsWith(PREFIX)) {
    return reply(false, 'refused: the test calendar name must start with ' + PREFIX);
  }
  // The bridge hands enum values and counts over as strings.
  if (Number($.EKEventStore.authorizationStatusForEntityType($.EKEntityTypeEvent)) !== FULL_ACCESS) {
    return reply(false, 'no full calendar access');
  }
  const store = $.EKEventStore.alloc.init;
  const error = Ref();
  if (op === 'create') {
    if (calendarsNamed(store, name).length > 0) {
      return reply(false, 'a calendar named ' + name + ' exists already');
    }
    const source = sourceTitled(store, argv[2] || 'iCloud');
    if (source === null) {
      return reply(false, 'no account named ' + (argv[2] || 'iCloud'));
    }
    const calendar = $.EKCalendar.calendarForEntityTypeEventStore($.EKEntityTypeEvent, store);
    calendar.setTitle(name);
    calendar.setSource(source);
    if (!store.saveCalendarCommitError(calendar, true, error)) {
      return reply(false, 'the calendar could not be created: ' + (error[0] ? ObjC.unwrap(error[0].localizedDescription) : '?'));
    }
    return reply(true, ObjC.unwrap(calendar.calendarIdentifier));
  }
  if (op === 'remove') {
    const named = calendarsNamed(store, name);
    for (const calendar of named) {
      if (!store.removeCalendarCommitError(calendar, true, error)) {
        return reply(false, 'the calendar could not be removed: ' + (error[0] ? ObjC.unwrap(error[0].localizedDescription) : '?'));
      }
    }
    return reply(true, named.length);
  }
  return reply(false, 'unknown op ' + op);
}
