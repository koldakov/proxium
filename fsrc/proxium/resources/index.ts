import type { ResourceProps } from 'react-admin'

import { basicProxyAccounts } from './basicProxyAccounts'
import { tokenProxyAccounts } from './tokenProxyAccounts'
import { users } from './users'

// The admin registry: a new section is one more entry here, in menu order.
export const resources: ResourceProps[] = [basicProxyAccounts, tokenProxyAccounts, users]
