import { Edit, email, TextInput, required } from 'react-admin'

import { NoDeleteToolbar } from '../../components/NoDeleteToolbar'
import { GuardedSimpleForm } from '../../components/UnsavedChangesGuard'
import { UserAccessInputs } from './UserAccessInputs'

// Permissions apply to the user's next request. The password is set from the show page.
export const UserEdit = () => (
  <Edit redirect="show" mutationMode="pessimistic">
    <GuardedSimpleForm toolbar={<NoDeleteToolbar />}>
      <TextInput source="email" validate={[required(), email()]} />
      <TextInput source="name" validate={required()} />
      <TextInput source="surname" validate={required()} />
      <UserAccessInputs />
    </GuardedSimpleForm>
  </Edit>
)
