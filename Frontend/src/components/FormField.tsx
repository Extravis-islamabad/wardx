import { Form } from 'antd';
import { cloneElement, useId, type ReactElement } from 'react';
import { Controller, type Control, type FieldValues, type Path } from 'react-hook-form';

interface Props<T extends FieldValues> {
  control: Control<T>;
  name: Path<T>;
  label: string;
  extra?: string;
  /** Receives react-hook-form's field props; spread them onto an antd input. */
  render: (field: { value: unknown; onChange: (v: unknown) => void; onBlur: () => void }) => ReactElement;
}

/** antd Form.Item wired to a react-hook-form field, showing its zod error. */
export function FormField<T extends FieldValues>({ control, name, label, extra, render }: Props<T>) {
  // Link the label to its input so screen readers (and getByLabel) find it.
  const id = useId();
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => (
        <Form.Item
          label={label}
          htmlFor={id}
          extra={extra}
          validateStatus={fieldState.error ? 'error' : undefined}
          help={fieldState.error?.message}
        >
          {cloneElement(
            render({ value: field.value, onChange: field.onChange, onBlur: field.onBlur }),
            { id } as Record<string, unknown>,
          )}
        </Form.Item>
      )}
    />
  );
}
