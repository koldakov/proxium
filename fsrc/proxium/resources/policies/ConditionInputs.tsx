import {
  Checkbox,
  Divider,
  MenuItem,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material'
import {
  ArrayInput,
  AutocompleteInput,
  CheckboxGroupInput,
  FormDataConsumer,
  InputHelperText,
  SelectInput,
  SimpleFormIterator,
  TextInput,
  required,
  useInput,
} from 'react-admin'

import {
  CONDITION_KINDS,
  CONDITION_MATCHES,
  LIST_HELPER,
  PROTOCOLS,
  TIME_ZONES,
  WEEKDAYS,
  browserTimeZone,
  domainsList,
  networksList,
  portsList,
} from './conditions'
import { AddButton } from './RuleCard'
import { ROWS_SX } from './rows'
import { describeDays } from './summary'

// The time input shows a placeholder of its own: the label stays above it.
const SHRUNK_LABEL = { inputLabel: { shrink: true } }

/** Whether a check is negated, as the word before it: "If" it matches or "Unless" it does. */
const NegateInput = ({ readOnly }: { readOnly: boolean }) => {
  const { field } = useInput({ source: 'negate', defaultValue: false })
  return (
    <ToggleButtonGroup
      exclusive
      size="small"
      value={field.value ? 'unless' : 'if'}
      disabled={readOnly}
      onChange={(_, value: string | null) => value !== null && field.onChange(value === 'unless')}
      // In line with the inputs, which have a margin above.
      sx={{ mt: 1, height: 40 }}
    >
      <ToggleButton value="if">If</ToggleButton>
      <ToggleButton value="unless">Unless</ToggleButton>
    </ToggleButtonGroup>
  )
}

// Picked from the top of the days list, they replace the days chosen.
const DAY_PRESETS = [
  { id: 'weekdays', name: 'Weekdays', days: [1, 2, 3, 4, 5] },
  { id: 'weekends', name: 'Weekends', days: [6, 7] },
  { id: 'everyDay', name: 'Every day', days: [1, 2, 3, 4, 5, 6, 7] },
]

/** Weekdays as a dropdown that reads like the summary when closed, e.g. Mon–Fri. */
const DaysInput = ({ readOnly }: { readOnly: boolean }) => {
  const {
    field,
    fieldState: { error, isTouched },
    formState: { isSubmitted },
  } = useInput({ source: 'days', defaultValue: DAY_PRESETS[0].days, validate: required() })
  const shownError = (isTouched || isSubmitted) && error !== undefined

  const change = (value: (number | string)[]) => {
    const preset = DAY_PRESETS.find((choice) => value.includes(choice.id))
    const days = preset?.days ?? value.filter((item) => typeof item === 'number')
    field.onChange([...days].sort((a, b) => a - b))
  }

  return (
    <TextField
      select
      label="Days"
      value={field.value ?? []}
      onChange={(event) => change(event.target.value as unknown as (number | string)[])}
      onBlur={field.onBlur}
      error={shownError}
      helperText={shownError && <InputHelperText error={error?.message} />}
      sx={{ minWidth: 150 }}
      slotProps={{
        input: { readOnly },
        select: {
          multiple: true,
          renderValue: (days) => describeDays(days as number[]),
        },
      }}
    >
      {DAY_PRESETS.map((preset) => (
        <MenuItem key={preset.id} value={preset.id}>
          {preset.name}
        </MenuItem>
      ))}
      <Divider />
      {WEEKDAYS.map((day) => (
        <MenuItem key={day.id} value={day.id}>
          <Checkbox
            size="small"
            checked={(field.value ?? []).includes(day.id)}
            sx={{ p: 0, mr: 1 }}
          />
          {day.name}
        </MenuItem>
      ))}
    </TextField>
  )
}

/** The fields of one check, by its kind. */
const BlockParams = ({ readOnly }: { readOnly: boolean }) => (
  <FormDataConsumer>
    {({ scopedFormData }) => {
      switch (scopedFormData?.kind) {
        case 'schedule':
          return (
            <>
              <DaysInput readOnly={readOnly} />
              <TextInput
                source="start"
                type="time"
                defaultValue="09:00"
                slotProps={SHRUNK_LABEL}
                readOnly={readOnly}
                validate={required()}
              />
              <TextInput
                source="end"
                type="time"
                defaultValue="18:00"
                slotProps={SHRUNK_LABEL}
                readOnly={readOnly}
                validate={required()}
                helperText="Before the start: till the next day. Same as the start: all day"
              />
              <AutocompleteInput
                source="timezone"
                label="Time zone"
                choices={TIME_ZONES}
                defaultValue={browserTimeZone()}
                readOnly={readOnly}
                validate={required()}
              />
            </>
          )
        case 'target_host':
          return (
            <TextInput
              source="domains"
              multiline
              readOnly={readOnly}
              validate={domainsList()}
              helperText={`Subdomains match too. ${LIST_HELPER}`}
            />
          )
        case 'target_network':
          return (
            <TextInput
              source="networks"
              multiline
              readOnly={readOnly}
              validate={networksList()}
              helperText={`When the client asks for an IP, not a name. ${LIST_HELPER}`}
            />
          )
        case 'client_network':
          return (
            <TextInput
              source="networks"
              multiline
              readOnly={readOnly}
              validate={networksList()}
              helperText={`Where the client connects from. ${LIST_HELPER}`}
            />
          )
        case 'target_port':
          return (
            <TextInput
              source="ports"
              readOnly={readOnly}
              validate={portsList()}
              helperText="E.g. 80, 443, 8000-8999"
            />
          )
        case 'protocol':
          return (
            <CheckboxGroupInput
              source="protocols"
              choices={PROTOCOLS}
              readOnly={readOnly}
              validate={required()}
            />
          )
        default:
          return null
      }
    }}
  </FormDataConsumer>
)

/** When a rule applies: checks that all must match or any one, none for always. Inside a rule of the form. */
export const ConditionInputs = ({ readOnly }: { readOnly: boolean }) => (
  <FormDataConsumer>
    {({ scopedFormData }) => {
      // A deeper tree than the form shows: saved untouched.
      if (scopedFormData?.complexCondition) {
        return (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Set through the API and kept as is: the form can't show it
          </Typography>
        )
      }

      const count = scopedFormData?.blocks?.length ?? 0
      return (
        <>
          {count === 0 && (
            <Typography variant="body2" color="text.secondary">
              No conditions: the rule always applies
            </Typography>
          )}
          {count > 1 && (
            <SelectInput
              source="match"
              label="Applies when"
              choices={CONDITION_MATCHES}
              defaultValue="all"
              readOnly={readOnly}
              validate={required()}
            />
          )}
          <ArrayInput source="blocks" label={false}>
            <SimpleFormIterator
              inline
              disableReordering
              disableClear
              disabled={readOnly}
              addButton={<AddButton label="Add condition" />}
              sx={ROWS_SX}
            >
              <NegateInput readOnly={readOnly} />
              <SelectInput
                source="kind"
                label="Condition"
                choices={CONDITION_KINDS}
                readOnly={readOnly}
                validate={required()}
              />
              <BlockParams readOnly={readOnly} />
            </SimpleFormIterator>
          </ArrayInput>
        </>
      )
    }}
  </FormDataConsumer>
)
