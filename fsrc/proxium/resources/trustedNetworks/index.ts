import LanIcon from '@mui/icons-material/Lan'
import type { ResourceProps } from 'react-admin'

import { TrustedNetworkList } from './TrustedNetworkList'
import { TrustedNetworkEdit } from './TrustedNetworkEdit'
import { TrustedNetworkCreate } from './TrustedNetworkCreate'

// No show page: every field fits the edit form.
export const trustedNetworks: ResourceProps = {
  name: 'trusted-networks',
  options: { label: 'Trusted networks' },
  icon: LanIcon,
  list: TrustedNetworkList,
  edit: TrustedNetworkEdit,
  create: TrustedNetworkCreate,
  recordRepresentation: 'name',
}
