import { BooleanField, DataTable, DateField, List, ReferenceField } from 'react-admin'

import { QuerySearchInput } from '../../components/QuerySearchInput'

const filters = [<QuerySearchInput key="query" source="query" alwaysOn />]

export const TokenProxyAccountList = () => (
  <List filters={filters} exporter={false}>
    <DataTable rowClick="show" bulkActionButtons={false}>
      <DataTable.Col source="id" disableSort />
      <DataTable.Col source="name" disableSort />
      <DataTable.Col source="key" disableSort />
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
