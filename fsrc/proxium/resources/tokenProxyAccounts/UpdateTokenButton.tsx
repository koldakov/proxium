import AutorenewIcon from '@mui/icons-material/Autorenew'
import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import {
  Button,
  Confirm,
  useDataProvider,
  useNotify,
  useRecordContext,
  useRefresh,
  useResourceContext,
} from 'react-admin'

import { SecretDialog } from '../../components/SecretDialog'
import type { ProxiumDataProvider } from '../../providers'

export const UpdateTokenButton = () => {
  const record = useRecordContext()
  const resource = useResourceContext()
  const dataProvider = useDataProvider<ProxiumDataProvider>()
  const notify = useNotify()
  const refresh = useRefresh()
  const [confirming, setConfirming] = useState(false)
  const [token, setToken] = useState<string | null>(null)

  const { mutate, isPending } = useMutation({
    mutationFn: () => dataProvider.updateToken(resource!, { id: record!.id }),
    onSuccess: (result) => {
      setConfirming(false)
      setToken(result.token)
      // The key changes with the token.
      refresh()
    },
    onError: (error: Error) => notify(error.message, { type: 'error' }),
  })

  if (record === undefined) {
    return null
  }

  return (
    <>
      <Button label="Regenerate token" onClick={() => setConfirming(true)}>
        <AutorenewIcon />
      </Button>
      <Confirm
        isOpen={confirming}
        loading={isPending}
        title="Regenerate token"
        content="The current token stops working right away."
        onConfirm={() => mutate()}
        onClose={() => setConfirming(false)}
      />
      {token !== null && (
        <SecretDialog title="New token" secret={token} onClose={() => setToken(null)} />
      )}
    </>
  )
}
