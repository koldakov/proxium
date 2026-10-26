// The browser's clock, 12 or 24 hours, as its own date inputs show it.
export const AMPM = ['h11', 'h12'].includes(
  new Intl.DateTimeFormat(undefined, { hour: 'numeric' }).resolvedOptions().hourCycle ?? '',
)

// How pickers show dates and times. Days unambiguous in any locale.
export const DATE_FORMAT = 'YYYY-MM-DD'
export const TIME_FORMAT = AMPM ? 'hh:mm A' : 'HH:mm'
export const DATE_TIME_FORMAT = `${DATE_FORMAT} ${TIME_FORMAT}`
