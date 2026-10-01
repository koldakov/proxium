import { Create } from 'react-admin'

import { TrustedNetworkForm } from './TrustedNetworkForm'
import { TrustedNetworksWarning } from './TrustedNetworksWarning'

export const TrustedNetworkCreate = () => (
  <>
    <TrustedNetworksWarning />
    <Create redirect="list">
      <TrustedNetworkForm defaultValues={{ isActive: true, outgoingMode: 'system' }} />
    </Create>
  </>
)
