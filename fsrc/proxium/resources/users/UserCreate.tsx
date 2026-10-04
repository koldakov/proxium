import { Create, email, PasswordInput, SimpleForm, TextInput, required } from 'react-admin'

import { UserAccessInputs } from './UserAccessInputs'

export const UserCreate = () => (
  <Create redirect="show">
    <SimpleForm
      defaultValues={{ isActive: true, isSuperuser: false, groupIds: [], permissions: [] }}
    >
      <TextInput source="email" validate={[required(), email()]} />
      <TextInput source="name" validate={required()} />
      <TextInput source="surname" validate={required()} />
      <PasswordInput source="password" validate={required()} helperText="At least 8 characters" />
      <UserAccessInputs />
    </SimpleForm>
  </Create>
)
