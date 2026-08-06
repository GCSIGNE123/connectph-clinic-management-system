import * as React from "react";

/**
 * Minimal dependency-free re-implementation of Radix's `Slot`, sufficient
 * for the `asChild` pattern used by our button/primitives. Merges the
 * child's props/ref with the ones passed to the wrapping component instead
 * of rendering an extra DOM node.
 */
export const Slot = React.forwardRef<HTMLElement, React.HTMLAttributes<HTMLElement>>(
  ({ children, ...props }, ref) => {
    if (React.isValidElement(children)) {
      const child = children as React.ReactElement<Record<string, unknown>>;
      return React.cloneElement(child, {
        ...props,
        ...child.props,
        className: cnMerge(
          (props as { className?: string }).className,
          (child.props as { className?: string }).className
        ),
        ref,
      });
    }
    return null;
  }
);
Slot.displayName = "Slot";

function cnMerge(a?: string, b?: string): string | undefined {
  return [a, b].filter(Boolean).join(" ") || undefined;
}
