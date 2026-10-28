import { Chip, Tooltip } from '@mui/material'
import { useRecordContext } from 'react-admin'

import { STATUSES, type ProxyInstanceStatus } from './statuses'

/** The status of the instance in context, what it means on hover. */
export const ProxyInstanceStatusChip = () => {
  const record = useRecordContext()
  if (record === undefined) {
    return null
  }

  const { label, color, description } = STATUSES[record.status as ProxyInstanceStatus]
  return (
    <Tooltip title={description}>
      <Chip label={label} color={color} size="small" />
    </Tooltip>
  )
}
