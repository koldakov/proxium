import { DeleteButton, Edit, SaveButton, Toolbar } from 'react-admin'

import { GuardedSimpleForm } from '../../components/UnsavedChangesGuard'
import { GroupInputs } from './GroupInputs'

const EditToolbar = () => (
  <Toolbar sx={{ justifyContent: 'space-between' }}>
    <SaveButton />
    <DeleteButton
      mutationMode="pessimistic"
      confirmTitle="Delete group"
      confirmContent="Its users lose its permissions right away, the users themselves stay."
    />
  </Toolbar>
)

// Users of the group get a change with their next request.
export const GroupEdit = () => (
  <Edit redirect="list" mutationMode="pessimistic">
    <GuardedSimpleForm toolbar={<EditToolbar />}>
      <GroupInputs />
    </GuardedSimpleForm>
  </Edit>
)
