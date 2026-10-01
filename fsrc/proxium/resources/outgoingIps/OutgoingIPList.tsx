import { DataTable, DateField, List, ReferenceField, SelectInput } from 'react-admin'

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

export const OutgoingIPList = () => (
  <List filters={filters} exporter={false}>
    <DataTable rowClick="edit" bulkActionButtons={false}>
      <DataTable.Col source="id" disableSort />
      <DataTable.Col source="name" disableSort />
      <DataTable.Col source="ip" label="IP" disableSort />
      <DataTable.Col source="createdById" label="Created by" disableSort>
        <ReferenceField source="createdById" reference="users" link="show" />
      </DataTable.Col>
      <DataTable.Col source="createdAt" label="Created" disableSort>
        <DateField source="createdAt" showTime />
      </DataTable.Col>
    </DataTable>
  </List>
)
