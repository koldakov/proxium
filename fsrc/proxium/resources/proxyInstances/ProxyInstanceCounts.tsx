import { Card, CardActionArea, CardContent, Stack, Typography } from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { useDataProvider, useListContext } from 'react-admin'

import type { ProxiumDataProvider } from '../../providers'
import { REFRESH_MS, STATUSES, type ProxyInstanceStatus } from './statuses'

/** How many instances are in each status, atop the list. A card filters the list by its status, again clears it. */
export const ProxyInstanceCounts = () => {
  const dataProvider = useDataProvider<ProxiumDataProvider>()
  const { filterValues, setFilters } = useListContext()
  const { data } = useQuery({
    queryKey: ['proxy-instances', 'getProxyInstanceCounts'],
    queryFn: () => dataProvider.getProxyInstanceCounts(),
    refetchInterval: REFRESH_MS,
  })

  const toggle = (status: ProxyInstanceStatus) =>
    setFilters(filterValues.status === status ? {} : { status })

  return (
    <Stack direction="row" spacing={2} sx={{ p: 2, flexWrap: 'wrap' }} useFlexGap>
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
              borderColor: filterValues.status === status || isAlarming ? highlight : undefined,
            }}
          >
            <CardActionArea onClick={() => toggle(status)} title={description}>
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
