// The EventKit side of the apple-calendar backend (calendar/apple.py), run as
//   osascript -l JavaScript eventkit.js '<request as JSON>'
// It prints one JSON object: {"ok": <result>} or {"error": {"kind": ..., "message": ...}}.
// Requests: {"op": "access"}, {"op": "calendars"}, {"op": "events", "start", "end"} and
// {"op": "create", "calendarId", "title", "start", "end", "allDay"}. Times are milliseconds
// since the epoch. All-day events are written and read as EventKit reports them, from midnight
// of the first day to 23:59:59 of the last; the Python side translates. It never updates or deletes an event: changes to a
// meeting send invitation mail, and EventKit has no undo.
ObjC.import('EventKit');
ObjC.import('Foundation');

// EKAuthorizationStatusFullAccess since macOS 14, the same value as the former "authorized".
const FULL_ACCESS = 3;
const NOT_DETERMINED = 0;
// osascript is stopped by the caller's timeout; this only bounds the wait inside the script.
const ACCESS_PROMPT_SECONDS = 120;

function answer(result) {
  return JSON.stringify({ok: result});
}

function failure(kind, message) {
  return JSON.stringify({error: {kind: kind, message: message}});
}

function text(value) {
  const unwrapped = ObjC.unwrap(value);
  return typeof unwrapped === 'string' ? unwrapped : null;
}

function date(milliseconds) {
  return $.NSDate.dateWithTimeIntervalSince1970(milliseconds / 1000);
}

function milliseconds(nsdate) {
  return Math.round(nsdate.timeIntervalSince1970 * 1000);
}

// The bridge hands enum values and counts over as strings ("3"), booleans and times as such.
function accessStatus() {
  return Number($.EKEventStore.authorizationStatusForEntityType($.EKEntityTypeEvent));
}

// The first call in a new privacy chain shows the access prompt and waits for the answer. The
// store that asked is not used afterwards: one created before the grant may show no calendars.
function hasFullAccess() {
  if (accessStatus() === NOT_DETERMINED) {
    let answered = false;
    const asking = $.EKEventStore.alloc.init;
    asking.requestFullAccessToEventsWithCompletion(function (granted, error) {
      answered = true;
    });
    const deadline = Date.now() + ACCESS_PROMPT_SECONDS * 1000;
    while (!answered && Date.now() < deadline) {
      $.NSRunLoop.currentRunLoop.runUntilDate($.NSDate.dateWithTimeIntervalSinceNow(0.1));
    }
  }
  return accessStatus() === FULL_ACCESS;
}

function allCalendars(store) {
  const found = store.calendarsForEntityType($.EKEntityTypeEvent);
  const calendars = [];
  for (let i = 0; i < Number(found.count); i++) {
    calendars.push(found.objectAtIndex(i));
  }
  return calendars;
}

function describeCalendar(calendar) {
  return {
    id: text(calendar.calendarIdentifier),
    name: text(calendar.title),
    account: text(calendar.source.title),
    writable: Boolean(calendar.allowsContentModifications),
  };
}

function describeEvent(event) {
  return {
    title: text(event.title),
    start: milliseconds(event.startDate),
    end: milliseconds(event.endDate),
    allDay: Boolean(event.isAllDay),
    calendar: text(event.calendar.title),
    account: text(event.calendar.source.title),
  };
}

function events(store, request) {
  const predicate = store.predicateForEventsWithStartDateEndDateCalendars(
    date(request.start), date(request.end), store.calendarsForEntityType($.EKEntityTypeEvent));
  const found = store.eventsMatchingPredicate(predicate);
  const described = [];
  for (let i = 0; i < Number(found.count); i++) {
    described.push(describeEvent(found.objectAtIndex(i)));
  }
  return answer(described);
}

function create(store, request) {
  const calendar = store.calendarWithIdentifier(request.calendarId);
  if (calendar.isNil()) {
    return failure('not-found', 'no calendar has the identifier ' + request.calendarId);
  }
  if (!calendar.allowsContentModifications) {
    return failure('read-only', 'the calendar ' + text(calendar.title) + ' does not allow changes');
  }
  const event = $.EKEvent.eventWithEventStore(store);
  event.setTitle(request.title);
  event.setStartDate(date(request.start));
  event.setEndDate(date(request.end));
  event.setAllDay(request.allDay === true);
  event.setCalendar(calendar);
  const error = Ref();
  if (!store.saveEventSpanCommitError(event, $.EKSpanThisEvent, true, error)) {
    const reason = error[0] ? text(error[0].localizedDescription) : null;
    return failure('save', reason || 'the calendar store refused the event');
  }
  const stored = store.eventWithIdentifier(event.eventIdentifier);
  if (stored.isNil()) {
    return failure('read-back', 'the event was saved but cannot be read back');
  }
  const described = describeEvent(stored);
  return answer({
    id: text(stored.eventIdentifier),
    title: described.title,
    start: described.start,
    end: described.end,
    allDay: described.allDay,
    calendarId: text(stored.calendar.calendarIdentifier),
  });
}

function run(argv) {
  let request;
  try {
    request = JSON.parse(argv[0]);
  } catch (error) {
    return failure('request', 'the request is not JSON');
  }
  if (!hasFullAccess()) {
    return failure('access', 'calendar access was not granted');
  }
  const store = $.EKEventStore.alloc.init;
  switch (request.op) {
    case 'access':
      return answer(true);
    case 'calendars':
      return answer(allCalendars(store).map(describeCalendar));
    case 'events':
      return events(store, request);
    case 'create':
      return create(store, request);
    default:
      return failure('request', 'unknown op ' + request.op);
  }
}
