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
  /** Enables click-to-sort on this column's header. */
  sortable?: boolean;
  /** Value used for sort comparison, if different from what `render`
   * displays (e.g. `render` formats a price as a string, but sorting
   * should still be numeric). Defaults to `render`'s own return value. */
  sortValue?: (row: T) => string | number | null | undefined;
}
