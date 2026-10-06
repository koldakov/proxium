import { Stack } from '@mui/material'
import { Edit, SimpleForm, TextInput, required } from 'react-admin'

import { NoDeleteToolbar } from '../../components/NoDeleteToolbar'
import { OutgoingModeInput } from '../../components/OutgoingModeInput'
import { PoliciesSection } from '../../components/PoliciesSection'

// The name, the outgoing mode and its pool change, the credentials are immutable.
// Policies apply at once, outside the form.
export const BasicProxyAccountEdit = () => (
  <Edit redirect="show" mutationMode="pessimistic">
    <SimpleForm toolbar={<NoDeleteToolbar />}>
      <TextInput source="name" validate={required()} />
      <OutgoingModeInput />
    </SimpleForm>
    <Stack sx={{ p: 2 }}>
      <PoliciesSection />
    </Stack>
  </Edit>
)
