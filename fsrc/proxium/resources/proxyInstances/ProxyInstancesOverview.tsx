import { Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material'
import { Link, RecordContextProvider, useCreatePath, useGetList } from 'react-admin'
import { useNavigate } from 'react-router-dom'

import { ShowSection } from '../../components/ShowSection'
import { ProxyInstanceCounts } from './ProxyInstanceCounts'
import { SinceField } from './SinceField'
import { REFRESH_MS, STATUSES, type ProxyInstanceStatus } from './statuses'
import { useProxyInstanceCounts } from './useProxyInstanceCounts'

// Unknown instances listed on the overview, the rest are a click away.
const UNKNOWN_SHOWN = 5

const UnknownInstances = ({ unknownPath }: { unknownPath: string }) => {
  const counts = useProxyInstanceCounts()
  const { data = [], total = 0 } = useGetList(
    'proxy-instances',
    { filter: { status: 'unknown' }, pagination: { page: 1, perPage: UNKNOWN_SHOWN } },
    { refetchInterval: REFRESH_MS },
  )
  if (counts === undefined) {
    return null
  }
  if (Object.values(counts).every((count) => count === 0)) {
    return (
      <Typography color="text.secondary">
        No proxy has reported yet: one shows up here once it starts.
      </Typography>
    )
  }
  if (total === 0) {
    return <Typography color="text.secondary">Every instance reports on time.</Typography>
  }

  return (
    <Stack spacing={1}>
      <Typography color="error">{STATUSES.unknown.description}</Typography>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Host</TableCell>
            <TableCell>Name</TableCell>
            <TableCell>Last seen</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {data.map((instance) => (
            <RecordContextProvider key={instance.id} value={instance}>
              <TableRow>
                <TableCell>{instance.hostname}</TableCell>
                <TableCell>{instance.name}</TableCell>
                <TableCell>
                  <SinceField source="lastSeenAt" />
                </TableCell>
              </TableRow>
            </RecordContextProvider>
          ))}
        </TableBody>
      </Table>
      {total > data.length && <Link to={unknownPath}>And {total - data.length} more</Link>}
    </Stack>
  )
}

/** Instances by status and the unknown ones, on the overview. A card opens the list filtered by its status. */
export const ProxyInstancesOverview = () => {
  const navigate = useNavigate()
  const createPath = useCreatePath()
  const listPath = createPath({ resource: 'proxy-instances', type: 'list' })
  // The list reads its filter from the URL.
  const filteredPath = (status: ProxyInstanceStatus) =>
    `${listPath}?${new URLSearchParams({ filter: JSON.stringify({ status }) })}`

  return (
    <ShowSection title="Proxy instances">
      <ProxyInstanceCounts onSelect={(status) => navigate(filteredPath(status))} />
      <UnknownInstances unknownPath={filteredPath('unknown')} />
      <Link to={listPath}>All instances</Link>
    </ShowSection>
  )
}
