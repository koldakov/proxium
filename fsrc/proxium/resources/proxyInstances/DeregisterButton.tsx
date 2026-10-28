import VisibilityOffIcon from '@mui/icons-material/VisibilityOff'
import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import {
  Button,
  Confirm,
  useCanAccess,
  useDataProvider,
  useNotify,
  useRecordContext,
  useRefresh,
  useResourceContext,
} from 'react-admin'

import { ConfirmContent } from '../../components/ConfirmContent'
import type { ProxiumDataProvider } from '../../providers'

/**
 * Takes the instance in context off the list. Only for stopped and unknown ones: a live one would be back on its
 * next report. Hidden without `deregister`.
 */
export const DeregisterButton = () => {
  const record = useRecordContext()
  const resource = useResourceContext()
  const dataProvider = useDataProvider<ProxiumDataProvider>()
  const notify = useNotify()
  const refresh = useRefresh()
  const [confirming, setConfirming] = useState(false)
  const { canAccess } = useCanAccess({ resource, action: 'deregister' })

  const { mutate, isPending, error, reset } = useMutation({
    mutationFn: () => dataProvider.deregister(resource!, { id: record!.id }),
    onSuccess: () => {
      setConfirming(false)
      notify('Deregistered', { type: 'success' })
      refresh()
    },
  })
  const close = () => {
    setConfirming(false)
    reset()
  }

  if (record === undefined || !['stopped', 'unknown'].includes(record.status) || !canAccess) {
    return null
  }

  return (
    <>
      <Button
        label="Deregister"
        onClick={(event) => {
          // In a table row: the click mustn't open the row too.
          event.stopPropagation()
          setConfirming(true)
        }}
      >
        <VisibilityOffIcon />
      </Button>
      <Confirm
        isOpen={confirming}
        loading={isPending}
        title={`Deregister ${record.hostname}`}
        content={
          <ConfirmContent
            text="The instance is taken off the list, e.g. a removed server. If its proxy reports again, it's back."
            error={error}
          />
        }
        onConfirm={() => mutate()}
        onClose={close}
      />
    </>
  )
}
