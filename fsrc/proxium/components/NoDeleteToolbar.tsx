import { SaveButton, Toolbar } from 'react-admin'

/** Form toolbar for resources the API can't delete. */
export const NoDeleteToolbar = () => (
  <Toolbar>
    <SaveButton />
  </Toolbar>
)
