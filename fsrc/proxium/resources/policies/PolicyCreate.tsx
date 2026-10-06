import { Create, SimpleForm } from 'react-admin'

import { toPolicyData, utcToday } from './limits'
import { PolicyInputs } from './PolicyInputs'

export const PolicyCreate = () => (
  <Create redirect="list" transform={toPolicyData}>
    <SimpleForm
      defaultValues={{ isActive: true, isGlobal: false, globalStartsOn: utcToday(), rules: [{}] }}
    >
      <PolicyInputs />
    </SimpleForm>
  </Create>
)
