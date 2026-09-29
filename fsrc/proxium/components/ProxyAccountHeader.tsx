import { Stack, Typography } from '@mui/material'
import { useRecordContext } from 'react-admin'

import { AccountStatusChip } from './AccountStatusChip'

/** The proxy account name with its status and id, atop a show page. */
export const ProxyAccountHeader = () => {
  const record = useRecordContext()
  if (record === undefined) {
    return null
  }

  return (
    <Stack spacing={0.5}>
      <Stack direction="row" alignItems="center" spacing={1.5}>
        <Typography variant="h5">{record.name}</Typography>
        <AccountStatusChip />
      </Stack>
      <Typography variant="body2" color="text.secondary">
        #{record.id}
      </Typography>
    </Stack>
  )
}
