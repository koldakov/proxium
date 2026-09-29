import { Chip } from '@mui/material'
import { useRecordContext } from 'react-admin'

/** Active, expired or revoked, from `isActive` and `expiresAt` of the proxy account in context. */
export const AccountStatusChip = () => {
  const record = useRecordContext()
  if (record === undefined) {
    return null
  }

  if (!record.isActive) {
    return <Chip label="Revoked" color="error" size="small" />
  }
  if (record.expiresAt !== null && new Date(record.expiresAt) <= new Date()) {
    return <Chip label="Expired" color="warning" size="small" />
  }
  return <Chip label="Active" color="success" size="small" />
}
