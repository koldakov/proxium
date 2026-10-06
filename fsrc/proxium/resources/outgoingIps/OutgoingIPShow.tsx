import { Show, SimpleForm } from 'react-admin'

import { OutgoingIPInputs } from './OutgoingIPInputs'

/** The edit form, read-only: for those who may only view outgoing IPs. */
export const OutgoingIPShow = () => (
  <Show>
    <SimpleForm toolbar={false}>
      <OutgoingIPInputs readOnly />
    </SimpleForm>
  </Show>
)
