import { DataTable, DateField, List } from 'react-admin'

import { useDetailPage } from '../../components/detailPage'
import { PermissionsField } from '../../components/PermissionsField'
import { QuerySearchInput } from '../../components/QuerySearchInput'

const filters = [<QuerySearchInput key="query" source="query" alwaysOn />]

export const GroupList = () => {
  const detailPage = useDetailPage('groups')

  return (
    <List filters={filters} exporter={false}>
      <DataTable rowClick={detailPage} bulkActionButtons={false}>
        <DataTable.Col source="id" disableSort />
        <DataTable.Col source="name" disableSort />
        <DataTable.Col source="permissions" disableSort>
          <PermissionsField />
        </DataTable.Col>
        <DataTable.Col source="createdAt" label="Created" disableSort>
          <DateField source="createdAt" showTime />
        </DataTable.Col>
      </DataTable>
    </List>
  )
}
