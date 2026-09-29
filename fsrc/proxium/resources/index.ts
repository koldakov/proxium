import VpnKeyIcon from '@mui/icons-material/VpnKey'
import type { ResourceProps } from 'react-admin'

import type { MenuNode } from '../components/GroupedMenu'
import { basicProxyAccounts } from './basicProxyAccounts'
import { tokenProxyAccounts } from './tokenProxyAccounts'
import { users } from './users'

// The admin registry: a new section is one more entry here and in the menu.
export const resources: ResourceProps[] = [basicProxyAccounts, tokenProxyAccounts, users]

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
  users.name,
]
