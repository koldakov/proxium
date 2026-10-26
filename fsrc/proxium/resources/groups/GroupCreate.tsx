import { Create } from 'react-admin'

import { GuardedSimpleForm } from '../../components/UnsavedChangesGuard'
import { GroupInputs } from './GroupInputs'

export const GroupCreate = () => (
  <Create redirect="list">
    <GuardedSimpleForm defaultValues={{ permissions: [] }}>
      <GroupInputs />
    </GuardedSimpleForm>
  </Create>
)
