import { Stack, Typography } from '@mui/material'
import { DateField, useRecordContext } from 'react-admin'

interface ExpiresFieldProps {
  source: string
  // Read by `Labeled`.
  label?: string
}

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 365 * 24 * 60 * 60],
  ['month', 30 * 24 * 60 * 60],
  ['day', 24 * 60 * 60],
  ['hour', 60 * 60],
  ['minute', 60],
]

const relativeTimeFormat = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })

// E.g. "in 3 days" or "2 hours ago", in the largest unit that fits.
const fromNow = (date: Date): string => {
  const seconds = (date.getTime() - Date.now()) / 1000
  const [unit, size] =
    UNITS.find(([, size]) => Math.abs(seconds) >= size) ?? UNITS[UNITS.length - 1]
  return relativeTimeFormat.format(Math.round(seconds / size), unit)
}

/** The expiry date with how far it is from now. Null means never. */
export const ExpiresField = ({ source }: ExpiresFieldProps) => {
  const record = useRecordContext()
  const value: string | null | undefined = record?.[source]
  if (value === undefined) {
    return null
  }
  if (value === null) {
    return <Typography variant="body2">Never</Typography>
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
