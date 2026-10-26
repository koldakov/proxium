import { Create, email, PasswordInput, TextInput, required } from 'react-admin'

import { GuardedSimpleForm } from '../../components/UnsavedChangesGuard'
import { UserAccessInputs } from './UserAccessInputs'

export const UserCreate = () => (
  <Create redirect="show">
    <GuardedSimpleForm
      defaultValues={{ isActive: true, isSuperuser: false, groupIds: [], permissions: [] }}
    >
      <TextInput source="email" validate={[required(), email()]} />
      <TextInput source="name" validate={required()} />
      <TextInput source="surname" validate={required()} />
      <PasswordInput source="password" validate={required()} helperText="At least 8 characters" />
      <UserAccessInputs />
    </GuardedSimpleForm>
  </Create>
)
