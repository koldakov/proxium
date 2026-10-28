import { Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material'
import { Link, RecordContextProvider, useCreatePath, useGetList } from 'react-admin'

import { IPAvailabilityChip } from '../../components/IPAvailabilityChip'
import { ShowSection } from '../../components/ShowSection'
import { MISSING_IP_HELP } from '../../components/outgoing'
import { REFRESH_MS } from '../proxyInstances/statuses'

// Missing IPs listed on the overview, the rest are a click away.
const MISSING_SHOWN = 5

const MissingIPs = ({ missingPath }: { missingPath: string }) => {
  // Any IP: tells if there are IPs at all and how many proxies run.
  const { data: [any] = [], isPending } = useGetList(
    'outgoing-ips',
    { pagination: { page: 1, perPage: 1 } },
    { refetchInterval: REFRESH_MS },
  )
  const { data = [], total = 0 } = useGetList(
    'outgoing-ips',
    { filter: { missing: 'true' }, pagination: { page: 1, perPage: MISSING_SHOWN } },
    { refetchInterval: REFRESH_MS },
  )
  if (isPending) {
    return null
  }
  if (any === undefined) {
    return <Typography color="text.secondary">No outgoing IPs added.</Typography>
  }
  if (any.liveInstances === 0) {
    return (
      <Typography color="text.secondary">
        No proxy is running: nothing to check the IPs against.
      </Typography>
    )
  }
  if (total === 0) {
    return (
      <Typography color="text.secondary">Every outgoing IP is on every running proxy.</Typography>
    )
  }

  return (
    <Stack spacing={1}>
      <Typography color="warning.main">{MISSING_IP_HELP}</Typography>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>IP</TableCell>
            <TableCell>Name</TableCell>
            <TableCell>Proxies</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {data.map((outgoingIp) => (
            <RecordContextProvider key={outgoingIp.id} value={outgoingIp}>
              <TableRow>
                <TableCell sx={{ fontFamily: 'monospace' }}>{outgoingIp.ip}</TableCell>
                <TableCell>{outgoingIp.name}</TableCell>
                <TableCell>
                  <IPAvailabilityChip />
                </TableCell>
              </TableRow>
            </RecordContextProvider>
          ))}
        </TableBody>
      </Table>
      {total > data.length && <Link to={missingPath}>And {total - data.length} more</Link>}
    </Stack>
  )
}

/** Outgoing IPs some running proxy doesn't have, on the overview. */
export const OutgoingIPsOverview = () => {
  const createPath = useCreatePath()
  const listPath = createPath({ resource: 'outgoing-ips', type: 'list' })
  // The list reads its filter from the URL.
  const missingPath = `${listPath}?${new URLSearchParams({
    filter: JSON.stringify({ missing: 'true' }),
  })}`

  return (
    <ShowSection title="Outgoing IPs">
      <MissingIPs missingPath={missingPath} />
      <Link to={listPath}>All outgoing IPs</Link>
    </ShowSection>
  )
}
