import { Create, SimpleForm } from 'react-admin'

import { OutgoingIPInputs } from './OutgoingIPInputs'

export const OutgoingIPCreate = () => (
  <Create redirect="list">
    <SimpleForm>
      <OutgoingIPInputs />
    </SimpleForm>
  </Create>
)
