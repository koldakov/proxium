import GroupsIcon from '@mui/icons-material/Groups'
import type { ResourceProps } from 'react-admin'

import { GroupCreate } from './GroupCreate'
import { GroupEdit } from './GroupEdit'
import { GroupList } from './GroupList'

// No show page: every field fits the edit form.
export const groups: ResourceProps = {
  name: 'groups',
  icon: GroupsIcon,
  list: GroupList,
  edit: GroupEdit,
  create: GroupCreate,
  recordRepresentation: 'name',
}
