import { BooleanInput, FormDataConsumer, TextInput, required } from 'react-admin'

import { ipNetwork } from '../../components/validators'
import { TypedEveryoneAlert } from './OpenToEveryoneAlert'
import { OverlapsSection } from './OverlapsSection'

/** The fields of a trusted network, shared by create and edit. */
export const TrustedNetworkInputs = () => (
  <>
    <TextInput source="name" validate={required()} helperText="E.g. Office" />
    <TextInput
      source="network"
      validate={[required(), ipNetwork()]}
      helperText="E.g. 192.168.0.0/16, or 10.0.0.5 for a single address. IPv6 works too"
    />
    <FormDataConsumer>
      {({ formData }) => (
        <>
          <TypedEveryoneAlert network={formData.network} />
          <OverlapsSection network={formData.network} />
        </>
      )}
    </FormDataConsumer>
    <BooleanInput source="isActive" label="Active" />
  </>
)
