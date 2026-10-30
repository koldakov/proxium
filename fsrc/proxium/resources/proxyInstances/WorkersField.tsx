import { Tooltip, Typography } from '@mui/material'
import { useRecordContext } from 'react-admin'

// Only these report live counts: a stopped instance runs none, an unknown one's are stale.
const LIVE_STATUSES = new Set(['pending', 'running'])

/** Serving workers of the instance in context out of all it runs, e.g. "3 / 4", in warning color if any is down. */
export const WorkersField = () => {
  const record = useRecordContext()
  if (record === undefined || !LIVE_STATUSES.has(record.status)) {
    return null
  }

  const isShort = record.runningWorkers < record.workers
  return (
    <Tooltip
      title={
        isShort
          ? 'Some workers are starting or restarting after a crash: the proxy serves on the rest.'
          : 'Every worker serves.'
      }
    >
      <Typography variant="body2" color={isShort ? 'warning.main' : undefined}>
        {record.runningWorkers} / {record.workers}
      </Typography>
    </Tooltip>
  )
}
