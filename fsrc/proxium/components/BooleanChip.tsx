import { Chip, type ChipProps } from '@mui/material'
import { useRecordContext } from 'react-admin'

interface BooleanChipProps {
  source: string
  whenTrue: string
  // Nothing is shown for false without it: e.g. "Global" alone reads better than "Not global".
  whenFalse?: string
  color?: ChipProps['color']
}

/** A chip for a boolean of the record in context, colored when true. */
export const BooleanChip = ({
  source,
  whenTrue,
  whenFalse,
  color = 'success',
}: BooleanChipProps) => {
  const record = useRecordContext()
  if (record === undefined) {
    return null
  }

  if (record[source]) {
    return <Chip label={whenTrue} color={color} size="small" />
  }
  if (whenFalse === undefined) {
    return null
  }
  return <Chip label={whenFalse} size="small" />
}
