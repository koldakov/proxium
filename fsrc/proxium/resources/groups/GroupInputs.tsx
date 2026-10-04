import { TextInput, required } from 'react-admin'

import { PermissionsInput } from '../../components/PermissionsInput'

export const GroupInputs = () => (
  <>
    <TextInput source="name" validate={required()} helperText="E.g. Operators, Read only" />
    <PermissionsInput />
  </>
)
