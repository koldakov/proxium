import { type ReactElement, useState } from 'react'
import { Confirm, type RaRecord, SimpleForm, useRecordContext, useSaveContext } from 'react-admin'

import { isOpenToEveryone } from './everyone'
import { TrustedNetworkInputs } from './TrustedNetworkInputs'

interface PendingConfirmation {
  network: string
  resolve: (confirmed: boolean) => void
}

interface TrustedNetworkFormProps {
  toolbar?: ReactElement
  defaultValues?: Partial<RaRecord>
}

/**
 * The trusted network form. A save that opens the proxy to everyone waits for a confirmation first:
 * not turning an open network off or renaming it. Enter submits through it too.
 */
export const TrustedNetworkForm = ({ toolbar, defaultValues }: TrustedNetworkFormProps) => {
  const record = useRecordContext()
  const { save } = useSaveContext()
  const [pending, setPending] = useState<PendingConfirmation | null>(null)

  // Errors it returns land next to the inputs, as with the default save.
  const handleSubmit = async (values: Partial<RaRecord>) => {
    if (isOpenToEveryone(values) && !isOpenToEveryone(record)) {
      const confirmed = await new Promise<boolean>((resolve) =>
        setPending({ network: values.network, resolve }),
      )
      setPending(null)
      if (!confirmed) {
        return undefined
      }
    }
    return save?.(values)
  }

  return (
    <>
      <SimpleForm onSubmit={handleSubmit} toolbar={toolbar} defaultValues={defaultValues}>
        <TrustedNetworkInputs />
      </SimpleForm>
      <Confirm
        isOpen={pending !== null}
        title="Trust the whole internet?"
        content={`${pending?.network} lets anyone on the internet use the proxy without a password.`}
        confirm="Save"
        onConfirm={() => pending?.resolve(true)}
        onClose={() => pending?.resolve(false)}
      />
    </>
  )
}
