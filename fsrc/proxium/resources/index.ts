import VpnKeyIcon from '@mui/icons-material/VpnKey'
import type { ResourceProps } from 'react-admin'

import type { MenuNode } from '../components/GroupedMenu'
import { basicProxyAccounts } from './basicProxyAccounts'
import { certificates } from './certificates'
import { outgoingIps } from './outgoingIps'
import { tokenProxyAccounts } from './tokenProxyAccounts'
import { trustedNetworks } from './trustedNetworks'
import { users } from './users'

// The admin registry: a new section is one more entry here and in the menu.
export const resources: ResourceProps[] = [
  basicProxyAccounts,
  tokenProxyAccounts,
  trustedNetworks,
  outgoingIps,
  certificates,
  users,
]

// The sidebar, in order.
export const menu: MenuNode[] = [
  {
    label: 'Proxy accounts',
    icon: VpnKeyIcon,
    items: [
      { resource: basicProxyAccounts.name, label: 'Basic' },
      { resource: tokenProxyAccounts.name, label: 'Token' },
    ],
  },
  trustedNetworks.name,
  outgoingIps.name,
  certificates.name,
  users.name,
]
