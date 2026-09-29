import { BooleanInput, Edit, SimpleForm, TextInput, required } from 'react-admin'

import { AwareDateTimeInput } from '../../components/AwareDateTimeInput'
import { NoDeleteToolbar } from '../../components/NoDeleteToolbar'

export const TokenProxyAccountEdit = () => (
  <Edit redirect="show" mutationMode="pessimistic">
    <SimpleForm toolbar={<NoDeleteToolbar />}>
      <TextInput source="name" validate={required()} />
      <BooleanInput source="isActive" label="Active" />
      <AwareDateTimeInput source="expiresAt" label="Expires" helperText="Empty: never" />
    </SimpleForm>
  </Edit>
)
