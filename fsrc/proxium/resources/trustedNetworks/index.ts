import LanIcon from '@mui/icons-material/Lan'
import type { ResourceProps } from 'react-admin'

import { TrustedNetworkList } from './TrustedNetworkList'
import { TrustedNetworkShow } from './TrustedNetworkShow'
import { TrustedNetworkEdit } from './TrustedNetworkEdit'
import { TrustedNetworkCreate } from './TrustedNetworkCreate'

// The show page is the edit page, read-only.
export const trustedNetworks: ResourceProps = {
  name: 'trusted-networks',
  options: { label: 'Trusted networks' },
  icon: LanIcon,
  list: TrustedNetworkList,
  show: TrustedNetworkShow,
  edit: TrustedNetworkEdit,
  create: TrustedNetworkCreate,
  recordRepresentation: 'name',
}
