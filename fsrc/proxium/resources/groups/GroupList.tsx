import { DataTable, DateField, List, useCanAccess } from 'react-admin'

import { PermissionsField } from '../../components/PermissionsField'
import { QuerySearchInput } from '../../components/QuerySearchInput'

const filters = [<QuerySearchInput key="query" source="query" alwaysOn />]

export const GroupList = () => {
  // No show page: without `change` a row leads nowhere.
  const { canAccess: canChange } = useCanAccess({ resource: 'groups', action: 'edit' })

  return (
    <List filters={filters} exporter={false}>
      <DataTable rowClick={canChange ? 'edit' : false} bulkActionButtons={false}>
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
