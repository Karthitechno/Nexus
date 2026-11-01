# Nexus & PayPal Merchant Policy: Payment Terms & Refunds

## 1. Payment Terms
- **Standard Invoicing Terms**: All invoices issued through the Nexus platform default to **Net 30** terms unless explicitly specified otherwise by the merchant.
- **Accepted Payment Methods**: Credit card, debit card, PayPal balance, and bank transfers via PayPal checkout.
- **Due Dates and Reminders**: Customers receive automatic email notifications upon invoice issuance and reminder alerts 3 days prior to due dates.
- **Late Payments**: Invoices overdue by more than 15 calendar days may accrue a late penalty fee of 1.5% per month or the maximum rate permitted by law.

## 2. Refund and Dispute Policies
- **Refund Eligibility Window**: Full or partial refunds can be issued within **180 days** of the original payment transaction date.
- **Refund Processing**: Refunds processed via the PayPal Invoicing API or Refunds API (`/v2/payments/captures/{capture_id}/refund`) are credited back to the customer's original payment method within 3 to 5 business days.
- **Dispute Resolution**: Buyers can file a dispute within 180 days if goods or services are not received or significantly not as described. Merchants have 20 calendar days to respond or provide evidence before a dispute escalates into a claim.
- **Transaction Fees**: PayPal transaction processing fees are generally non-refundable when issuing customer refunds.

