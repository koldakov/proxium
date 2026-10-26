import { useMemo } from 'react'
import { useRecordContext } from 'react-admin'
import type { SimpleFormProps } from 'react-admin'

import { GuardedSimpleForm } from '../../components/UnsavedChangesGuard'
import { toFormPolicy } from './conditions'

/** A form of the loaded policy as `PolicyInputs` edit it: rule conditions split into form fields. */
export const PolicyForm = (props: SimpleFormProps) => {
  const record = useRecordContext()
  // The form resets when the record changes: a new object on every render would wipe the edits.
  const formRecord = useMemo(() => (record ? toFormPolicy(record) : undefined), [record])
  return <GuardedSimpleForm record={formRecord} {...props} />
}
