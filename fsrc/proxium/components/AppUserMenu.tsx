import PersonIcon from '@mui/icons-material/Person'
import { ListItemIcon, ListItemText, MenuItem } from '@mui/material'
import { Logout, UserMenu, useUserMenu } from 'react-admin'
import { Link } from 'react-router-dom'

const ProfileMenuItem = ({ to }: { to: string }) => {
  const userMenu = useUserMenu()

  return (
    <MenuItem component={Link} to={to} onClick={userMenu?.onClose}>
      <ListItemIcon>
        <PersonIcon fontSize="small" />
      </ListItemIcon>
      <ListItemText>Profile</ListItemText>
    </MenuItem>
  )
}

/** The top right menu: the user's own profile, open to everyone, then logout. */
export const AppUserMenu = ({ profilePath }: { profilePath: string }) => (
  <UserMenu>
    <ProfileMenuItem to={profilePath} />
    <Logout />
  </UserMenu>
)
