import { Show, SimpleForm } from 'react-admin'

import { GroupInputs } from './GroupInputs'

/** The edit form, read-only: for those who may only view groups. */
export const GroupShow = () => (
  <Show>
    <SimpleForm toolbar={false}>
      <GroupInputs readOnly />
    </SimpleForm>
  </Show>
)
