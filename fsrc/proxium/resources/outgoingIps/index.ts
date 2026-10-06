import PublicIcon from '@mui/icons-material/Public'
import type { ResourceProps } from 'react-admin'

import { OutgoingIPList } from './OutgoingIPList'
import { OutgoingIPShow } from './OutgoingIPShow'
import { OutgoingIPEdit } from './OutgoingIPEdit'
import { OutgoingIPCreate } from './OutgoingIPCreate'

// The show page is the edit form, read-only.
export const outgoingIps: ResourceProps = {
  name: 'outgoing-ips',
  options: { label: 'Outgoing IPs' },
  icon: PublicIcon,
  list: OutgoingIPList,
  show: OutgoingIPShow,
  edit: OutgoingIPEdit,
  create: OutgoingIPCreate,
  recordRepresentation: 'ip',
}
