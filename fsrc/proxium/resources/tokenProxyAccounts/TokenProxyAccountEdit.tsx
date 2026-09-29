import { Edit, SimpleForm, TextInput, required } from 'react-admin'

import { NoDeleteToolbar } from '../../components/NoDeleteToolbar'

// Only the name changes, the token is immutable.
export const TokenProxyAccountEdit = () => (
  <Edit redirect="show" mutationMode="pessimistic">
    <SimpleForm toolbar={<NoDeleteToolbar />}>
      <TextInput source="name" validate={required()} />
    </SimpleForm>
  </Edit>
)
