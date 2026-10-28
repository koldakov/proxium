import { Stack, Typography } from '@mui/material'
import { DateField, useRecordContext } from 'react-admin'

interface SinceFieldProps {
  source: string
  // Read by `DataTable.Col` and `Labeled`.
  label?: string
}

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['day', 24 * 60 * 60],
  ['hour', 60 * 60],
  ['minute', 60],
  ['second', 1],
]

const relativeTimeFormat = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })

// E.g. "12 seconds ago" or "3 days ago", in the largest unit that fits: reports come every few seconds.
const fromNow = (date: Date): string => {
  const seconds = (date.getTime() - Date.now()) / 1000
  const [unit, size] =
    UNITS.find(([, size]) => Math.abs(seconds) >= size) ?? UNITS[UNITS.length - 1]
  return relativeTimeFormat.format(Math.round(seconds / size), unit)
}

/** A past moment with how long ago it was, e.g. the last report of an instance. */
export const SinceField = ({ source }: SinceFieldProps) => {
  const record = useRecordContext()
  const value: string | undefined = record?.[source]
  if (value === undefined) {
    return null
  }

  return (
    <Stack>
      <DateField source={source} showTime />
      <Typography variant="caption" color="text.secondary">
        {fromNow(new Date(value))}
      </Typography>
    </Stack>
  )
}
