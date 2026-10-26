import { useEffect } from 'react'
import { Confirm, SimpleForm, type SimpleFormProps, useBlocker } from 'react-admin'
import { useFormState } from 'react-hook-form'

/**
 * Asks before leaving a changed form, in place of react-admin's `warnWhenUnsavedChanges`,
 * which asks with the browser's own `confirm`. Render it inside the form.
 */
export const UnsavedChangesGuard = () => {
  // react-hook-form changes `dirtyFields` in place: React Compiler would keep the first, empty, count.
  'use no memo'
  const { isSubmitSuccessful, dirtyFields } = useFormState()
  const isDirty = Object.keys(dirtyFields).length > 0
  const shouldBlock = isDirty && !isSubmitSuccessful

  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      shouldBlock && nextLocation.pathname !== currentLocation.pathname,
  )

  // A save or delete resets the form in the same tick it redirects: let that redirect through.
  useEffect(() => {
    if (blocker.state === 'blocked' && !shouldBlock) {
      blocker.proceed()
    }
  }, [blocker, shouldBlock])

  // Reloading or closing the tab: only the browser's own dialog can ask then.
  useEffect(() => {
    if (!shouldBlock) {
      return undefined
    }
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      // Older browsers ask only when it's set.
      event.returnValue = true
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [shouldBlock])

  return (
    <Confirm
      isOpen={blocker.state === 'blocked' && shouldBlock}
      title="Leave without saving?"
      content="Changes on this page will be lost."
      confirm="Leave"
      cancel="Stay"
      confirmColor="warning"
      onConfirm={() => blocker.state === 'blocked' && blocker.proceed()}
      onClose={() => blocker.state === 'blocked' && blocker.reset()}
    />
  )
}

/** `SimpleForm` that asks before leaving it changed: for every form that saves. */
export const GuardedSimpleForm = ({ children, ...props }: SimpleFormProps) => (
  <SimpleForm {...props}>
    {children}
    <UnsavedChangesGuard />
  </SimpleForm>
)
