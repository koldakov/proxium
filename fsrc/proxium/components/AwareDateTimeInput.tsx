import { DateTimeInput, type DateTimeInputProps } from 'react-admin'

// The input gives local time without an offset, the API wants an aware ISO string. Empty means none.
const toIsoString = (value: string): string | null =>
  value === '' ? null : new Date(value).toISOString()

/** `DateTimeInput` sending the picked local time as UTC. */
export const AwareDateTimeInput = (props: DateTimeInputProps) => (
  <DateTimeInput parse={toIsoString} {...props} />
)
