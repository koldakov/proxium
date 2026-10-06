import PolicyIcon from '@mui/icons-material/Policy'
import type { ResourceProps } from 'react-admin'

import { PolicyCreate } from './PolicyCreate'
import { PolicyEdit } from './PolicyEdit'
import { PolicyList } from './PolicyList'
import { PolicyShow } from './PolicyShow'

// The show page is the edit form, read-only.
export const policies: ResourceProps = {
  name: 'policies',
  icon: PolicyIcon,
  list: PolicyList,
  show: PolicyShow,
  edit: PolicyEdit,
  create: PolicyCreate,
  recordRepresentation: 'name',
}
