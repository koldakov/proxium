import { Show } from 'react-admin'

import { PolicyForm } from './PolicyForm'
import { PolicyInputs } from './PolicyInputs'

/** The edit form, read-only: for those who may only view policies. */
export const PolicyShow = () => (
  <Show>
    <PolicyForm toolbar={false}>
      <PolicyInputs readOnly />
    </PolicyForm>
  </Show>
)
