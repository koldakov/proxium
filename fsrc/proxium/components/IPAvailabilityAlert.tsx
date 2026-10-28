import { Alert } from '@mui/material'
import { useRecordContext } from 'react-admin'

import { MISSING_IP_HELP, ipAvailability, missingIpText } from './outgoing'

/** Atop the page of the outgoing IP in context, if some running proxy doesn't have it. */
export const IPAvailabilityAlert = () => {
  const record = useRecordContext()
  if (record === undefined) {
    return null
  }

  const availability = ipAvailability(record)
  if (availability === undefined || availability === 'everywhere') {
    return null
  }
  return (
    <Alert severity={availability === 'nowhere' ? 'error' : 'warning'} sx={{ mb: 2 }}>
      {missingIpText(record)}. {MISSING_IP_HELP}
    </Alert>
  )
}
