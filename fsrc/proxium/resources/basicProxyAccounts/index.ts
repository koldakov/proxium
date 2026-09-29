import KeyIcon from '@mui/icons-material/Key'
import type { ResourceProps } from 'react-admin'

import { BasicProxyAccountList } from './BasicProxyAccountList'
import { BasicProxyAccountShow } from './BasicProxyAccountShow'
import { BasicProxyAccountEdit } from './BasicProxyAccountEdit'
import { BasicProxyAccountCreate } from './BasicProxyAccountCreate'

export const basicProxyAccounts: ResourceProps = {
  name: 'basic-proxy-accounts',
  options: { label: 'Basic proxy accounts' },
  icon: KeyIcon,
  list: BasicProxyAccountList,
  show: BasicProxyAccountShow,
  edit: BasicProxyAccountEdit,
  create: BasicProxyAccountCreate,
  recordRepresentation: 'username',
}
