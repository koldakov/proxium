import { Alert, Box } from '@mui/material'
import { DataTable, List, SelectInput, useListContext } from 'react-admin'

import { DeregisterButton } from './DeregisterButton'
import { ProxyInstanceCounts } from './ProxyInstanceCounts'
import { ProxyInstanceIPs } from './ProxyInstanceIPs'
import { ProxyInstanceStatusChip } from './ProxyInstanceStatusChip'
import { SinceField } from './SinceField'
import { REFRESH_MS, STATUS_CHOICES } from './statuses'
import { WorkersField } from './WorkersField'

const filters = [<SelectInput key="status" source="status" choices={STATUS_CHOICES} alwaysOn />]

// Atop the list: a card filters the list by its status, again clears it.
const ListCounts = () => {
  const { filterValues, setFilters } = useListContext()

  return (
    <Box sx={{ p: 2 }}>
      <ProxyInstanceCounts
        selected={filterValues.status}
        onSelect={(status) => setFilters(filterValues.status === status ? {} : { status })}
      />
    </Box>
  )
}

export const ProxyInstanceList = () => (
  <>
    <Alert severity="info" sx={{ mb: 2 }}>
      Every proxy reports here on its own: a new one shows up once it starts, a restarted one keeps
      its row. One that stops reporting turns unknown.
    </Alert>
    <List
      filters={filters}
      exporter={false}
      // Statuses change on their own: the page follows them without a reload.
      queryOptions={{ refetchInterval: REFRESH_MS }}
    >
      <ListCounts />
      {/* A row opens its IPs. */}
      <DataTable bulkActionButtons={false} expand={<ProxyInstanceIPs />}>
        <DataTable.Col source="hostname" label="Host" disableSort />
        <DataTable.Col source="name" disableSort />
        <DataTable.Col label="Status" disableSort>
          <ProxyInstanceStatusChip />
        </DataTable.Col>
        <DataTable.Col label="Workers" disableSort>
          <WorkersField />
        </DataTable.Col>
        <DataTable.Col source="version" disableSort />
        <DataTable.Col source="startedAt" label="Started" disableSort>
          <SinceField source="startedAt" />
        </DataTable.Col>
        <DataTable.Col source="lastSeenAt" label="Last seen" disableSort>
          <SinceField source="lastSeenAt" />
        </DataTable.Col>
        <DataTable.Col disableSort>
          <DeregisterButton />
        </DataTable.Col>
      </DataTable>
    </List>
  </>
)
