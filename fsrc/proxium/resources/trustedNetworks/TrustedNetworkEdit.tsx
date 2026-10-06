import { Stack } from '@mui/material'
import { DeleteButton, Edit, SaveButton, Toolbar } from 'react-admin'

import { PoliciesSection } from '../../components/PoliciesSection'
import { TrafficSection } from '../../components/TrafficSection'
import { DeleteConfirmContent } from './DeleteConfirmContent'
import { TrustedNetworkForm } from './TrustedNetworkForm'
import { TrustedNetworksWarning } from './TrustedNetworksWarning'

const EditToolbar = () => (
  <Toolbar sx={{ justifyContent: 'space-between' }}>
    <SaveButton />
    <DeleteButton
      mutationMode="pessimistic"
      confirmTitle="Delete network"
      confirmContent={<DeleteConfirmContent />}
    />
  </Toolbar>
)

export const TrustedNetworkEdit = () => (
  <>
    <TrustedNetworksWarning />
    <Edit redirect="list" mutationMode="pessimistic">
      <TrustedNetworkForm toolbar={<EditToolbar />} />
      <Stack spacing={2} sx={{ p: 2 }}>
        <PoliciesSection />
        <TrafficSection />
      </Stack>
    </Edit>
  </>
)
