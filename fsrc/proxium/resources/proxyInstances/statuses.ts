import type { ChipProps } from '@mui/material'

export type ProxyInstanceStatus = 'pending' | 'running' | 'stopped' | 'unknown'

interface StatusLook {
  label: string
  color: ChipProps['color']
  // What it means for the admin, e.g. in a tooltip.
  description: string
}

// In the order the summary shows them.
export const STATUSES: Record<ProxyInstanceStatus, StatusLook> = {
  running: {
    label: 'Running',
    color: 'success',
    description: 'Serving clients.',
  },
  pending: {
    label: 'Pending',
    color: 'info',
    description: 'Starting, not serving yet.',
  },
  unknown: {
    label: 'Unknown',
    color: 'error',
    description: 'Missed its reports: crashed, hung or cut off from the database.',
  },
  stopped: {
    label: 'Stopped',
    color: 'default',
    description: 'Shut down gracefully.',
  },
}

export const STATUS_CHOICES = Object.entries(STATUSES).map(([id, { label }]) => ({
  id,
  name: label,
}))

// The proxy reports every 30 s by default: a refresh in between shows changes soon enough.
export const REFRESH_MS = 10 * 1000
