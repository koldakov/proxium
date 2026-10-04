import BlockIcon from '@mui/icons-material/Block'
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

import type { ProxiumDataProvider } from '../providers'

/** Revokes the proxy account in context for good. Hidden once revoked or without `revoke`. */
export const RevokeButton = () => {
  const record = useRecordContext()
  const resource = useResourceContext()
  const dataProvider = useDataProvider<ProxiumDataProvider>()
  const notify = useNotify()
  const refresh = useRefresh()
  const [confirming, setConfirming] = useState(false)
  const { canAccess } = useCanAccess({ resource, action: 'revoke' })

  const { mutate, isPending } = useMutation({
    mutationFn: () => dataProvider.revoke(resource!, { id: record!.id }),
    onSuccess: () => {
      setConfirming(false)
      notify('Revoked', { type: 'success' })
      refresh()
    },
    onError: (error: Error) => notify(error.message, { type: 'error' }),
  })

  if (record === undefined || !record.isActive || !canAccess) {
    return null
  }

  return (
    <>
      <Button label="Revoke" color="error" onClick={() => setConfirming(true)}>
        <BlockIcon />
      </Button>
      <Confirm
        isOpen={confirming}
        loading={isPending}
        title="Revoke"
        content="The credentials stop working right away and can't be restored."
        onConfirm={() => mutate()}
        onClose={() => setConfirming(false)}
      />
    </>
  )
}
