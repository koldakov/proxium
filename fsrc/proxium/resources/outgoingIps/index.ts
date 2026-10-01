import PublicIcon from '@mui/icons-material/Public'
import type { ResourceProps } from 'react-admin'

import { OutgoingIPList } from './OutgoingIPList'
import { OutgoingIPEdit } from './OutgoingIPEdit'
import { OutgoingIPCreate } from './OutgoingIPCreate'

// No show page: every field fits the edit form.
export const outgoingIps: ResourceProps = {
  name: 'outgoing-ips',
  options: { label: 'Outgoing IPs' },
  icon: PublicIcon,
  list: OutgoingIPList,
  edit: OutgoingIPEdit,
  create: OutgoingIPCreate,
  recordRepresentation: 'ip',
}
