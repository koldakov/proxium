import { Stack } from '@mui/material'
import { Edit, TextInput, required } from 'react-admin'

import { NoDeleteToolbar } from '../../components/NoDeleteToolbar'
import { OutgoingModeInput } from '../../components/OutgoingModeInput'
import { PoliciesSection } from '../../components/PoliciesSection'
import { GuardedSimpleForm } from '../../components/UnsavedChangesGuard'

// The name, the outgoing mode and its pool change, the token is immutable.
// Policies apply at once, outside the form.
export const TokenProxyAccountEdit = () => (
  <Edit redirect="show" mutationMode="pessimistic">
    <GuardedSimpleForm toolbar={<NoDeleteToolbar />}>
      <TextInput source="name" validate={required()} />
      <OutgoingModeInput />
    </GuardedSimpleForm>
    <Stack sx={{ p: 2 }}>
      <PoliciesSection />
    </Stack>
  </Edit>
)
