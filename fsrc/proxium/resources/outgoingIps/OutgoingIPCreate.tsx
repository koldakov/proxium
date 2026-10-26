import { Create } from 'react-admin'

import { GuardedSimpleForm } from '../../components/UnsavedChangesGuard'
import { OutgoingIPInputs } from './OutgoingIPInputs'

export const OutgoingIPCreate = () => (
  <Create redirect="list">
    <GuardedSimpleForm>
      <OutgoingIPInputs />
    </GuardedSimpleForm>
  </Create>
)
