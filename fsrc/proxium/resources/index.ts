import AdminPanelSettingsIcon from '@mui/icons-material/AdminPanelSettings'
import VpnKeyIcon from '@mui/icons-material/VpnKey'
import type { ResourceProps } from 'react-admin'

import type { MenuNode } from '../components/GroupedMenu'
import { overviewLink } from '../pages/overview'
import { settingsLink } from '../pages/settings'
import { basicProxyAccounts } from './basicProxyAccounts'
import { certificates } from './certificates'
import { groups } from './groups'
import { outgoingIps } from './outgoingIps'
import { policies } from './policies'
import { proxyInstances } from './proxyInstances'
import { tokenProxyAccounts } from './tokenProxyAccounts'
import { trustedNetworks } from './trustedNetworks'
import { users } from './users'

// The admin registry: a new section is one more entry here and in the menu.
export const resources: ResourceProps[] = [
  basicProxyAccounts,
  tokenProxyAccounts,
  trustedNetworks,
  outgoingIps,
  policies,
  certificates,
  proxyInstances,
  users,
  groups,
]

// The sidebar, in order. Proxy instances are under the overview, the rest is what the admin configures.
export const menu: MenuNode[] = [
  overviewLink,
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
  policies.name,
  certificates.name,
  {
    label: 'Access',
    icon: AdminPanelSettingsIcon,
    items: [
      { resource: users.name, label: 'Users' },
      { resource: groups.name, label: 'Groups' },
    ],
  },
  settingsLink,
]
