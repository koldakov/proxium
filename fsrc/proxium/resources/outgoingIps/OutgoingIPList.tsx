import { DataTable, DateField, List, SelectInput, useCanAccess } from 'react-admin'

import { CreatedByField } from '../../components/CreatedByField'
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
]

export const OutgoingIPList = () => {
  // No show page: without `change` a row leads nowhere.
  const { canAccess: canChange } = useCanAccess({ resource: 'outgoing-ips', action: 'edit' })

  return (
    <List filters={filters} exporter={false}>
      <DataTable rowClick={canChange ? 'edit' : false} bulkActionButtons={false}>
        <DataTable.Col source="id" disableSort />
        <DataTable.Col source="name" disableSort />
        <DataTable.Col source="ip" label="IP" disableSort />
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
