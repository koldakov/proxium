import { BooleanField, DataTable, DateField, List, ReferenceField, SearchInput } from 'react-admin'

const filters = [<SearchInput key="query" source="query" alwaysOn />]

export const BasicProxyAccountList = () => (
  <List filters={filters} exporter={false}>
    <DataTable rowClick="show" bulkActionButtons={false}>
      <DataTable.Col source="id" disableSort />
      <DataTable.Col source="username" disableSort />
      <DataTable.Col source="isActive" label="Active" field={BooleanField} disableSort />
      <DataTable.Col source="expiresAt" label="Expires" disableSort>
        <DateField source="expiresAt" showTime emptyText="Never" />
      </DataTable.Col>
      <DataTable.Col source="createdById" label="Created by" disableSort>
        <ReferenceField source="createdById" reference="users" link="show" />
      </DataTable.Col>
      <DataTable.Col source="createdAt" label="Created" disableSort>
        <DateField source="createdAt" showTime />
      </DataTable.Col>
    </DataTable>
  </List>
)
