import { BooleanField, DataTable, DateField, List, SelectInput, useCanAccess } from 'react-admin'

import { CreatedByField } from '../../components/CreatedByField'
import { QuerySearchInput } from '../../components/QuerySearchInput'

const filters = [
  <QuerySearchInput key="query" source="query" alwaysOn />,
  // Strings, as in the query string: a `false` id would read as no choice.
  <SelectInput
    key="isGlobal"
    source="isGlobal"
    label="Global"
    choices={[
      { id: 'true', name: 'Global' },
      { id: 'false', name: 'Not global' },
    ]}
    alwaysOn
  />,
]

export const PolicyList = () => {
  // No show page: without `change` a row leads nowhere.
  const { canAccess: canChange } = useCanAccess({ resource: 'policies', action: 'edit' })

  return (
    <List filters={filters} exporter={false}>
      <DataTable rowClick={canChange ? 'edit' : false} bulkActionButtons={false}>
        <DataTable.Col source="id" disableSort />
        <DataTable.Col source="name" disableSort />
        <DataTable.Col source="isActive" label="Active" disableSort>
          <BooleanField source="isActive" />
        </DataTable.Col>
        <DataTable.Col source="isGlobal" label="Global" disableSort>
          <BooleanField source="isGlobal" />
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
