export interface FieldOption {
  value: string;
  label: string;
}

export interface FieldConfig {
  name: string;
  label: string;
  type: "text" | "textarea" | "number" | "select" | "checkbox" | "color" | "time" | "date";
  required?: boolean;
  options?: FieldOption[];
  placeholder?: string;
  /** Only shown/edited on create, not on edit (e.g. codes that are immutable). */
  createOnly?: boolean;
  /** Hidden entirely from the form (e.g. server-generated code shown read-only in the table only). */
  hidden?: boolean;
}

export interface ColumnConfig<T> {
  header: string;
  render: (row: T) => string | number | null | undefined;
}
