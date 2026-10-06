import { Show, SimpleForm } from 'react-admin'

import { PolicyInputs } from './PolicyInputs'

/** The edit form, read-only: for those who may only view policies. */
export const PolicyShow = () => (
  <Show>
    <SimpleForm toolbar={false}>
      <PolicyInputs readOnly />
    </SimpleForm>
  </Show>
)
