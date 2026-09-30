import { Box } from '@mui/material'
import { DeleteButton, Edit, SaveButton, Toolbar } from 'react-admin'

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
      <Box sx={{ p: 2 }}>
        <TrafficSection />
      </Box>
    </Edit>
  </>
)
