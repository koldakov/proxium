import { DataTable, DateField, List, SelectInput, TextField } from 'react-admin'

import { CreatedByField } from '../../components/CreatedByField'
import { IPAvailabilityChip } from '../../components/IPAvailabilityChip'
import { useDetailPage } from '../../components/detailPage'
import { QuerySearchInput } from '../../components/QuerySearchInput'

const filters = [
  <QuerySearchInput key="query" source="query" alwaysOn />,
  <SelectInput
    key="version"
    source="version"
    choices={[
      { id: 4, name: 'IPv4' },
      { id: 6, name: 'IPv6' },
    ]}
  />,
  // Against the pending and running proxies.
  <SelectInput
    key="missing"
    source="missing"
    label="Proxies"
    choices={[
      { id: 'true', name: 'Missing on some' },
      { id: 'false', name: 'On every one' },
    ]}
  />,
]

export const OutgoingIPList = () => {
  const detailPage = useDetailPage('outgoing-ips')

  return (
    <List filters={filters} exporter={false}>
      <DataTable rowClick={detailPage} bulkActionButtons={false}>
        <DataTable.Col source="id" disableSort />
        <DataTable.Col source="name" disableSort />
        <DataTable.Col source="ip" label="IP" disableSort>
          <TextField source="ip" sx={{ fontFamily: 'monospace' }} />
        </DataTable.Col>
        <DataTable.Col label="Proxies" disableSort>
          <IPAvailabilityChip showOk />
        </DataTable.Col>
        <DataTable.Col source="createdById" label="Created by" disableSort>
          <CreatedByField />
        </DataTable.Col>
        <DataTable.Col source="createdAt" label="Created" disableSort>
          <DateField source="createdAt" showTime />
        </DataTable.Col>
      </DataTable>
    </List>
  )
}
