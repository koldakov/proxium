import { Create, SimpleForm } from 'react-admin'

import { GroupInputs } from './GroupInputs'

export const GroupCreate = () => (
  <Create redirect="list">
    <SimpleForm defaultValues={{ permissions: [] }}>
      <GroupInputs />
    </SimpleForm>
  </Create>
)
