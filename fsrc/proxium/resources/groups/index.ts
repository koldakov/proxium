import GroupsIcon from '@mui/icons-material/Groups'
import type { ResourceProps } from 'react-admin'

import { GroupCreate } from './GroupCreate'
import { GroupEdit } from './GroupEdit'
import { GroupList } from './GroupList'
import { GroupShow } from './GroupShow'

// The show page is the edit form, read-only.
export const groups: ResourceProps = {
  name: 'groups',
  icon: GroupsIcon,
  list: GroupList,
  show: GroupShow,
  edit: GroupEdit,
  create: GroupCreate,
  recordRepresentation: 'name',
}
