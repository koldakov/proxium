import TokenIcon from '@mui/icons-material/Token'
import type { ResourceProps } from 'react-admin'

import { TokenProxyAccountList } from './TokenProxyAccountList'
import { TokenProxyAccountShow } from './TokenProxyAccountShow'
import { TokenProxyAccountEdit } from './TokenProxyAccountEdit'
import { TokenProxyAccountCreate } from './TokenProxyAccountCreate'

export const tokenProxyAccounts: ResourceProps = {
  name: 'token-proxy-accounts',
  options: { label: 'Token proxy accounts' },
  icon: TokenIcon,
  list: TokenProxyAccountList,
  show: TokenProxyAccountShow,
  edit: TokenProxyAccountEdit,
  create: TokenProxyAccountCreate,
  recordRepresentation: 'name',
}
