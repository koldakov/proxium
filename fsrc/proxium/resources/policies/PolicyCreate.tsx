import { Create, SimpleForm } from 'react-admin'

import { toPolicyData, utcToday } from './limits'
import { PolicyInputs } from './PolicyInputs'

export const PolicyCreate = () => (
  <Create redirect="list" transform={toPolicyData}>
    <SimpleForm
      defaultValues={{
        isActive: true,
        isGlobal: false,
        globalStartsOn: utcToday(),
        rules: [{ name: 'Default', match: 'all', blocks: [] }],
      }}
    >
      <PolicyInputs />
    </SimpleForm>
  </Create>
)
