import { Create } from 'react-admin'

import { GuardedSimpleForm } from '../../components/UnsavedChangesGuard'
import { toPolicyData, utcToday } from './limits'
import { PolicyInputs } from './PolicyInputs'

export const PolicyCreate = () => (
  <Create redirect="list" transform={toPolicyData}>
    <GuardedSimpleForm
      defaultValues={{
        isActive: true,
        isGlobal: false,
        globalStartsOn: utcToday(),
        rules: [{ name: 'Default', match: 'all', blocks: [] }],
      }}
    >
      <PolicyInputs />
    </GuardedSimpleForm>
  </Create>
)
