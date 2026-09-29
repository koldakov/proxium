import { BooleanInput, Create, PasswordInput, SimpleForm, TextInput, required } from 'react-admin'

import { AwareDateTimeInput } from '../../components/AwareDateTimeInput'

export const BasicProxyAccountCreate = () => (
  <Create redirect="show">
    <SimpleForm>
      <TextInput source="username" validate={required()} />
      <PasswordInput source="password" validate={required()} />
      <BooleanInput source="isActive" label="Active" defaultValue />
      <AwareDateTimeInput source="expiresAt" label="Expires" helperText="Empty: never" />
    </SimpleForm>
  </Create>
)
