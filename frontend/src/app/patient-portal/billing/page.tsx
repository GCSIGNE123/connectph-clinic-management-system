"use client";

import { useEffect, useState } from "react";
import { patientApiFetch } from "@/features/patient-portal/api/client";

interface InvItem { description: string; quantity: string; unit_price: string; line_total: string; }
interface Payment { id: string; payment_method: string; amount: string; status: string; paid_at: string; }
interface Invoice {
  id: string; invoice_number: string; invoice_date: string; status: string; subtotal: string; discount_total: string;
  grand_total: string; amount_paid: string; balance_due: string; items: InvItem[]; payments: Payment[];
}
interface Summary { outstanding_balance: string; invoices: Invoice[]; }

export default function BillingPage() {
  const [data, setData] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    patientApiFetch<Summary>("/patient-portal/billing").then(setData).catch((e) => setError(e.message));
  }, []);

  if (error) return <div style={{ color: "#dc2626" }}>{error}</div>;
  if (!data) return <div>Loading...</div>;

  return (
    <div>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 16 }}>Billing</h1>
      <div style={{ background: "#0f766e", color: "#fff", borderRadius: 10, padding: 16, marginBottom: 16 }}>
        <div style={{ fontSize: 12, opacity: 0.85 }}>Outstanding Balance</div>
        <div style={{ fontSize: 24, fontWeight: 700 }}>PHP {Number(data.outstanding_balance).toFixed(2)}</div>
      </div>
      {data.invoices.length === 0 && <div style={{ fontSize: 13, color: "#64748b" }}>No invoices yet.</div>}
      {data.invoices.map((inv) => (
        <div key={inv.id} style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: 12, marginBottom: 10 }}>
          <div style={{ fontWeight: 600, fontSize: 14 }}>{inv.invoice_number} - {inv.invoice_date} ({inv.status})</div>
          <div style={{ fontSize: 12, color: "#475569", marginTop: 4 }}>
            Subtotal PHP {Number(inv.subtotal).toFixed(2)} | Discount PHP {Number(inv.discount_total).toFixed(2)} | Total PHP {Number(inv.grand_total).toFixed(2)} | Paid PHP {Number(inv.amount_paid).toFixed(2)} | Balance PHP {Number(inv.balance_due).toFixed(2)}
          </div>
          <div style={{ marginTop: 8, overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead><tr style={{ textAlign: "left", color: "#64748b" }}><th style={{ padding: 4 }}>Item</th><th>Qty</th><th>Unit</th><th>Total</th></tr></thead>
              <tbody>
                {inv.items.map((it, i) => (
                  <tr key={i} style={{ borderTop: "1px solid #f1f5f9" }}>
                    <td style={{ padding: 4 }}>{it.description}</td><td>{it.quantity}</td><td>{Number(it.unit_price).toFixed(2)}</td><td>{Number(it.line_total).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {inv.payments.length > 0 && (
            <div style={{ marginTop: 8, fontSize: 12, color: "#0f766e" }}>
              Payments: {inv.payments.map((p) => `${p.payment_method} PHP ${Number(p.amount).toFixed(2)} (${p.status})`).join(", ")}
            </div>
          )}
        </div>
      ))}
      <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 8 }}>
        Online payment is not available yet - please pay at the clinic&apos;s cashier.
      </div>
    </div>
  );
}
