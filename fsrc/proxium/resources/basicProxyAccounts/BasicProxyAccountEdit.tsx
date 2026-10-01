import { Edit, SimpleForm, TextInput, required } from 'react-admin'

import { NoDeleteToolbar } from '../../components/NoDeleteToolbar'
import { OutgoingModeInput } from '../../components/OutgoingModeInput'

// The name, the outgoing mode and its pool change, the credentials are immutable.
export const BasicProxyAccountEdit = () => (
  <Edit redirect="show" mutationMode="pessimistic">
    <SimpleForm toolbar={<NoDeleteToolbar />}>
      <TextInput source="name" validate={required()} />
      <OutgoingModeInput />
    </SimpleForm>
  </Edit>
)
