import { DeleteButton, Edit, SaveButton, SimpleForm, Toolbar } from 'react-admin'

import { OutgoingIPInputs } from './OutgoingIPInputs'

const EditToolbar = () => (
  <Toolbar sx={{ justifyContent: 'space-between' }}>
    <SaveButton />
    <DeleteButton
      mutationMode="pessimistic"
      confirmTitle="Delete IP"
      confirmContent="An IP in a pool can't be deleted: take it out of the pools first."
    />
  </Toolbar>
)

// A changed IP applies to every pool with it, on new connections.
export const OutgoingIPEdit = () => (
  <Edit redirect="list" mutationMode="pessimistic">
    <SimpleForm toolbar={<EditToolbar />}>
      <OutgoingIPInputs />
    </SimpleForm>
  </Edit>
)
