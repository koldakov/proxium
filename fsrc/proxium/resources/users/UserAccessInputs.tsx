import { Typography } from '@mui/material'
import {
  AutocompleteArrayInput,
  BooleanInput,
  type RaRecord,
  ReferenceArrayInput,
  useCanAccess,
  useRecordContext,
} from 'react-admin'

import { useMyPermissions } from '../../components/permissions'
import { PermissionsInput } from '../../components/PermissionsInput'

// An empty query is refused by the API: no filter lists every group.
const toQuery = (query: string) => (query ? { query } : {})

/** Activity, superuser status, groups and own permissions: only what the logged-in user may give. */
export const UserAccessInputs = () => {
  const record = useRecordContext()
  const me = useMyPermissions()
  const { canAccess: canListGroups } = useCanAccess({ resource: 'groups', action: 'list' })
  if (me === undefined) {
    return null
  }

  // Nobody locks themselves out: the API refuses it.
  const isMe = record?.id === me.id
  // A group gives all its permissions at once.
  const isOutOfReach = (group: RaRecord) =>
    !me.isSuperuser && group.permissions.some((code: string) => !me.permissions.includes(code))

  return (
    <>
      <Typography variant="h6">Access</Typography>
      <BooleanInput
        source="isActive"
        label="Active"
        readOnly={isMe}
        helperText={isMe ? "You can't deactivate yourself" : "An inactive user can't log in"}
      />
      {me.isSuperuser && (
        <BooleanInput
          source="isSuperuser"
          label="Superuser"
          readOnly={isMe}
          helperText={
            isMe ? 'Another superuser can take it away' : 'Has every permission, groups aside'
          }
        />
      )}
      {canListGroups && (
        <ReferenceArrayInput source="groupIds" reference="groups">
          <AutocompleteArrayInput
            label="Groups"
            optionText="name"
            filterToQuery={toQuery}
            getOptionDisabled={isOutOfReach}
            helperText={
              me.isSuperuser
                ? 'The user has all their permissions'
                : 'Only groups with the permissions you have yourself'
            }
          />
        </ReferenceArrayInput>
      )}
      <PermissionsInput label="Own permissions, besides the groups'" />
    </>
  )
}
