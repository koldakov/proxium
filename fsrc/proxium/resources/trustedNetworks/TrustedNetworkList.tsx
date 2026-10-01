import {
  BooleanField,
  DataTable,
  DateField,
  List,
  ReferenceField,
  SelectField,
  TextInput,
} from 'react-admin'

import { OUTGOING_MODES } from '../../components/outgoing'
import { QuerySearchInput } from '../../components/QuerySearchInput'
import { ipNetwork } from '../../components/validators'
import { OpenToEveryoneAlert } from './OpenToEveryoneAlert'
import { TrustedNetworksWarning } from './TrustedNetworksWarning'

// An invalid filter isn't applied: a network half typed doesn't reach the API.
const filters = [
  <QuerySearchInput key="query" source="query" alwaysOn />,
  <TextInput key="within" source="within" label="Inside network" validate={ipNetwork()} />,
  <TextInput key="contains" source="contains" label="Containing network" validate={ipNetwork()} />,
]

export const TrustedNetworkList = () => (
  <>
    <OpenToEveryoneAlert />
    <TrustedNetworksWarning />
    <List filters={filters} exporter={false}>
      <DataTable rowClick="edit" bulkActionButtons={false}>
        <DataTable.Col source="id" disableSort />
        <DataTable.Col source="name" disableSort />
        <DataTable.Col source="network" disableSort />
        <DataTable.Col source="isActive" label="Active" field={BooleanField} disableSort />
        <DataTable.Col source="outgoingMode" label="Outgoing IP" disableSort>
          <SelectField source="outgoingMode" choices={OUTGOING_MODES} />
        </DataTable.Col>
        <DataTable.Col source="createdById" label="Created by" disableSort>
          <ReferenceField source="createdById" reference="users" link="show" />
        </DataTable.Col>
        <DataTable.Col source="createdAt" label="Created" disableSort>
          <DateField source="createdAt" showTime />
        </DataTable.Col>
      </DataTable>
    </List>
  </>
)
