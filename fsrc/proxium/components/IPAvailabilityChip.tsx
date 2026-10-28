import { Chip, Tooltip } from '@mui/material'
import { useRecordContext } from 'react-admin'

import { MISSING_IP_HELP, ipAvailability, missingIpText } from './outgoing'

interface IPAvailabilityChipProps {
  // A chip for an IP every proxy has too: in a list of IPs, not where only trouble matters.
  showOk?: boolean
}

/** Whether the running proxies have the outgoing IP in context. Nothing while no proxy runs. */
export const IPAvailabilityChip = ({ showOk = false }: IPAvailabilityChipProps) => {
  const record = useRecordContext()
  if (record === undefined) {
    return null
  }

  const availability = ipAvailability(record)
  if (availability === undefined || (availability === 'everywhere' && !showOk)) {
    return null
  }
  if (availability === 'everywhere') {
    return <Chip label="On every proxy" color="success" size="small" />
  }
  return (
    <Tooltip title={MISSING_IP_HELP}>
      <Chip
        label={missingIpText(record)}
        color={availability === 'nowhere' ? 'error' : 'warning'}
        size="small"
      />
    </Tooltip>
  )
}
