import PeopleIcon from '@mui/icons-material/People'
import type { ResourceProps } from 'react-admin'

import { UserList } from './UserList'
import { UserShow } from './UserShow'
import { UserCreate } from './UserCreate'

// No edit: the API updates only the logged-in user.
export const users: ResourceProps = {
  name: 'users',
  icon: PeopleIcon,
  list: UserList,
  show: UserShow,
  create: UserCreate,
  recordRepresentation: 'email',
}
