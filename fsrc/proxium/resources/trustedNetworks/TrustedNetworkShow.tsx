import { Stack } from '@mui/material'
import { Show, SimpleForm } from 'react-admin'

import { PoliciesSection } from '../../components/PoliciesSection'
import { TrafficSection } from '../../components/TrafficSection'
import { TrustedNetworkInputs } from './TrustedNetworkInputs'
import { TrustedNetworksWarning } from './TrustedNetworksWarning'

/** The edit page, read-only: for those who may only view trusted networks. */
export const TrustedNetworkShow = () => (
  <>
    <TrustedNetworksWarning />
    <Show>
      <SimpleForm toolbar={false}>
        <TrustedNetworkInputs readOnly />
      </SimpleForm>
      <Stack spacing={2} sx={{ p: 2 }}>
        <PoliciesSection />
        <TrafficSection />
      </Stack>
    </Show>
  </>
)
