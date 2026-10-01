import { TextInput, required } from 'react-admin'

import { ipAddress } from '../../components/validators'

/** The fields of an outgoing IP, shared by create and edit. */
export const OutgoingIPInputs = () => (
  <>
    <TextInput source="name" validate={required()} helperText="E.g. Frankfurt 1" />
    <TextInput
      source="ip"
      label="IP"
      validate={[required(), ipAddress()]}
      helperText="An address of the proxy server, e.g. 203.0.113.10. Not checked: a wrong one fails its connections"
    />
  </>
)
