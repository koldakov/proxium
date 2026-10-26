import { DatePicker } from '@mui/x-date-pickers/DatePicker'
import { DateTimePicker } from '@mui/x-date-pickers/DateTimePicker'
import { TimePicker } from '@mui/x-date-pickers/TimePicker'
import dayjs, { type Dayjs } from 'dayjs'
import { type ReactNode, useState } from 'react'
import { InputHelperText, type Validator, useInput } from 'react-admin'

import { AMPM, DATE_FORMAT, DATE_TIME_FORMAT, TIME_FORMAT } from './dates'

// Stored while the picker holds a half-typed value: fails validation instead of reading as empty.
const INVALID = 'invalid'

const complete: Validator = (value) => (value === INVALID ? 'Not complete' : undefined)

interface Codec {
  // The form's value, never empty or invalid, as the picker shows it.
  toPicked: (value: string) => Dayjs
  // A valid picked value as the form keeps it.
  fromPicked: (picked: Dayjs) => string
  // Of the field: as wide as its value, not the form, the icon next to the value.
  width: number
}

export interface PickerInputProps {
  source: string
  label: string
  helperText?: ReactNode
  validate?: Validator | Validator[]
  readOnly?: boolean
  defaultValue?: string
}

/**
 * A picker bound to a form field. The picker keeps its own value while typing: the form gets `INVALID` for a
 * half-typed one, which converted back would reset what was typed.
 */
const usePickerInput = (
  { source, label, helperText, validate = [], readOnly = false, defaultValue }: PickerInputProps,
  { toPicked, fromPicked, width }: Codec,
) => {
  // react-hook-form's field state reads through getters of one object: React Compiler would keep the first error.
  'use no memo'
  const {
    field,
    fieldState: { error, isTouched },
    formState: { isSubmitted },
    isRequired,
  } = useInput({
    source,
    defaultValue,
    validate: [complete, ...(Array.isArray(validate) ? validate : [validate])],
  })
  const toState = (value: string | null | undefined) => ({
    value,
    picked: value && value !== INVALID ? toPicked(value) : null,
  })
  const [state, setState] = useState(() => toState(field.value))

  // Changed outside the picker, e.g. a reset: show the new value.
  let { picked } = state
  if (state.value !== field.value) {
    const next = toState(field.value)
    picked = next.picked
    setState(next)
  }

  const shownError = (isTouched || isSubmitted) && error !== undefined

  return {
    value: picked,
    onChange: (next: Dayjs | null) => {
      const value = next === null ? null : next.isValid() ? fromPicked(next) : INVALID
      setState({ value, picked: next })
      field.onChange(value)
    },
    readOnly,
    slotProps: {
      textField: {
        label,
        required: isRequired,
        onBlur: field.onBlur,
        error: shownError,
        helperText: shownError ? <InputHelperText error={error?.message} /> : helperText,
        size: 'small' as const,
        margin: 'dense' as const,
        fullWidth: false,
        sx: { width, flexShrink: 0 },
      },
    },
  }
}

// As the API takes them, whatever the picker shows.
const API_DATE_FORMAT = 'YYYY-MM-DD'
const API_TIME_FORMAT = 'HH:mm'

const DATE_CODEC: Codec = {
  toPicked: (value) => dayjs(value),
  fromPicked: (picked) => picked.format(API_DATE_FORMAT),
  width: 180,
}

const TIME_CODEC: Codec = {
  toPicked: (value) => dayjs(`2000-01-01T${value}`),
  fromPicked: (picked) => picked.format(API_TIME_FORMAT),
  width: AMPM ? 150 : 130,
}

// The picker shows local time, the API takes an aware ISO string.
const AWARE_CODEC: Codec = {
  toPicked: (value) => dayjs(value),
  fromPicked: (picked) => picked.toISOString(),
  width: AMPM ? 260 : 230,
}

/** A calendar day as `YYYY-MM-DD`, no time zone. */
export const DatePickerInput = (props: PickerInputProps) => (
  <DatePicker format={DATE_FORMAT} {...usePickerInput(props, DATE_CODEC)} />
)

/** A time of day as `HH:mm`, shown in the browser's 12 or 24 hours. */
export const TimePickerInput = (props: PickerInputProps) => (
  <TimePicker format={TIME_FORMAT} ampm={AMPM} {...usePickerInput(props, TIME_CODEC)} />
)

/** A moment picked in local time, kept as an ISO string in UTC. Empty: null. */
export const AwareDateTimeInput = (props: PickerInputProps) => (
  <DateTimePicker format={DATE_TIME_FORMAT} ampm={AMPM} {...usePickerInput(props, AWARE_CODEC)} />
)
