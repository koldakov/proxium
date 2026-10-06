import { BooleanInput, FormDataConsumer, TextInput, required, useRecordContext } from 'react-admin'

import { NewPoliciesInput } from '../../components/NewPoliciesInput'
import { OutgoingModeInput } from '../../components/OutgoingModeInput'
import { ipNetwork } from '../../components/validators'
import { TypedEveryoneAlert } from './OpenToEveryoneAlert'
import { OverlapsSection } from './OverlapsSection'

/** The fields of a trusted network, shared by create and edit. */
export const TrustedNetworkInputs = () => {
  // A saved network assigns policies in its Policies section.
  const isNew = useRecordContext()?.id === undefined

  return (
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
      <OutgoingModeInput />
      {isNew && <NewPoliciesInput />}
    </>
  )
}
