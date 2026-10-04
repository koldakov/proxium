import PeopleIcon from '@mui/icons-material/People'
import type { ResourceProps } from 'react-admin'

import { UserList } from './UserList'
import { UserShow } from './UserShow'
import { UserCreate } from './UserCreate'
import { UserEdit } from './UserEdit'

export const users: ResourceProps = {
  name: 'users',
  icon: PeopleIcon,
  list: UserList,
  show: UserShow,
  edit: UserEdit,
  create: UserCreate,
  recordRepresentation: 'email',
}
