import { Card, CardActionArea, CardContent, Stack, Typography } from '@mui/material'

import { STATUSES, type ProxyInstanceStatus } from './statuses'
import { useProxyInstanceCounts } from './useProxyInstanceCounts'

interface ProxyInstanceCountsProps {
  // Its card stands out, e.g. the status the list is filtered by.
  selected?: ProxyInstanceStatus
  onSelect: (status: ProxyInstanceStatus) => void
}

/** How many instances are in each status, a card per status. */
export const ProxyInstanceCounts = ({ selected, onSelect }: ProxyInstanceCountsProps) => {
  const data = useProxyInstanceCounts()

  return (
    <Stack direction="row" spacing={2} sx={{ flexWrap: 'wrap' }} useFlexGap>
      {(Object.keys(STATUSES) as ProxyInstanceStatus[]).map((status) => {
        const count = data?.[status]
        const { label, color, description } = STATUSES[status]
        // Unknown ones need a look: the card stands out while there are any.
        const isAlarming = status === 'unknown' && count !== undefined && count > 0
        // `default` has no palette entry of its own.
        const highlight = color === 'default' ? 'text.secondary' : `${color}.main`
        return (
          <Card
            key={status}
            variant="outlined"
            sx={{
              minWidth: 160,
              flex: '1 1 160px',
              borderColor: selected === status || isAlarming ? highlight : undefined,
            }}
          >
            <CardActionArea onClick={() => onSelect(status)} title={description}>
              <CardContent>
                <Typography variant="body2" color="text.secondary">
                  {label}
                </Typography>
                <Typography variant="h5" color={isAlarming ? 'error' : undefined}>
                  {count ?? '…'}
                </Typography>
              </CardContent>
            </CardActionArea>
          </Card>
        )
      })}
    </Stack>
  )
}
