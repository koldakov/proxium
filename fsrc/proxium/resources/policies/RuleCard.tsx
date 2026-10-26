import AddIcon from '@mui/icons-material/Add'
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward'
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import ExpandLessIcon from '@mui/icons-material/ExpandLess'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import {
  Avatar,
  Box,
  Button,
  Card,
  Chip,
  IconButton,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material'
import { type ReactNode, useState } from 'react'
import {
  FormDataConsumer,
  TextInput,
  required,
  useSimpleFormIterator,
  useSimpleFormIteratorItem,
} from 'react-admin'
import { useFormState } from 'react-hook-form'

import { describeConditions, describeLimits } from './summary'

/** An iterator's add button with its label shown: react-admin's shows only an icon, the label as a tooltip. */
export const AddButton = ({
  label,
  variant = 'text',
}: {
  label: string
  variant?: 'text' | 'outlined'
}) => {
  const { add } = useSimpleFormIterator()
  return (
    <Button size="small" variant={variant} startIcon={<AddIcon />} onClick={() => add()}>
      {label}
    </Button>
  )
}

const SummaryLine = ({ label, text }: { label: string; text: string }) => (
  <Stack direction="row" spacing={1.5} alignItems="baseline">
    <Typography variant="overline" color="text.secondary" sx={{ minWidth: 40, lineHeight: 1.6 }}>
      {label}
    </Typography>
    <Typography variant="body2">{text}</Typography>
  </Stack>
)

/** A collapsed card hides its fields: it says so when one of them is wrong. */
const ErrorsChip = ({ index }: { index: number }) => {
  // react-hook-form changes `errors` in place: React Compiler would keep the first, empty, one.
  'use no memo'
  const { errors } = useFormState({ name: `rules.${index}` })
  const hasErrors = Array.isArray(errors.rules) && errors.rules[index] !== undefined
  return hasErrors ? <Chip label="Has errors" color="error" size="small" /> : null
}

interface RuleCardProps {
  readOnly: boolean
  // Under the summary, shown collapsed too.
  notice: ReactNode
  // The rule's fields under the summary.
  children: ReactNode
}

/**
 * One rule of a policy in a card: its number and name, a summary of when it applies and what it limits, its fields
 * below. Collapses to the summary, as it starts on the read-only page. Inside the rules iterator.
 */
export const RuleCard = ({ readOnly, notice, children }: RuleCardProps) => {
  const { index, total, remove, reOrder } = useSimpleFormIteratorItem()
  const [expanded, setExpanded] = useState(!readOnly)

  return (
    <Card sx={{ p: 2, mb: 2 }}>
      <Stack direction="row" spacing={1.5} alignItems="flex-start">
        <Avatar
          sx={{ width: 28, height: 28, mt: 1.25, fontSize: 14, bgcolor: 'primary.main' }}
          aria-label={`Rule ${index + 1}`}
        >
          {index + 1}
        </Avatar>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          {readOnly ? (
            <FormDataConsumer>
              {({ scopedFormData }) => (
                <Typography variant="subtitle1" sx={{ mt: 1 }}>
                  {scopedFormData?.name}
                </Typography>
              )}
            </FormDataConsumer>
          ) : (
            <TextInput
              source="name"
              label="Rule name"
              validate={required()}
              helperText="E.g. Working hours"
              sx={{ maxWidth: 420 }}
            />
          )}
        </Box>
        <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 1 }}>
          {!expanded && <ErrorsChip index={index} />}
          {/* Order matters: the first matching rule applies. Spans: a tooltip needs an enabled child. */}
          {!readOnly && (
            <>
              <Tooltip title="Move up">
                <span>
                  <IconButton
                    onClick={() => reOrder(index - 1)}
                    disabled={index === 0}
                    size="small"
                  >
                    <ArrowUpwardIcon fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
              <Tooltip title="Move down">
                <span>
                  <IconButton
                    onClick={() => reOrder(index + 1)}
                    disabled={index === total - 1}
                    size="small"
                  >
                    <ArrowDownwardIcon fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
            </>
          )}
          <Tooltip title={expanded ? 'Collapse' : 'Expand'}>
            <IconButton onClick={() => setExpanded(!expanded)} size="small">
              {expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            </IconButton>
          </Tooltip>
          {!readOnly && (
            <Tooltip title="Delete rule">
              <IconButton onClick={remove} size="small">
                <DeleteOutlineIcon />
              </IconButton>
            </Tooltip>
          )}
        </Stack>
      </Stack>

      <FormDataConsumer>
        {({ scopedFormData }) =>
          scopedFormData && (
            <Box sx={{ mt: 1, ml: 5.5 }}>
              <SummaryLine label="When" text={describeConditions(scopedFormData)} />
              <SummaryLine label="Limit" text={describeLimits(scopedFormData)} />
            </Box>
          )
        }
      </FormDataConsumer>
      <Box sx={{ ml: 5.5 }}>{notice}</Box>

      {/* Hidden, not unmounted: the fields keep validating while collapsed. */}
      <Box sx={{ display: expanded ? 'block' : 'none', mt: 2, ml: { md: 5.5 } }}>{children}</Box>
    </Card>
  )
}
