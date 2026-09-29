import { BooleanInput, Edit, SimpleForm, TextInput, TopToolbar, required } from 'react-admin'

import { AwareDateTimeInput } from '../../components/AwareDateTimeInput'
import { NoDeleteToolbar } from '../../components/NoDeleteToolbar'
import { UpdatePasswordButton } from './UpdatePasswordButton'

export const BasicProxyAccountEdit = () => (
  <Edit
    redirect="show"
    mutationMode="pessimistic"
    actions={
      <TopToolbar>
        <UpdatePasswordButton />
      </TopToolbar>
    }
  >
    <SimpleForm toolbar={<NoDeleteToolbar />}>
      <TextInput source="username" validate={required()} />
      <BooleanInput source="isActive" label="Active" />
      <AwareDateTimeInput source="expiresAt" label="Expires" helperText="Empty: never" />
    </SimpleForm>
  </Edit>
)
