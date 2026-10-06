import { DeleteButton, Edit, SaveButton, SimpleForm, Toolbar } from 'react-admin'

import { toPolicyData } from './limits'
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

// The proxy applies a change to new connections within seconds, open ones keep the limits they started with.
export const PolicyEdit = () => (
  <Edit redirect="list" mutationMode="pessimistic" transform={toPolicyData}>
    <SimpleForm toolbar={<EditToolbar />}>
      <PolicyInputs />
    </SimpleForm>
  </Edit>
)
