import { TextInput, required } from 'react-admin'

import { PermissionsInput } from '../../components/PermissionsInput'

// Read-only on the show page, for those who may only view.
export const GroupInputs = ({ readOnly = false }: { readOnly?: boolean }) => (
  <>
    <TextInput
      source="name"
      readOnly={readOnly}
      validate={required()}
      helperText="E.g. Operators, Read only"
    />
    <PermissionsInput readOnly={readOnly} />
  </>
)
