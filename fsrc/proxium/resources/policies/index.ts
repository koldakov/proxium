import PolicyIcon from '@mui/icons-material/Policy'
import type { ResourceProps } from 'react-admin'

import { PolicyCreate } from './PolicyCreate'
import { PolicyEdit } from './PolicyEdit'
import { PolicyList } from './PolicyList'

// No show page: every field fits the edit form.
export const policies: ResourceProps = {
  name: 'policies',
  icon: PolicyIcon,
  list: PolicyList,
  edit: PolicyEdit,
  create: PolicyCreate,
  recordRepresentation: 'name',
}
