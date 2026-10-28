import { Show, SimpleForm } from 'react-admin'

import { IPAvailabilityAlert } from '../../components/IPAvailabilityAlert'
import { OutgoingIPInputs } from './OutgoingIPInputs'

/** The edit form, read-only: for those who may only view outgoing IPs. */
export const OutgoingIPShow = () => (
  <Show>
    <SimpleForm toolbar={false}>
      <IPAvailabilityAlert />
      <OutgoingIPInputs readOnly />
    </SimpleForm>
  </Show>
)
