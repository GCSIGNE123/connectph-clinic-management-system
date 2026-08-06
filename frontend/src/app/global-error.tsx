"use client";

import { useEffect } from "react";

/**
 * Root-level error boundary. Renders its own <html>/<body> because it
 * replaces the entire root layout when an error escapes it.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error(error);
  }, [error]);

  return (
    <html lang="en">
      <body>
        <div
          style={{
            minHeight: "100vh",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: "1rem",
            fontFamily: "system-ui, sans-serif",
            padding: "1.5rem",
            textAlign: "center",
            background: "#f8fafc",
            color: "#0f172a",
          }}
        >
          <h1 style={{ fontSize: "1.25rem", fontWeight: 600 }}>Application error</h1>
          <p style={{ maxWidth: "24rem", fontSize: "0.875rem", color: "#475569" }}>
            A critical error occurred. Please try reloading the application.
          </p>
          <button
            onClick={() => reset()}
            style={{
              borderRadius: "0.375rem",
              background: "#2563EB",
              color: "white",
              padding: "0.5rem 1rem",
              fontSize: "0.875rem",
              fontWeight: 500,
              border: "none",
              cursor: "pointer",
            }}
          >
            Reload
          </button>
        </div>
      </body>
    </html>
  );
}
