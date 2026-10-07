import { DeleteButton, Edit, SaveButton, Toolbar } from 'react-admin'

import { toPolicyData } from './limits'
import { PolicyForm } from './PolicyForm'
import { PolicyInputs } from './PolicyInputs'

const EditToolbar = () => (
  <Toolbar sx={{ justifyContent: 'space-between' }}>
    <SaveButton />
    <DeleteButton
      mutationMode="pessimistic"
      confirmTitle="Delete policy"
      confirmContent="It's taken off every account and network, which lose its limits within seconds."
    />
  </Toolbar>
)

// The proxy applies a change to new connections within seconds, open ones keep the rules they started with.
export const PolicyEdit = () => (
  <Edit redirect="list" mutationMode="pessimistic" transform={toPolicyData}>
    <PolicyForm toolbar={<EditToolbar />}>
      <PolicyInputs />
    </PolicyForm>
  </Edit>
)
