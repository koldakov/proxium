import { Chip, Stack } from '@mui/material'
import { useRecordContext } from 'react-admin'

import { isExpired, isExpiringSoon } from './expiry'

/** Active or not, expired or expiring soon, self-signed: of the certificate in context. */
export const CertificateStatusChip = () => {
  const record = useRecordContext()
  if (record === undefined) {
    return null
  }

  return (
    <Stack direction="row" spacing={0.5}>
      {record.isActive ? (
        <Chip label="Active" color="success" size="small" />
      ) : (
        <Chip label="Inactive" size="small" />
      )}
      {isExpired(record) && <Chip label="Expired" color="error" size="small" />}
      {isExpiringSoon(record) && <Chip label="Expires soon" color="warning" size="small" />}
      {record.isSelfSigned && <Chip label="Self-signed" variant="outlined" size="small" />}
    </Stack>
  )
}
