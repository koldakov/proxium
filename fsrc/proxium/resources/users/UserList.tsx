import { DataTable, DateField, List } from 'react-admin'

import { BooleanChip } from '../../components/BooleanChip'
import { QuerySearchInput } from '../../components/QuerySearchInput'

const filters = [<QuerySearchInput key="query" source="query" alwaysOn />]

export const UserList = () => (
  <List filters={filters} exporter={false}>
    <DataTable rowClick="show" bulkActionButtons={false}>
      <DataTable.Col source="id" disableSort />
      <DataTable.Col source="email" disableSort />
      <DataTable.Col source="name" disableSort />
      <DataTable.Col source="surname" disableSort />
      <DataTable.Col source="isActive" label="Status" disableSort>
        <BooleanChip source="isActive" whenTrue="Active" whenFalse="Deactivated" />
      </DataTable.Col>
      <DataTable.Col source="isSuperuser" label="Superuser" disableSort>
        <BooleanChip source="isSuperuser" whenTrue="Superuser" color="primary" />
      </DataTable.Col>
      <DataTable.Col source="createdAt" label="Created" disableSort>
        <DateField source="createdAt" showTime />
      </DataTable.Col>
    </DataTable>
  </List>
)
